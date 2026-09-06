from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openrouter import OpenRouterModel

from .domain import ComparisonCompany, RiskLevel, VerificationStatus
from .llm_provider import openrouter_provider
from .settings import Settings

logger = logging.getLogger(__name__)


class ComparisonStatement(BaseModel):
    text: str = Field(
        max_length=320,
        description="Одно короткое утверждение только по указанным фактам",
    )
    fact_refs: list[str] = Field(
        min_length=1,
        max_length=2,
        description="Идентификаторы фактов, подтверждающих всё утверждение",
    )


class CompanyComparisonStatement(BaseModel):
    company_inn: str = Field(
        description="ИНН единственной компании, о которой говорится в утверждении",
    )
    text: str = Field(
        max_length=360,
        description="Одно ёмкое утверждение об одной компании",
    )
    fact_refs: list[str] = Field(
        min_length=1,
        max_length=4,
        description="Идентификаторы всех фактов, использованных в утверждении",
    )


class ComparisonSummaryOutput(BaseModel):
    leader_statement: ComparisonStatement
    company_statements: list[CompanyComparisonStatement] = Field(
        min_length=2,
        max_length=4,
    )


COMPARISON_INSTRUCTIONS = """
Составь ёмкий сравнительный анализ российских контрагентов: 3–6 коротких
предложений, не более 1200 знаков суммарно. Он может быть в 1,5–2 раза
подробнее анализа одной компании, но без повторов и общих рассуждений.

leader_statement — первое предложение только о лидере или лидирующей группе
по готовой банковской оценке. Используй строго fact comparison.leaders.
company_statements — отдельные предложения о конкретных компаниях. В каждом
элементе укажи точный company_inn, пиши только об этой компании и используй
не более трёх наиболее важных фактов этой компании. Сначала объясни сильными
сторонами и важными оговорками, почему лидер или лидирующая группа выглядит
лучше, затем назови главные факторы внимания компаний с высоким и средним
риском. Не повторяй в этих предложениях сам уровень риска — он уже назван и
показан в таблице. Не объединяй факты разных компаний в одном предложении и не обобщай их
словами «у них», «у обеих» или «в их отчётах». При одинаковом risk_level не
утверждай, что одна компания надёжнее другой.

Используй только входные facts и не меняй их смысл. Не добавляй причин,
предположений, прогнозов или рекомендаций. Не называй отсутствие сведений
отсутствием риска. Уровень риска уже определён банком — не пересчитывай его.
Числа переноси точно в указанном формате. Не упоминай JSON, поля, источники и
процесс проверки. Для каждого предложения укажи fact_refs на все факты,
которые оно использует. Не упоминай ни одного показателя или числа, если его
fact_ref не указан.
""".strip()

RISK_LABELS = {
    RiskLevel.LOW: "низкий риск",
    RiskLevel.MEDIUM: "средний риск",
    RiskLevel.HIGH: "высокий риск",
    RiskLevel.UNKNOWN: "нет оценки риска",
}


