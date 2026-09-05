# Business Counterparty Verification

MVP для хакатона AI Talent Hub: FastAPI-сервис получает один или несколько ИНН
(до 10 за запрос), извлекает карточки контрагентов, запускает шесть
MCP-анализаторов и формирует отдельное итоговое summary для каждой компании.
После анализа пользователь может задавать уточняющие вопросы в общем чате по
одной, нескольким или всем найденным компаниям. Ответы строятся только по данным
их отчётов.

## Архитектура

- `counterparty_verification.api` — HTTP API;
- `counterparty_verification.mcp_server` — отдельный FastMCP-сервис;
- `frontend` — React-интерфейс на Core Components с отчётами, графиками и
  общим AI-чатом;
- Pydantic AI + OpenRouter — специалисты, итоговый evaluator и Q&A;
- MongoDB: `reports` хранит исходные отчёты, `counterparty_cards` — готовые
  карточки пайплайна, `chat_sessions` — сессии и историю чатов;
- JSON и PostgreSQL остаются доступными как альтернативные репозитории.

MCP-инструменты отвечают за общую информацию, структуру, юридические и
репутационные риски, финансы и госзакупки. Все разделы запускаются параллельно.
Без ключа OpenRouter анализ остаётся работоспособным в детерминированном режиме,
а диалоговый endpoint сообщает, что модель не настроена. Все LLM-агенты
используют одну модель из `OPENROUTER_MODEL`. Цвета светофора рассчитываются
детерминированно и не изменяются моделью.

## Установка

Для воспроизводимого запуска нужен только Docker. Создайте локальную
конфигурацию и замените `MONGO_ROOT_PASSWORD=change_me`:

```bash
cp .env.example .env
nano .env
```

`OPENROUTER_API_KEY` можно оставить пустым: тогда анализ будет
детерминированным, без LLM, а чат будет недоступен. Для работы чата укажите
ключ и модель:

```env
OPENROUTER_API_KEY=<ваш ключ>
OPENROUTER_MODEL=~deepseek/deepseek-v4-flash-latest
```

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
запускает MCP, API и frontend. Коллекция `chat_sessions` и TTL-индекс для
автоматического удаления истёкших сессий создаются при запуске API.
Python-зависимости Docker-образов зафиксированы в `requirements.lock.txt`.

Frontend: <http://localhost:3000>. Swagger UI: <http://localhost:8000/docs>.

Интерфейс позволяет найти и последовательно добавить до 10 компаний, после
чего запустить один общий анализ. Полные отчёты раскрываются внутри карточек,
а чат использует общий `chat_id` результатов.

Если ключ OpenRouter был добавлен после запуска, пересоздайте только API:

```bash
docker compose up -d --force-recreate --no-deps api
```

Остановить сервисы без удаления данных:

```bash
docker compose down
```

## API

Запустить анализ одной или нескольких карточек:

```bash
curl -X POST http://localhost:8000/api/v1/analyses \
  -H 'Content-Type: application/json' \
  -d '{"inns":["1684017097","772377037026"]}'
```

Поле `inns` принимает от 1 до 10 ИНН. Поддерживаются десятизначные
ИНН организаций и двенадцатизначные ИНН индивидуальных предпринимателей.
Результаты возвращаются в порядке запроса. Для каждого ИНН указывается статус
`success`, `not_found` или `error`, поэтому отсутствие одной компании не
прерывает обработку остальных.

В ответе верхнего уровня возвращается общий `chat_id`, а в `results` — отдельные
`analysis_id`, итоговые `summary`, уровни риска и результаты всех глав:

```json
{
  "chat_id": "CHAT_ID",
  "results": [
    {
      "inn": "1684017097",
      "status": "success",
      "analysis": {
        "analysis_id": "ANALYSIS_ID",
        "summary": "...",
        "risk_level": "LOW",
        "chapters": []
      }
    }
  ]
}
```

Отправить вопрос в общий чат по найденным компаниям:

```bash
curl -X POST http://localhost:8000/api/v1/chats/CHAT_ID/messages \
  -H 'Content-Type: application/json' \
  -d '{"message":"Кто руководитель ТЕХПРОФ?"}'
```

Следующие вопросы отправляются с тем же `chat_id`. Можно спрашивать об одной
компании, сравнивать несколько компаний или обращаться сразу ко всем компаниям
чата. Ответ содержит краткий `answer` и массив `sources` с проверенными полями
исходных карточек.

Получить историю чата:

```bash
curl http://localhost:8000/api/v1/chats/CHAT_ID/messages
```

Ранее существовавший endpoint вопроса по одному `analysis_id` сохранён для
совместимости:

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
