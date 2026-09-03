# Словарь данных PostgreSQL

Имена таблиц и колонок соответствуют согласованной нормализованной схеме.
Дочерние таблицы связаны с `company_reports` составным внешним ключом
`(report_id, company_inn) -> (report_id, inn)`.

## company_reports

| column_name | description_ru |
|---|---|
| report_id | Уникальный ID конкретной версии отчёта |
| report_date | Дата формирования отчёта |
| inn | ИНН организации |
| ogrn | ОГРН организации |
| short_name | Краткое наименование контрагента |
| full_name | Полное наименование контрагента |
| risk_level | Общий уровень риска: LOW / MEDIUM / HIGH |
| zsk_risk_level | Уровень риска ЗСК: GREEN / YELLOW / RED |
| kpp | КПП контрагента |
| okpo | ОКПО контрагента |
| address | Юридический адрес |
| email | E-mail компании |
| website | Сайт компании |
| company_size | Размер организации |
| staff | Диапазон численности персонала |
| registration_date | Дата регистрации организации |
| years_from_registration | Сколько лет существует компания |
| status | Статус организации: действующая / закрытая |
| status_reason | Причина закрытия организации |
| status_date | Дата последнего обновления статуса |
| share_capital | Уставный капитал |
| branches_count | Количество филиалов |
| raw_report_json | Полный исходный JSON-отчёт без изменений |

Ключи: `PRIMARY KEY (report_id)`, `UNIQUE (report_id, inn)`.

## structure_items

| column_name | description_ru |
|---|---|
| id | Уникальный ID строки |
| report_id | ID отчёта |
| company_inn | ИНН анализируемой компании |
| subject_inn | ИНН промежуточной сущности для вложенной связи |
| item_type | founder, director, activity, related_company, parent_organization, related_parent_organization, branch, phone, tax_system |
| item_index | Порядковый номер объекта внутри массива |
| name | Имя человека или название объекта |
| related_inn | ИНН связанного лица или организации |
| related_ogrn | ОГРН связанной организации |
| role | Роль объекта в структуре |
| position | Должность руководителя |
| code | Код, например ОКВЭД |
| description | Описание вида деятельности или объекта |
| share | Доля учредителя, % |
| amount | Сумма доли учредителя |
| date_from | Дата начала участия / управления / вступления |
| active | Активен ли объект сейчас |
| registration_date | Дата регистрации связанной компании |
| address | Адрес объекта |
| phone_type | Тип телефона |
| phone_code | Код телефона |
| phone_number | Номер телефона |
| auth_person_name | ФИО руководителя связанной организации |
| auth_person_position | Должность руководителя связанной организации |
| details_json | Дополнительные исходные поля объекта |

Ключ: `PRIMARY KEY (id)`.

## financial_reports

| column_name | description_ru |
|---|---|
| report_id | ID отчёта |
| company_inn | ИНН компании |
| year | Год отчётности |
| proceeds | Выручка |
| profit | Прибыль или убыток |
| total_assets | Общая сумма активов |
| current_assets_total | Оборотные активы всего |
| stocks | Запасы |
| receivables | Дебиторская задолженность |
| bankroll | Денежные средства и эквиваленты |
| uncurrent_assets_total | Внеоборотные активы всего |
| fixed_assets | Основные средства |
| total_liabilities | Всего пассивов |
| capitals | Капитал и резервы |
| long_term_duties_total | Долгосрочные обязательства всего |
| long_term_duties_others | Прочие долгосрочные обязательства |
| short_term_liabilities_total | Краткосрочные обязательства всего |
| borrowed_funds | Краткосрочные заёмные средства |
| accounts_payable | Кредиторская задолженность |
| sustainability | Коэффициент финансовой устойчивости |
| solvency | Коэффициент платёжеспособности |
| profitability | Коэффициент рентабельности |

Ключ: `PRIMARY KEY (report_id, year)`.

## risk_factors

| column_name | description_ru |
|---|---|
| report_id | ID отчёта |
| company_inn | ИНН компании |
| sign | positive или negative |
| item_index | Порядковый номер фактора |
| code | Код фактора |
| name | Текстовое описание фактора |
| chapter | Раздел отчёта |

Ключ: `PRIMARY KEY (report_id, sign, item_index)`.

## arbitration

| column_name | description_ru |
|---|---|
| id | Уникальный ID строки |
| report_id | ID отчёта |
| company_inn | ИНН компании |
| source | Источник агрегации: по годам или по статусам |
| year | Год арбитражных дел |
| role | plaintiff, defendant или all |
| case_status | finished, appealed, pending или all |
| case_count | Количество дел |
| amount | Общая сумма по делам |

Ключ: `PRIMARY KEY (id)`.

## legal_events

| column_name | description_ru |
|---|---|
| report_id | ID отчёта |
| company_inn | ИНН компании |
| event_type | execution, inspection или license |
| item_index | Порядковый номер события |
| external_id | Номер производства, ERP ID проверки и т. п. |
| event_date | Дата события / начала |
| end_date | Дата окончания |
| active | Активно ли событие |
| status | Статус проверки, лицензии и т. п. |
| amount | Сумма исполнительного производства |
| title | Название лицензии или объекта |
| authority | Контролирующий орган / орган выдачи |
| form | Форма проверки |
| details_json | Дополнительные исходные поля события |

Ключ: `PRIMARY KEY (report_id, event_type, item_index)`.

## procurements

| column_name | description_ru |
|---|---|
| report_id | ID отчёта |
| company_inn | ИНН компании |
| item_index | Порядковый номер записи |
| year | Год проведения закупок |
| federal_law_code | Код федерального закона |
| tender_admitted_count | Количество тендеров с участием компании |
| tender_winner_count | Количество выигранных тендеров |
| contract_signed_count | Количество подписанных контрактов |
| contract_signed_amount | Общая сумма подписанных контрактов |

Ключ: `PRIMARY KEY (report_id, item_index)`.
