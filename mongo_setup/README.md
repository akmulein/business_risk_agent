# MongoDB: база отчётов контрагентов

## Устройство

- Docker image: `mongo:7.0`.
- Database: `counterparties`.
- Collection: `reports`.
- Один элемент исходного JSON — один документ MongoDB.
- Источник: `../data/raw/contractors_audit.snapshot.json`.
- Данные MongoDB сохраняются в Docker volume `counterparty-mongo_mongo_data`.
- `mongo-seed` создаёт индексы и импортирует документы по исходному `_id`.

Содержание отчётов не изменяется. Extended JSON (`$date`, `$numberLong`) при
импорте преобразуется в соответствующие BSON-типы MongoDB.

## Запуск

```bash
cd mongo_setup
cp .env.example .env
nano .env
```

В `.env` замените `MONGO_ROOT_PASSWORD=change_me`, затем выполните:

```bash
docker compose pull
docker compose up -d
docker compose ps -a
docker compose logs mongo-seed
```

Ожидаемое состояние:

- `contractor-mongo` — `healthy`;
- `mongo-seed` — `Exited (0)`;
- в логах seed — `100 document(s) imported successfully`.

## Подключение

Из приложения на хосте:

```text
mongodb://contractors_admin:<password>@localhost:27017/counterparties?authSource=admin
```

Из контейнера в том же Compose/network:

```text
mongodb://contractors_admin:<password>@mongo:27017/counterparties?authSource=admin
```

Проверка количества документов:

```bash
docker compose exec mongo sh -lc 'mongosh --quiet \
  --username "$MONGO_INITDB_ROOT_USERNAME" \
  --password "$MONGO_INITDB_ROOT_PASSWORD" \
  --authenticationDatabase admin \
  "$MONGO_INITDB_DATABASE" \
  --eval "db.reports.countDocuments({})"'
```

Ожидаемый результат: `100`.
