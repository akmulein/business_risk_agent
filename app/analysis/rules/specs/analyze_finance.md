# `analyze_finance`

Тул читает `financial_reports` и финансовые коэффициенты, уже сохранённые в карточке. LLM, сеть и внешние источники не используются.

Проверки работают по последнему отчётному году. Для динамики выручки используются последние два года, при наличии — последние три года.

Глава не выставляет риск: `risk_level = UNKNOWN`. Все находки возвращаются в `observations`.

## Наблюдения

### `net_loss`

Срабатывает, если `profit` последнего отчётного года меньше `0`.

Evidence:

- `financial_reports[].profit`
- `financial_reports[].year`

### `revenue_decline`

Срабатывает, если `proceeds` последнего года меньше `proceeds` предыдущего года.

Если есть три года и снижение идёт два года подряд, это отдельно отражается в тексте наблюдения.

Evidence:

- `financial_reports[].proceeds`
- `financial_reports[].year`

### `liquidity_gap`

Срабатывает, если показатель покрытия краткосрочных обязательств меньше `1.0`.

Приоритет источников:

1. `solvency`, если он есть в отчёте.
2. Расчёт `current_assets_total / short_term_liabilities_total`, если `solvency` отсутствует.

Evidence:

- `financial_reports[].solvency`, если используется коэффициент поставщика
- `financial_reports[].current_assets_total`, если используется расчёт
- `financial_reports[].short_term_liabilities_total`, если используется расчёт
- `financial_reports[].year`

### `negative_equity`

Срабатывает, если `capitals` последнего отчётного года меньше `0`.

Evidence:

- `financial_reports[].capitals`
- `financial_reports[].year`
- `financial_reports[].total_liabilities`, если есть
- `financial_reports[].total_assets`, если есть

### `leverage`

Срабатывает в одном из двух случаев:

1. `sustainability` есть в отчёте и меньше `0.5`.
2. `sustainability` отсутствует, а расчётная доля долговых обязательств в активах не ниже `0.85`.

Расчётная доля долга считается так:

- если есть `long_term_duties_total` и `short_term_liabilities_total`, используется их сумма;
- иначе используется `total_assets - capitals`, только если баланс выглядит согласованным;
- `total_liabilities` не считается долгом, потому что в raw-схеме это итог пассива и он включает капитал.

Evidence:

- `financial_reports[].sustainability`, если используется коэффициент поставщика
- `financial_reports[].long_term_duties_total`, если используется явный долг
- `financial_reports[].short_term_liabilities_total`, если используется явный долг
- `financial_reports[].total_assets`
- `financial_reports[].capitals`, если используется fallback `assets - capital`
- `financial_reports[].total_liabilities`, если используется для проверки баланса
- `financial_reports[].year`

## Недостаточность данных

Если `financial_reports` пустой, глава считается недостаточной по данным. Отсутствие отдельного поля не приравнивается к нулю.
