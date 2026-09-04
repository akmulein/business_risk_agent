# PostgreSQL setup for contractor reports

## 1. Create `.env`

```bash
cp .env.example .env
```

Edit `.env` if desired. For local development the defaults are enough after replacing `change_me` with a password.

## 2. Start PostgreSQL

```bash
docker compose up -d
```

Check that it is healthy:

```bash
docker compose ps
```

On the first startup PostgreSQL automatically executes `db/schema.sql` and creates all 7 tables and indexes.

> `schema.sql` from `/docker-entrypoint-initdb.d` runs only when the database volume is initialized for the first time. If you change the schema during development and want a completely fresh database:
>
> ```bash
> docker compose down -v
> docker compose up -d
> ```

## 3. Create Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 4. Load parsed CSV files

The 7 CSV files should be in `data/processed/`:

- company_reports.csv
- structure_items.csv
- financial_reports.csv
- risk_factors.csv
- arbitration.csv
- legal_events.csv
- procurements.csv

Run:

```bash
python src/load_db.py --data-dir data/processed
```

By default the loader clears the existing tables before loading. To append new report snapshots instead:

```bash
python src/load_db.py --data-dir data/processed --append
```

## 5. Verify the database

Open psql inside the container:

```bash
docker exec -it contractor-postgres psql -U contractors_user -d contractors
```

Useful checks:

```sql
SELECT COUNT(*) FROM company_reports;
SELECT COUNT(*) FROM structure_items;
SELECT COUNT(*) FROM financial_reports;
SELECT COUNT(*) FROM risk_factors;
SELECT COUNT(*) FROM arbitration;
SELECT COUNT(*) FROM legal_events;
SELECT COUNT(*) FROM procurements;
```

For the current dataset the expected row counts are:

```text
company_reports       100
structure_items      2822
financial_reports     194
risk_factors         1643
arbitration            351
legal_events          4230
procurements            16
```

Example future tool query:

```sql
SELECT year, proceeds, profit, total_assets, accounts_payable
FROM financial_reports
WHERE company_inn = '1684017097'
ORDER BY year DESC;
```
