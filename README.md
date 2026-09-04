# Business Counterparty Verification

MVP для хакатона AI Talent Hub: FastAPI-сервис получает ИНН, извлекает одну
карточку контрагента, запускает шесть MCP-анализаторов и формирует итоговое
summary. Уточняющие ответы строятся только по снимку этой карточки.

## Архитектура

- `counterparty_verification.api` — HTTP API;
- `counterparty_verification.mcp_server` — отдельный FastMCP-сервис;
- Pydantic AI + OpenRouter — специалисты, итоговый evaluator и Q&A;
- MongoDB: `reports` хранит исходные отчёты, `counterparty_cards` — готовые
  карточки пайплайна;
- JSON и PostgreSQL остаются доступными как альтернативные репозитории.

MCP-инструменты отвечают за общую информацию, структуру, юридические и
репутационные риски, финансы и госзакупки. Все разделы запускаются параллельно.
Без ключа OpenRouter анализ остаётся работоспособным в детерминированном режиме,
а диалоговый endpoint сообщает, что модель не настроена.

## Установка

Для воспроизводимого запуска нужен только Docker. Создайте локальную
конфигурацию и замените `MONGO_ROOT_PASSWORD=change_me`:

```bash
cp .env.example .env
nano .env
```

`OPENROUTER_API_KEY` можно оставить пустым: тогда анализ будет
детерминированным, без LLM.

## Локальный запуск

В первом терминале:

```bash
conda activate alpha_hackathon
python -m counterparty_verification.mcp_server
```

Во втором:

```bash
conda activate alpha_hackathon
uvicorn counterparty_verification.api:app --reload
```

Swagger UI: <http://localhost:8000/docs>.

Для локального запуска без Docker установите проект через
`python -m pip install -e ".[dev]"` и используйте:

```env
REPOSITORY_BACKEND=mongo
MONGODB_URL=mongodb://contractors_admin:<password>@localhost:27017/counterparties?authSource=admin
MONGODB_DATABASE=counterparties
MONGODB_COLLECTION=counterparty_cards
```

## Запуск в Docker

```bash
docker compose up --build
```

Команда поднимает MongoDB, создаёт `reports` и `counterparty_cards`, затем
запускает MCP и API. Swagger UI: <http://localhost:8000/docs>.

Остановить сервисы без удаления данных:

```bash
docker compose down
```

## API

Запустить анализ тестовой карточки:

```bash
curl -X POST http://localhost:8000/api/v1/analyses \
  -H 'Content-Type: application/json' \
  -d '{"inn":"7707083893"}'
```

В ответе возвращаются `analysis_id`, итоговый `summary`, уровень риска и
результаты всех глав. Задать уточняющий вопрос:

```bash
curl -X POST http://localhost:8000/api/v1/analyses/ANALYSIS_ID/questions \
  -H 'Content-Type: application/json' \
  -d '{"question":"Как менялась прибыль?"}'
```

Тестовая карточка в `data/counterparties.json` содержит синтетические значения и
не является реальным отчётом об указанной организации.

## Проверка

```bash
pytest
```

Тесты не обращаются к OpenRouter и не требуют API-ключа.
