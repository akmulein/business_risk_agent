# Контекст реализации MVP

Этот документ предназначен для разработчика или AI-агента, который продолжит
работу над проектом на другом устройстве. Исходные требования находятся в
`description.md`, перечень полей карточки — в `input_data_columns.md`.

## Цель и ключевое ограничение

Пользователь вводит ИНН юридического лица. Сервис выбирает ровно одну карточку
контрагента, анализирует её по шести главам и возвращает текстовое summary.
После анализа пользователь может задавать уточняющие вопросы.

Критическое требование: LLM может использовать только выбранную карточку и
результаты её анализа. Веб-поиск и внешние источники не подключены. Если данных
не хватает, агент должен прямо сообщить об этом.

## Выбранный стек

- Python 3.12, окружение conda `alpha_hackathon`;
- FastAPI — внешний HTTP API;
- FastMCP — отдельный MCP-сервис с аналитическими инструментами;
- Pydantic AI — specialist, evaluator и Q&A agents;
- OpenRouter — провайдер моделей;
- Pydantic — входные, доменные и выходные схемы;
- SQLAlchemy + asyncpg — заготовка подключения PostgreSQL;
- pytest — тесты без настоящего API-ключа.

Зависимости зафиксированы в `pyproject.toml` и `environment.yml`. Настройки
описаны в `.env.example`; настоящий `.env` игнорируется Git.

## Структура и ответственность модулей

- `src/counterparty_verification/domain.py` — карточка, уровни риска,
  `ChapterResult`, API-схемы и проверка контрольной суммы ИНН.
- `src/counterparty_verification/repositories.py` — протокол репозитория,
  рабочий JSON-репозиторий и PostgreSQL-репозиторий для нормализованной схемы.
- `src/counterparty_verification/analyzers.py` — шесть детерминированных
  анализаторов. Они формируют выводы, факторы риска и evidence с путями полей.
- `src/counterparty_verification/mcp_server.py` — FastMCP-сервер, публикующий
  каждый анализатор как отдельный tool.
- `src/counterparty_verification/mcp_client.py` — HTTP-клиент MCP с таймаутом и
  двумя попытками; локальный адаптер используется в тестах.
- `src/counterparty_verification/agents.py` — конфигурация Pydantic AI через
  OpenRouter, specialist/evaluator/Q&A и проверки ссылок на исходные поля.
- `src/counterparty_verification/prompt_constants.py` — единая точка изменения
  всех UPPER_CASE-промптов для MCP и LLM-агентов.
- `src/counterparty_verification/services.py` — параллельный запуск всех глав,
  частичный результат при отказе одной главы и TTL-хранилище Q&A-сессий.
- `src/counterparty_verification/api.py` — FastAPI-приложение и обработка
  HTTP-ошибок.
- `data/counterparties.json` — временная синтетическая карточка. Она не является
  реальным отчётом об указанной организации.

## Поток запроса

1. `POST /api/v1/analyses` валидирует десятизначный ИНН и его контрольную сумму.
2. `CounterpartyRepository.get_by_inn()` возвращает только одну карточку.
3. `AnalysisService` параллельно вызывает шесть MCP tools:
   `analyze_general`, `analyze_structure`, `analyze_legal`,
   `analyze_reputation`, `analyze_finance`, `analyze_procurement`.
4. Сбой отдельного MCP tool не отменяет отчёт: соответствующая глава получает
   `UNKNOWN` и пометку об ошибке.
5. При наличии `OPENROUTER_API_KEY` specialist-agents улучшают формулировки, а
   evaluator-agent создаёт summary. Выход LLM принимается только с допустимыми
   ссылками на evidence. Без ключа формируется детерминированное summary.
6. Карточка и результат сохраняются в памяти на `SESSION_TTL_SECONDS`; клиенту
   возвращается `analysis_id`.
7. `POST /api/v1/analyses/{analysis_id}/questions` передаёт Q&A-agent только
   снимок этой карточки и её главы. Ссылки на отсутствующие поля отклоняются.

## API

### Создание анализа

```http
POST /api/v1/analyses
Content-Type: application/json

{"inn":"7707083893"}
```

Ответ: `analysis_id`, `inn`, `summary`, `risk_level`, `chapters`.

### Уточняющий вопрос

```http
POST /api/v1/analyses/{analysis_id}/questions
Content-Type: application/json

{"question":"Как менялась прибыль?"}
```

Также доступны `GET /health`, `GET /ready` и Swagger UI `/docs`.

## Локальный запуск без Docker

```bash
source /Users/loginplease/anaconda3/etc/profile.d/conda.sh
conda activate alpha_hackathon
python -m pip install -e ".[dev]"
cp .env.example .env
```

В `.env` нужно вручную добавить `OPENROUTER_API_KEY`. Затем в двух терминалах:

```bash
python -m counterparty_verification.mcp_server
```

```bash
uvicorn counterparty_verification.api:app --reload
```

Проверка:

```bash
pytest -q
```

Docker-файлы подготовлены для другого устройства, но на текущем ноутбуке Docker
не установлен и запускать его здесь не нужно.

## Подключение будущей PostgreSQL

Схема состоит из `company_reports`, `structure_items`, `financial_reports`,
`risk_factors`, `arbitration`, `legal_events` и `procurements`. Имена колонок и
ключи перечислены в `input_data_columns.md`. Дочерние таблицы связаны с
`company_reports` составным ключом `(report_id, company_inn)`. Репозиторий
выбирает последнюю версию отчёта по `report_date`, затем загружает связанные
строки всех шести аналитических разделов. После готовности БД:

1. загрузить карточки в эту таблицу;
2. задать `DATABASE_URL`;
3. установить `REPOSITORY_BACKEND=postgres`;
4. добавить и применить Alembic-миграцию;
5. заменить in-memory session store на PostgreSQL/Redis, если API будет запущен
   в нескольких экземплярах.

Интерфейс репозитория и API менять для этого не требуется.

## Что проверено и что осталось

Проверены unit/API-тесты, компиляция модулей, установка зависимостей и реальный
HTTP round-trip к FastMCP. Тесты не расходуют токены OpenRouter.

Для следующего этапа нужны настоящий набор карточек и API-ключ. После их
появления необходимо провести интеграционные тесты выбранной модели, настроить
пороговые значения риска с бизнес-экспертами и добавить персистентное хранение
диалогов. Веб-интерфейс в текущий backend-MVP не входит.
