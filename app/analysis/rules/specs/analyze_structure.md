# `analyze_structure`

Тул читает `company_reports`, `structure_items`, `risk_factors` и записи лицензий из `legal_events`. LLM, сеть и внешние реестры не используются.

Глава не выставляет риск: `risk_level = UNKNOWN`. Все находки возвращаются в `observations`.

Проверки с пометкой «только для юрлиц» не применяются к ИП.

## Наблюдения

### `director_authority`

Срабатывает в одном из случаев:

- у юрлица нет директора и нет управляющей организации;
- должность директора содержит признаки ликвидации, банкротства или арбитражного управления.

Evidence:

- `company_reports.inn`, `full_name`, если руководитель отсутствует
- `structure_items[].position`
- `structure_items[].name`
- `company_reports.status`
- `company_reports.status_reason`

### `director_change`

Срабатывает, если директор назначен не более чем за `365` дней до даты отчёта.

Если назначение было не более чем за `90` дней до даты отчёта, это отдельно отражается в тексте.

Evidence:

- `structure_items[].date_from`
- `structure_items[].name`
- `company_reports.report_date`

### `mass_director`

Срабатывает, если текущий директор также указан руководителем связанных организаций из того же отчёта.

Если таких связанных организаций не меньше `3`, текст усиливается.

Evidence:

- `structure_items[].name` директора
- `structure_items[].auth_person_name` связанных организаций
- `structure_items[].name` связанных организаций
- `risk_factors[].name`, если есть связанный флаг поставщика

### `provider_flags`

Срабатывает, если в `risk_factors` есть негативные флаги поставщика:

- `invalidAuthpersonsData`
- `disqualifiedAuthpersons`
- `massAuthpersons`
- `invalidRegistrationData`

Evidence:

- `risk_factors[].name`

### `ownership_integrity`

Только для юрлиц.

Срабатывает, если данные об участниках противоречивы:

- все перечисленные учредители неактивны;
- сумма долей активных учредителей отличается от `100%` больше чем на `1` п.п.;
- сумма долей в рублях отличается от `company_reports.share_capital` больше чем на `1` рубль.

Evidence:

- `structure_items[].active`
- `structure_items[].share`
- `structure_items[].amount`
- `company_reports.share_capital`

### `ownership_chain`

Только для юрлиц.

Срабатывает, если контроль идёт через другие организации:

- среди активных учредителей есть юрлицо;
- либо руководителем выступает управляющая организация.

Evidence:

- `structure_items[].related_inn`
- `structure_items[].name`

### `affiliation`

Срабатывает, если ИНН учредителя или руководителя совпадает с ИНН связанной организации.

Если доля такого участника не ниже `20%`, в тексте отмечается признак взаимозависимости.

Evidence:

- `structure_items[].related_inn`
- `structure_items[].name`
- `structure_items[].share`, если применяется порог `20%`

### `okved_breadth`

Срабатывает, если:

- дополнительных ОКВЭД больше `20`;
- либо поставщик данных передал негативный фактор `massOkved`.

Если дополнительных ОКВЭД больше `50`, это отдельно отражается в тексте.

Evidence:

- `structure_items[].code` основного и дополнительных ОКВЭД
- `risk_factors[].name`, если используется `massOkved`

### `license_gap`

Срабатывает, если основной ОКВЭД входит в перечень групп, где могут требоваться лицензии, специальные разрешения или СРО, и в отчёте нет активной лицензии.

Проверяется только основной ОКВЭД. Отсутствие `licenses` в raw не трактуется как доказанное отсутствие обязательного разрешения.

Evidence:

- `structure_items[].code`
- `structure_items[].description`

### `shell_pattern`

Только для юрлиц.

Срабатывает, если одновременно выполняются минимум `3` формальных признака:

- уставный капитал не выше `10 000` ₽;
- либо уставный капитал не выше `100 000` ₽;
- единственный участник является руководителем;
- компания зарегистрирована не более `1` года назад;
- микропредприятие без филиалов;
- нет телефона, e-mail и сайта;
- дополнительных ОКВЭД больше `20`.

Это не вывод о фиктивности компании. Это только сигнал соотнести масштаб контрагента с суммой сделки.

Evidence:

- `company_reports.share_capital`
- `structure_items[].share`
- `structure_items[].name`
- `company_reports.registration_date`
- `company_reports.company_size`
- `company_reports.branches_count`
- `company_reports.email`
- `company_reports.website`
- `structure_items[].code`

## Недостаточность данных

Если `structure_items` пустой, глава считается недостаточной по данным. Отсутствие отдельного поля не приравнивается к нулю или подтверждённому отсутствию признака.
