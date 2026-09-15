# `analyze_general`

Тул читает только `company_reports`. LLM, сеть и внешние реестры не используются.

Глава не выставляет риск: `risk_level = UNKNOWN`. Все находки возвращаются в `observations`.

## Наблюдения

### `closed_status`

Срабатывает, если `company_reports.status` равен `CLOSED` или `закрытая`.

В evidence попадают:

- `company_reports.status`
- `company_reports.status_reason`

Тул не проверяет актуальность статуса во внешних реестрах и не использует поля `risk_level` / `zsk_risk_level` как отдельные наблюдения.
