from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from .chat_models import ChatAgentResult, ChatMessage, ChatSource
from .domain import AnalysisResponse, CounterpartyCard
from .llm_config import MODEL_SYSTEM_PROMPT
from .settings import Settings


class ChatModelNotConfiguredError(RuntimeError):
    pass


class ChatModelCitation(BaseModel):
    inn: str = Field(description="ИНН отчёта, к которому относится факт")
    field: str = Field(description="Точный путь поля из fields этого отчёта")


class ChatModelOutput(BaseModel):
    answer: str = Field(
        description=(
            "Краткий прямой ответ, обычно 1–3 предложения. Не упоминать поля, "
            "JSON, источники, citations или процесс проверки"
        )
    )
    citations: list[ChatModelCitation] = Field(
        default_factory=list,
        description=(
            "Пары inn/field для машинной проверки фактов; не дублировать "
            "их в answer"
        ),
    )
    insufficient_data: bool = Field(
        default=False,
        description="true, если в отчётах нет ответа",
    )


def flatten_evidence(value: Any, prefix: str = "") -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if isinstance(value, dict):
        if not value and prefix:
            fields[prefix] = {}
        for key, nested in value.items():
            path = f"{prefix}.{key}" if prefix else key
            fields.update(flatten_evidence(nested, path))
    elif isinstance(value, list):
        if not value and prefix:
            fields[prefix] = []
        for index, nested in enumerate(value):
            fields.update(flatten_evidence(nested, f"{prefix}[{index}]"))
    elif value is not None and prefix:
        fields[prefix] = value
    return fields


def _openrouter_model(settings: Settings) -> OpenRouterModel:
    if not settings.openrouter_api_key:
        raise ChatModelNotConfiguredError("OPENROUTER_API_KEY is not configured")
    return OpenRouterModel(
        settings.openrouter_model,
        provider=OpenRouterProvider(api_key=settings.openrouter_api_key),
    )


class ReportChatAgent:
    def __init__(self, settings: Settings, model_agent: Any | None = None) -> None:
        if model_agent is not None:
            self.agent = model_agent
        elif settings.openrouter_api_key:
            self.agent = Agent(
                _openrouter_model(settings),
                output_type=ChatModelOutput,
                instructions=MODEL_SYSTEM_PROMPT,
            )
        else:
            self.agent = None

    async def answer(
        self,
        question: str,
        cards: list[CounterpartyCard],
        analyses: dict[str, AnalysisResponse],
        history: list[ChatMessage],
    ) -> ChatAgentResult:
        if self.agent is None:
            raise ChatModelNotConfiguredError("OPENROUTER_API_KEY is not configured")

        evidence_by_inn: dict[str, dict[str, Any]] = {}
        reports: list[dict[str, Any]] = []
        compact_analyses: list[dict[str, Any]] = []
        for card in cards:
            inn = card.company_reports.inn
            fields = flatten_evidence(card.model_dump(mode="json"))
            evidence_by_inn[inn] = fields
            reports.append({"inn": inn, "fields": fields})
            analysis = analyses.get(inn)
            if analysis is not None:
                compact_analyses.append(
                    {
                        "inn": inn,
                        "risk_level": analysis.risk_level,
                        "chapters": [
                            {
                                "chapter": chapter.chapter,
                                "risk_level": chapter.risk_level,
                                "data_sufficient": chapter.data_sufficient,
                            }
                            for chapter in analysis.chapters
                        ],
                    }
                )

        payload = {
            "question": question,
            "reports": reports,
            "analyses": compact_analyses,
            "history": [
                {"role": message.role, "content": message.content}
                for message in history
            ],
        }
        result = await self.agent.run(
            json.dumps(payload, ensure_ascii=False, default=str)
        )
        output = ChatModelOutput.model_validate(result.output)
        if output.insufficient_data:
            return ChatAgentResult(
                answer="В предоставленных отчетах нет данных для ответа."
            )
        if not output.citations:
            return ChatAgentResult(
                answer="В предоставленных отчетах нет подтверждения для ответа."
            )

        sources: list[ChatSource] = []
        seen: set[tuple[str, str]] = set()
        for citation in output.citations:
            fields = evidence_by_inn.get(citation.inn)
            key = (citation.inn, citation.field)
            if fields is None or citation.field not in fields:
                return ChatAgentResult(
                    answer=("В предоставленных отчетах нет подтверждения для ответа.")
                )
            if key not in seen:
                sources.append(
                    ChatSource(
                        inn=citation.inn,
                        field=citation.field,
                        value=fields[citation.field],
                    )
                )
                seen.add(key)
        return ChatAgentResult(answer=output.answer.strip(), sources=sources)
