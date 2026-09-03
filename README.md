# Business Counterparty Verification

MVP для хакатона AI Talent Hub: FastAPI-сервис получает ИНН, извлекает одну
карточку контрагента, запускает шесть MCP-анализаторов и формирует итоговое
summary. Уточняющие ответы строятся только по снимку этой карточки.
C
## Архитектура

- `counterparty_verification.api` — HTTP API;
- `counterparty_verification.mcp_server` — отдельный FastMCP-сервис;
- Pydantic AI + OpenRouter — специалисты, итоговый evaluator и Q&A;
- JSON-репозиторий — временная замена PostgreSQL;
- SQLAlchemy-репозиторий для нормализованных таблиц уже определён и включается
  через настройку.

MCP-инструменты отвечают за общую информацию, структуру, юридические и
репутационные риски, финансы и госзакупки. Все разделы запускаются параллельно.
Без ключа OpenRouter анализ остаётся работоспособным в детерминированном режиме,
а диалоговый endpoint сообщает, что модель не настроена.

## Установка

```bash
source /Users/loginplease/anaconda3/etc/profile.d/conda.sh
conda activate alpha_hackathon
python -m pip install -e ".[dev]"
cp .env.example .env
```

Заполните `OPENROUTER_API_KEY` в `.env`. Модель меняется через
`OPENROUTER_MODEL`.

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

## Запуск в Docker

```bash
docker compose up --build
```

Будущий PostgreSQL запускается отдельно:

```bash
docker compose --profile database up -d postgres
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
