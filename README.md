# Airflow + MongoDB + Streamlit Batch ETL Pipeline

Batch ETL pipeline orchestrated with Apache Airflow. It ingests data from three public APIs, stores raw and processed data in MongoDB, and shows the results in a Streamlit dashboard. Everything runs locally with Docker Compose.

Theme: a small Mexico monitor with the daily weather in Merida, the USD/MXN exchange rate and recent earthquakes.

Status: work in progress. Ingestion, transformations and the load step are done, the dashboard is being built next (see the checklist at the bottom).

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

## How the pipeline works

`main_pipeline` has 7 tasks: three ingestion tasks run in parallel, each one feeds its own transform task, and a final load task waits for all three transforms.

```
ingest_weather     >> transform_weather     \
ingest_fx          >> transform_fx           >> load
ingest_earthquakes >> transform_earthquakes /
```

**Ingestion**
- Each run fetches the day it covers plus the 6 days before it (`PIPELINE_LOOKBACK_DAYS` in `.env`, default 7). The overlap picks up late or revised data.
- The response is saved untouched inside a wrapper document in `raw_<source>`: source, fetch time, window, request parameters, record count and the original payload.
- The document `_id` is built from the source and the window, so re-running a day replaces its document instead of adding a duplicate (idempotent).
- The Banxico token travels in a request header, never in the URL, the logs or the stored request.

**Transformation** (reusable logic in `dags/utils/transform_helpers.py`)
- Standardization: snake_case names with units in the name, ISO 8601 dates and timestamps, Celsius, millimetres and km/h (other units are converted, unknown units fail the task), percentages as decimals.
- Cleaning: records missing a critical field are dropped, impossible values (for example a 95 C air temperature or an invalid date) are dropped as corrupted, duplicates are removed keeping the freshest. Non critical gaps are imputed and counted.
- Enrichment: at least two derived fields per dataset (see the data model).
- Each processed document uses a natural key as `_id` (a date, or the USGS event id), so overlapping windows overwrite the same documents instead of duplicating them. The first day of each exchange rate window takes its previous rate from MongoDB, so its daily change is never lost.

**Load**
- Builds `processed_daily_overview`, one document per date joining the three sources.
- Writes one audit document per DAG run to `pipeline_runs`.
- Creates the indexes if missing and deletes raw documents older than 30 days.

**XCom**: every task passes a small summary to the next one, never the data itself. Ingestion returns the raw document id and record count, transform reads the raw document by that id and returns counts of what it kept, dropped and imputed, and load collects the three summaries into the run audit. You can see them in the Airflow UI under each task, XCom tab.

## Data model

| Collection | Key (`_id`) | Main fields |
|---|---|---|
| `raw_weather`, `raw_fx`, `raw_earthquakes` | `<source>:<window start>:<window end>` | `source`, `fetched_at`, `window`, `request`, `record_count`, `payload` |
| `processed_weather` | date | `temp_max_c`, `temp_min_c`, `precipitation_mm`, `wind_speed_max_kmh`, `weather_description`; derived: `temp_mean_c`, `temp_range_c`, `heat_category`, `is_extreme_heat`, `is_rainy_day` |
| `processed_fx` | date | `usd_mxn_rate`; derived: `usd_mxn_change`, `usd_mxn_change_pct` (decimal), `peso_trend`, `is_large_move` |
| `processed_earthquakes` | USGS event id | `event_time`, `event_date`, `magnitude`, `latitude`, `longitude`, `depth_km`, `place`; derived: `magnitude_class`, `depth_class`, `distance_to_merida_km`, `is_near_merida`, `is_significant` |
| `processed_daily_overview` | date | weather, exchange rate and earthquake summary per date (`earthquake_count`, `max_magnitude`, ...) |
| `pipeline_runs` | DAG run id | `finished_at`, `window`, `tasks` (summary of each task), `overview_rows`, `raw_deleted` |

Look at the processed data:

```bash
docker compose exec mongodb bash -c 'mongosh -u "$MONGO_APP_USER" -p "$MONGO_APP_PASSWORD" --authenticationDatabase "$MONGO_DB" "$MONGO_DB" --quiet --eval "printjson(db.processed_daily_overview.find().sort({date: -1}).limit(3).toArray())"'
```

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
  transform_*.py            One module per dataset (clean, standardize, enrich)
  load_mongo.py             Daily overview, run audit, indexes and raw cleanup
  utils/                    Shared helpers (MongoDB, HTTP and run window, transform helpers)
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
- [x] Transformations (standardization, cleaning, enrichment) into processed_<source>
- [x] Transform and load tasks added to `main_pipeline`
- [ ] Streamlit dashboard with filters and charts
- [ ] CI workflow, final README (XCom explanation, screenshots)
