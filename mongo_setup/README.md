# MongoDB setup for counterparty reports

This setup imports the source snapshot without changing its document structure:

`../data/raw/contractors_audit.snapshot.json`

One array element becomes one document in `counterparties.reports`. MongoDB
Extended JSON values such as `$date` are stored using their BSON equivalents;
the business data itself is not recalculated, normalized, or validated.

## Start

```bash
cd mongo_setup
cp .env.example .env
```

Set a non-default password in `.env`, then run:

```bash
docker compose up -d
```

The `mongo` service keeps the database in the `mongo_data` volume. The
`mongo-seed` service waits for MongoDB, creates indexes, imports all 100 source
documents, and exits successfully.

## Verify

```bash
docker compose ps -a
docker compose exec mongo mongosh \
  --username contractors_admin \
  --password YOUR_PASSWORD \
  --authenticationDatabase admin \
  counterparties \
  --eval 'db.reports.countDocuments({})'
```

Expected result: `100`.

Find the latest report by INN:

```javascript
db.reports.findOne(
  { "report.baseInfo.inn": "1684017097" },
  {},
  { sort: { "report.reportDate": -1 } }
)
```

## Re-import

The seed uses source `_id` values as upsert keys, so it can be run repeatedly:

```bash
docker compose run --rm mongo-seed
```

## Stop

Keep the data:

```bash
docker compose down
```

Delete the local MongoDB volume as well:

```bash
docker compose down -v
```

The last command is destructive and should only be used when a clean local
database is required.
