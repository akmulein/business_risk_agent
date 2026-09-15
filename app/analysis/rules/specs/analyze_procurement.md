# `analyze_procurement`

Тул читает `procurements` и `company_reports.report_date`. LLM, сеть, ЕИС и реестр недобросовестных поставщиков не используются.

Глава не выставляет риск: `risk_level = UNKNOWN`. Все находки возвращаются в `observations`.

## Общие правила

Если за один год есть несколько строк закупок, годовые показатели суммируются по строкам этого года.

`winner_count > signed_count` трактуется только как расхождение агрегированных счётчиков. Без связи с конкретной закупкой тул не делает вывод о неподписании контракта или уклонении поставщика.

## Наблюдения

### `abnormal_win_rate`

Срабатывает, если всего подано не меньше `5` заявок и доля побед:

- не выше `15%`;
- либо не ниже `90%`.

Evidence:

- `procurements[].tender_admitted_count`
- `procurements[].tender_winner_count`
- `procurements[].year`

### `contract_signing_gap`

Срабатывает, если в каком-либо году `tender_winner_count > contract_signed_count`.

Наблюдение фиксирует только расхождение агрегированных данных.

Evidence:

- `procurements[].tender_winner_count`
- `procurements[].contract_signed_count`
- `procurements[].year`

### `activity_dropoff`

Срабатывает, если у компании была закупочная активность, но последний год с записью в `procurements` отстаёт от года отчёта минимум на `2` года.

Evidence:

- `procurements[].tender_admitted_count`
- `procurements[].tender_winner_count`
- `procurements[].contract_signed_count`
- `procurements[].year`
- `company_reports.report_date`

### `contract_size_spike`

Срабатывает, если есть минимум два года с подписанными контрактами и средний контракт последнего активного года минимум в `4` раза больше среднего по предыдущим активным годам.

Evidence:

- `procurements[].contract_signed_amount`
- `procurements[].contract_signed_count`
- `procurements[].year`

### `law_regime_mix`

Срабатывает, если подписано минимум `3` контракта и доля 223-ФЗ не ниже `80%`.

Если есть суммы, доля считается по сумме контрактов. Если сумм нет, доля считается по количеству контрактов.

Выводы 44-ФЗ не применяются к строкам 223-ФЗ.

Evidence:

- `procurements[].federal_law_code`
- `procurements[].contract_signed_amount`
- `procurements[].contract_signed_count`
- `procurements[].year`

## Недостаточность данных

Если `procurements` пустой, глава считается недостаточной по данным. Отсутствие закупочных строк не означает отсутствие закупок во внешних источниках.
