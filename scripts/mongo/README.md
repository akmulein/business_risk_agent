# MongoDB seed scripts

Эта папка содержит скрипты, которые используются корневым `docker-compose.yml` при запуске сервиса.
Отдельно запускать MongoDB из этой директории не нужно.

## Что делает `mongo-seed`

При `docker compose up --build` сервис `mongo-seed`:

1. импортирует `data/seed/contractors_audit.snapshot.json` в коллекцию `reports`;
2. строит прикладную read-модель `counterparty_cards`;
3. создаёт индексы для быстрых запросов по ИНН и ключевым полям.

Повторный запуск безопасен: исходные отчёты импортируются через upsert по `_id`, а read-модель пересобирается заново из raw-данных.

## Коллекции

- `reports` — исходные отчёты без изменения структуры;
- `counterparty_cards` — подготовленные карточки, которые читает приложение;
- `counterparty_cards_building` — временная коллекция во время пересборки read-модели.

## Проверка локальной базы

После запуска приложения можно проверить количество документов:

```bash
docker compose exec mongo sh -lc 'mongosh --quiet   --username "$MONGO_INITDB_ROOT_USERNAME"   --password "$MONGO_INITDB_ROOT_PASSWORD"   --authenticationDatabase admin   "$MONGO_INITDB_DATABASE"   --eval "db.reports.countDocuments({})"'
```

Ожидаемый результат для текущего seed-файла: `100`.

Проверка подготовленных карточек:

```bash
docker compose exec mongo sh -lc 'mongosh --quiet   --username "$MONGO_INITDB_ROOT_USERNAME"   --password "$MONGO_INITDB_ROOT_PASSWORD"   --authenticationDatabase admin   "$MONGO_INITDB_DATABASE"   --eval "db.counterparty_cards.countDocuments({})"'
```

Ожидаемый результат: `100`.