def _money(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ") + " ₽"


def _percent(value: float) -> str:
    return f"{value:.1f}%".replace(".", ",")


def _enforcement_text(count: int) -> str:
    last_two = count % 100
    last = count % 10
    if last_two in range(11, 15) or last == 0 or last >= 5:
        return f"{count} действующих исполнительных производств"
    if last == 1:
        return f"{count} действующее исполнительное производство"
    return f"{count} действующих исполнительных производства"


def _defendant_case_text(count: int) -> str:
    last_two = count % 100
    last = count % 10
    if last_two in range(11, 15) or last == 0 or last >= 5:
        return f"{count} текущих арбитражных дел в роли ответчика"
    if last == 1:
        return f"{count} текущее арбитражное дело в роли ответчика"
    return f"{count} текущих арбитражных дела в роли ответчика"


def _ranking_facts(companies: list[ComparisonCompany]) -> list[dict[str, Any]]:
    grouped: dict[RiskLevel, list[str]] = defaultdict(list)
    for company in companies:
        grouped[company.risk_level].append(company.name)
    leader_level = companies[0].risk_level
    leaders = grouped[leader_level]
    if leader_level == RiskLevel.UNKNOWN:
        leader_text = (
            "По банковской оценке лидера выделить нельзя: для всех компаний "
            "уровень риска не определён."
        )
    else:
        subject = "выглядит" if len(leaders) == 1 else "выглядят"
        leader_text = (
            f"Лучше остальных по банковской оценке {subject} "
            f"{', '.join(leaders)}: {RISK_LABELS[leader_level]}."
        )
    facts: list[dict[str, Any]] = [
        {
            "id": "comparison.leaders",
            "kind": "ranking",
            "leader": True,
            "text": leader_text,
        }
    ]
    return facts


def _facts(companies: list[ComparisonCompany]) -> list[dict[str, Any]]:
    facts = _ranking_facts(companies)
    leader_level = companies[0].risk_level
    strength_counts: dict[str, int] = defaultdict(int)

    def add(
        company: ComparisonCompany,
        field: str,
        kind: str,
        text: str,
    ) -> None:
        is_leader = company.risk_level == leader_level
        if kind == "strength" and not is_leader:
            return
        if kind == "strength":
            if strength_counts[company.inn] >= 3:
                return
            strength_counts[company.inn] += 1
        facts.append(
            {
                "id": f"{company.inn}.{field}",
                "kind": kind,
                "leader": is_leader,
                "company_inn": company.inn,
                "risk_level": company.risk_level.value,
                "text": text,
            }
        )

    for company in companies:
        name = company.name
        if company.bankruptcy_status == VerificationStatus.ISSUE:
            add(
                company,
                "bankruptcy_status",
                "concern",
                f"У {name} есть отметка о банкротстве или ликвидации.",
            )
        elif company.bankruptcy_status == VerificationStatus.OK:
            add(
                company,
                "bankruptcy_status",
                "strength",
                f"В отчёте {name} нет отметки о банкротстве или ликвидации.",
            )
        if company.fns_status == VerificationStatus.ISSUE:
            add(
                company,
                "fns_status",
                "concern",
                f"У {name} есть замечания по проверяемым признакам ФНС.",
            )
        elif company.fns_status == VerificationStatus.OK:
            add(
                company,
                "fns_status",
                "strength",
                f"В отчёте {name} нет замечаний по проверяемым признакам ФНС.",
            )
        if (
            company.active_enforcements is not None
            and company.active_enforcements > 0
        ):
            add(
                company,
                "active_enforcements",
                "concern",
                f"У {name} — "
                f"{_enforcement_text(company.active_enforcements)}.",
            )
        elif company.active_enforcements == 0:
            add(
                company,
                "active_enforcements",
                "strength",
                f"У {name} нет действующих исполнительных производств.",
            )
        if company.defendant_cases is not None and company.defendant_cases > 0:
            add(
                company,
                "defendant_cases",
                "concern",
                f"У {name} — {_defendant_case_text(company.defendant_cases)}.",
            )
        elif company.defendant_cases == 0:
            add(
                company,
                "defendant_cases",
                "strength",
                f"У {name} нет текущих арбитражных дел в роли ответчика.",
            )
        if company.profit is not None and company.profit < 0:
            add(
                company,
                "profit",
                "concern",
                f"Убыток {name} за "
                f"{company.financial_year or 'последний отчётный год'} "
                f"составляет {_money(abs(company.profit))}.",
            )
        elif company.profit is not None and company.profit > 0:
            add(
                company,
                "profit",
                "strength",
                f"Прибыль {name} за "
                f"{company.financial_year or 'последний отчётный год'} "
                f"составляет {_money(company.profit)}.",
            )
        if (
            company.revenue_change_percent is not None
            and company.revenue_change_percent < 0
        ):
            add(
                company,
                "revenue_change_percent",
                "concern",
                f"Выручка {name} снизилась на "
                f"{_percent(abs(company.revenue_change_percent))} "
                "к предыдущему отчётному году.",
            )
        elif (
            company.revenue_change_percent is not None
            and company.revenue_change_percent > 0
        ):
            add(
                company,
                "revenue_change_percent",
                "strength",
                f"Выручка {name} выросла на "
                f"{_percent(company.revenue_change_percent)} "
                "к предыдущему отчётному году.",
            )
        if company.capital is not None and company.capital < 0:
            add(
                company,
                "capital",
                "concern",
                f"Капитал {name} за "
                f"{company.financial_year or 'последний отчётный год'} "
                f"отрицательный: −{_money(abs(company.capital))}.",
            )
    return facts


def _number_tokens(text: str) -> set[str]:
    return {
        token.replace(".", ",")
        for token in re.findall(r"\d+(?:[.,]\d+)?", text)
    }


def _check_numbers(
    statement: ComparisonStatement | CompanyComparisonStatement,
    facts_by_id: dict[str, Any],
) -> None:
    """Единственная оставленная проверка: числа в тексте должны быть
    подтверждены цитируемыми фактами."""
    cited_text = " ".join(
        str(facts_by_id[ref]["text"])
        for ref in statement.fact_refs
        if ref in facts_by_id
    )
    unsupported = _number_tokens(statement.text) - _number_tokens(cited_text)
    if unsupported:
        raise RuntimeError(
            "В тексте использованы числа, которых нет в указанных fact_refs: "
            + ", ".join(sorted(unsupported))
        )


class ComparisonAgent:
    def __init__(self, settings: Settings) -> None:
        self.enabled = bool(settings.openrouter_api_key)
        self.agent = None
        if self.enabled:
            model = OpenRouterModel(
                settings.openrouter_model,
                provider=openrouter_provider(settings.openrouter_api_key),
            )
            self.agent = Agent(
                model,
                output_type=ComparisonSummaryOutput,
                instructions=COMPARISON_INSTRUCTIONS,
                model_settings={"temperature": 0},
            )

    async def summarize(self, companies: list[ComparisonCompany]) -> str:
        if not self.agent:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")
        facts = _facts(companies)
        facts_by_id = {str(fact["id"]): fact for fact in facts}
        base_prompt = json.dumps(
            {
                "task": "Составь ёмкое сравнение и выдели главные факторы.",
                "facts": facts,
            },
            ensure_ascii=False,
        )

        max_attempts = 3
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            prompt = base_prompt
            if last_error is not None:
                prompt = (
                    f"{base_prompt}\n\n"
                    f"Предыдущая попытка не прошла проверку: {last_error}. "
                    "Исправь именно это и составь сравнение заново, "
                    "не меняя остальное."
                )
            try:
                logger.info("Comparison LLM call attempt=%d", attempt)
                result = await self.agent.run(prompt)
                summary = self._build_summary(result.output, facts_by_id)
                logger.info("Comparison LLM call succeeded attempt=%d", attempt)
                return summary
            except Exception as error:  # noqa: BLE001 - retried, then re-raised
                last_error = error
                logger.warning(
                    "Comparison LLM call attempt=%d failed: %s", attempt, error
                )
                if attempt == max_attempts:
                    raise RuntimeError(
                        f"Не удалось получить корректное сравнение за "
                        f"{max_attempts} попыток: {error}"
                    ) from error
        raise RuntimeError("Не удалось получить сравнение")

    @staticmethod
    def _build_summary(
        output: ComparisonSummaryOutput,
        facts_by_id: dict[str, Any],
    ) -> str:
        ordered_statements = [output.leader_statement, *output.company_statements]
        if set(output.leader_statement.fact_refs) != {"comparison.leaders"}:
            raise RuntimeError("Первое утверждение не ссылается на лидеров")
        for statement in ordered_statements:
            unknown_refs = set(statement.fact_refs) - facts_by_id.keys()
            if unknown_refs:
                raise RuntimeError(
                    "Указаны неизвестные fact_refs: "
                    + ", ".join(sorted(unknown_refs))
                )
            _check_numbers(statement, facts_by_id)
        for statement in output.company_statements:
            expected_prefix = f"{statement.company_inn}."
            if not all(
                ref.startswith(expected_prefix) for ref in statement.fact_refs
            ):
                raise RuntimeError(
                    "Утверждение компании ссылается на факты другого контрагента"
                )
        summary = " ".join(
            statement.text.strip() for statement in ordered_statements
        )
        if len(summary) > 1200:
            raise RuntimeError("Сравнительный анализ длиннее 1200 знаков")
        return summary
