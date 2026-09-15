# `analyze_legal`

Тул читает `arbitration`, `legal_events`, `company_reports` и последние финансовые показатели для оценки масштаба сумм. LLM, сеть и внешние реестры не используются.

Глава не выставляет риск: `risk_level = UNKNOWN`. Все находки возвращаются в `observations`.

## Общие правила

Арбитражные данные бывают двух типов:

- `source = status` / `by_status` — разбивка по статусам дел;
- `source = yearly` / `by_year` — годовая динамика.

Эти источники не суммируются между собой. Строки `role = all` не используются для порогов, чтобы не удваивать данные.

## Наблюдения

### `defendant_exposure`

Срабатывает по строкам `source = status`, `role = defendant`, если есть открытые (`pending`) или обжалованные (`appealed`) дела.

Закрытые дела (`finished`) сами по себе наблюдение не создают, но могут попадать в текст как фон.

Evidence:

- `arbitration[].case_count`
- `arbitration[].amount`
- `arbitration[].case_status`
- `company_reports.report_date`
- последние `financial_reports[].proceeds`, `profit`, `total_assets`, если используются для масштаба

### `arbitration_trend`

Срабатывает по годовым строкам ответчика, если за последние годы есть рост нагрузки.

Условия:

- последний год минимум в 2 раза выше предыдущего по числу дел или сумме;
- либо нагрузка растёт три года подряд.

Год без строки в отчёте не считается нулём.

Evidence:

- `arbitration[].year`
- `arbitration[].case_count`
- `arbitration[].amount`
- `company_reports.report_date`

### `enforcement_load`

Срабатывает, если в `legal_events` есть активные исполнительные производства: `event_type = execution`, `active = true`.

Тул сохраняет фактический статус и сумму из отчёта. Он не утверждает, что долг подтверждён судом или что он не исполнен, если этого нет в raw-данных.

Evidence:

- `legal_events[].active`
- `legal_events[].amount`
- `legal_events[].external_id`, если есть
- `legal_events[].event_date`, если есть
- последние `financial_reports[].proceeds`, `profit`, `total_assets`, если используются для масштаба

### `inspection_findings`

Срабатывает по `legal_events` с `event_type = inspection`, если статус содержит признаки нарушения или предстоящей проверки.

Не срабатывает на проверки без нарушений, отменённые проверки и записи без понятного результата.

Evidence:

- `legal_events[].status`
- `legal_events[].authority`
- `legal_events[].title`
- `legal_events[].form`
- `legal_events[].event_date`
- `legal_events[].end_date`

### `license_validity`

Срабатывает по `legal_events` с `event_type = license`, если лицензия неактивна или истекает в ближайшие `90` дней от даты отчёта.

Не проверяет, нужна ли лицензия для ОКВЭД. Это делает `analyze_structure`.

Evidence:

- `company_reports.report_date`
- `legal_events[].status`
- `legal_events[].end_date`
- `legal_events[].title`
- `legal_events[].external_id`
- `legal_events[].authority`
- `legal_events[].event_date`

## Недостаточность данных

Если нет ни `arbitration`, ни `legal_events`, глава считается недостаточной по данным. Пустые массивы не означают отсутствие юридических рисков во внешнем мире.
