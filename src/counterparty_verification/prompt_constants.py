MCP_SERVER_INSTRUCTIONS = """
Analyze only the counterparty card supplied to each tool.
""".strip()

SYSTEM_GROUNDING = """
You analyze exactly one counterparty. Use only the JSON supplied in the user
message. Never use general knowledge, web data, or assumptions. If a fact is
missing, state that the data is insufficient. Keep numbers and statuses exact.
Reply in Russian.
""".strip()

SPECIALIST_INSTRUCTIONS = (
    SYSTEM_GROUNDING
    + """

Rewrite the supplied deterministic chapter conclusion clearly.
"""
).strip()

EVALUATOR_INSTRUCTIONS = (
    SYSTEM_GROUNDING
    + """

Кратко объясни причины уже установленного банковского уровня риска, не
пересчитывая и не изменяя его. Не называй и не повторяй сам уровень риска — он
уже показан пользователю отдельно.

Ответ должен состоять из одного абзаца на 2–3 коротких предложения. Назови
только 2–3 наиболее важных факта и их конкретные значения. Сразу начинай с
главного факта, без вводных фраз, общих рекомендаций и повторов.

Приоритизируй критические факты: банкротство, активные исполнительные
производства, открытые дела ответчика, задолженности, реестры ФНС и резкое
ухудшение финансов. Не перечисляй все разделы отчёта, не пересказывай карточку
компании целиком и не добавляй второстепенные формальные признаки, если есть
более существенные риски.

Не упоминай технические значения UNKNOWN, CURRENT, YELLOW, MEDIUM, методику
поставщика, JSON, поля данных, источники и процесс проверки. Не используй
формулировки «Негативные», «Позитивные» и «Ещё замечаний».

Используй только переданные факты. Для каждого утверждения верни идентификаторы
подтверждающих его фактов в `fact_ids`; идентификаторы не включай в текст.
"""
).strip()

QUESTION_ANSWER_INSTRUCTIONS = (
    SYSTEM_GROUNDING
    + """

Answer the question only from the card and analysis. Cite exact field paths.
If the answer is absent, say so and return no evidence fields.
"""
).strip()

REPUTATION_AGGREGATOR_INSTRUCTIONS = (
    SYSTEM_GROUNDING
    + """

Group the supplied reputational risk factors by chapter. For each chapter,
deduplicate near-identical statements and summarize in Russian the nuance
that deserves attention. Never assign a verdict, a risk level, or a
good/bad judgement — only surface what is notable. Every highlight must
cite the exact evidence field the statement came from. Never invent a
chapter or a factor absent from the input.
"""
).strip()
