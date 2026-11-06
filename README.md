# Airflow + MongoDB + Streamlit Batch ETL Pipeline

Batch ETL pipeline orchestrated with Apache Airflow. It ingests data from three public APIs, stores raw and processed data in MongoDB, and shows the results in a Streamlit dashboard. Everything runs locally with Docker Compose.

Theme: a small Mexico monitor with the daily weather in Merida, the USD/MXN exchange rate and recent earthquakes.

Status: work in progress. Ingestion is done, the transformations, the load step and the dashboard are being built step by step (see the checklist at the bottom).

## Services

| Service | Technology | Port | Purpose |
|---|---|---|---|
| airflow-webserver | Apache Airflow 2.10.5 | 8080 | DAG scheduling and monitoring UI |
| airflow-scheduler | Apache Airflow 2.10.5 | internal | Runs the DAGs |
| airflow-postgres | PostgreSQL 16 | internal | Airflow metadata only (DAG state, logs, task history) |
| mongodb | MongoDB 7.0 | 27017 (localhost only) | Pipeline data: `raw_<source>` and `processed_<source>` |
| streamlit | Streamlit | 8501 | Dashboard on top of the processed data |

PostgreSQL never stores pipeline data. MongoDB never stores Airflow metadata.

## APIs used

| Source | Data | Docs | Key |
|---|---|---|---|
| Open-Meteo Forecast API | Daily temperature, rain and wind for Merida | https://open-meteo.com/en/docs | None |
| Banxico SIE API | USD/MXN FIX exchange rate (series SF43718) | https://www.banxico.org.mx/SieAPIRest/service/v1/ | Free token |
| USGS Earthquake Catalog | Earthquakes (M2.5+) in a bounding box around Mexico | https://earthquake.usgs.gov/fdsnws/event/1/ | None |

Weather data by [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0). Exchange rate data from Banco de Mexico. Earthquake data from the U.S. Geological Survey.

## Quick start (Linux)

Requirements: Docker Engine with the Compose plugin, and your user in the `docker` group.

```bash
bash scripts/init_env.sh          # creates .env with generated secrets
```

Get a free Banxico token at https://www.banxico.org.mx/SieAPIRest/service/v1/token and add it to `.env` as `BANXICO_TOKEN=<your token>` (no spaces around the `=`). `.env` is gitignored, so the token stays on your machine.

```bash
docker compose up --build -d      # first build takes a few minutes
docker compose ps                 # wait until everything is healthy
```

- Airflow UI: http://localhost:8080 (user `admin`, password `admin`)
- Streamlit dashboard: http://localhost:8501
- MongoDB shell: `mongosh "mongodb://pipeline_app:<MONGO_APP_PASSWORD>@localhost:27017/pipeline_db?authSource=pipeline_db"` (the password is in `.env`)

## Run the pipeline

The `main_pipeline` DAG runs daily at 08:00 UTC (02:00 in Merida). To run it now, press the play button next to `main_pipeline` in the Airflow UI, or:

```bash
docker compose exec airflow-scheduler airflow dags trigger main_pipeline
docker compose exec airflow-scheduler airflow dags list-runs -d main_pipeline
```

Check the DAG loaded without errors (it should print "No data found"):

```bash
docker compose exec airflow-scheduler airflow dags list-import-errors
```

Task logs: Airflow UI, DAG run, task, Logs. From the terminal: `docker compose logs airflow-scheduler --tail 50`.

Inspect what was stored in MongoDB (payload hidden to keep the output short):

```bash
docker compose exec mongodb bash -c 'mongosh -u "$MONGO_APP_USER" -p "$MONGO_APP_PASSWORD" --authenticationDatabase "$MONGO_DB" "$MONGO_DB" --quiet --eval "printjson(db.raw_fx.findOne({}, {payload: 0}))"'
```

Replace `raw_fx` with `raw_weather` or `raw_earthquakes` for the other sources.

## How ingestion works

- One Airflow task per API (`ingest_weather`, `ingest_fx`, `ingest_earthquakes`), each with 2 retries.
- Each run fetches the day it covers plus the 6 days before it (`PIPELINE_LOOKBACK_DAYS` in `.env`, default 7). The overlap picks up late or revised data.
- The response is saved untouched inside a wrapper document in `raw_<source>`: source, fetch time, window, request parameters, record count and the original payload.
- The document `_id` is built from the source and the window, so re-running a day replaces its document instead of adding a duplicate (idempotent).
- Each task returns a small summary (source, collection, record count, window) through XCom, so the next tasks know what was loaded without passing the data itself.
- The Banxico token travels in a request header, never in the URL, the logs or the stored request.

## Stopping and resetting

```bash
docker compose down        # stop, keep the data
docker compose down -v     # stop and delete all data (Postgres, MongoDB and Airflow logs)
```

The MongoDB user is created by `docker/mongo/init-mongo.sh` the first time the data volume is created. If you change the MongoDB credentials in `.env`, run `docker compose down -v` so the init script runs again.

If `airflow-init` fails with a permissions error, check that `AIRFLOW_UID` in `.env` matches the output of `id -u`.

## Project layout

```
dags/
  main_pipeline.py          The DAG
  ingestion_*.py            One module per API (request, record count, raw storage)
  utils/                    Shared helpers (MongoDB connection and writes, HTTP, run window)
streamlit_app/              Dashboard (own Dockerfile)
docker/                     Airflow image and MongoDB init script
scripts/init_env.sh         Generates .env
tests/                      Unit tests (pytest)
docker-compose.yml          All services
```

Run the tests locally:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

## Build checklist

- [x] Docker Compose stack: Airflow, PostgreSQL, MongoDB, Streamlit
- [x] MongoDB helpers (`dags/utils/mongo_utils.py`) with idempotent upserts
- [x] Smoke test DAG
- [x] API ingestion tasks into raw_<source>
- [ ] Transformations (standardization, cleaning, enrichment) into processed_<source>
- [ ] Transform and load tasks added to `main_pipeline`
- [ ] Streamlit dashboard with filters and charts
- [ ] CI workflow, final README (XCom explanation, screenshots)
