# Airflow + MongoDB + Streamlit Batch ETL Pipeline

Batch ETL pipeline orchestrated with Apache Airflow. It ingests data from three public APIs, stores raw and processed data in MongoDB, and shows the results in a Streamlit dashboard. Everything runs locally with Docker Compose.

Status: work in progress. The infrastructure is ready, the pipeline itself is being built step by step (see the checklist at the bottom).

## Services

| Service | Technology | Port | Purpose |
|---|---|---|---|
| airflow-webserver | Apache Airflow 2.10.5 | 8080 | DAG scheduling and monitoring UI |
| airflow-scheduler | Apache Airflow 2.10.5 | internal | Runs the DAGs |
| airflow-postgres | PostgreSQL 16 | internal | Airflow metadata only (DAG state, logs, task history) |
| mongodb | MongoDB 7.0 | 27017 (localhost only) | Pipeline data: `raw_<source>` and `processed_<source>` |
| streamlit | Streamlit | 8501 | Dashboard on top of the processed data |

PostgreSQL never stores pipeline data. MongoDB never stores Airflow metadata.

## Quick start (Linux)

Requirements: Docker Engine with the Compose plugin, and your user in the `docker` group.

```bash
bash scripts/init_env.sh          # creates .env with generated secrets
docker compose up --build -d      # first build takes a few minutes
docker compose ps                 # wait until everything is healthy
```

- Airflow UI: http://localhost:8080 (user `admin`, password `admin`)
- Streamlit dashboard: http://localhost:8501
- MongoDB shell: `mongosh "mongodb://pipeline_app:<MONGO_APP_PASSWORD>@localhost:27017/pipeline_db?authSource=pipeline_db"` (the password is in `.env`)

## Check that the stack works

1. Open the Airflow UI and trigger the `smoke_test_mongo` DAG, or run
   `docker compose exec airflow-scheduler airflow dags trigger smoke_test_mongo`.
2. Both tasks should turn green. Task logs: Airflow UI, DAG run, task, Logs. From the terminal:
   `docker compose logs airflow-scheduler --tail 50`.
3. Reload the Streamlit dashboard. The collections table should list `smoke_test` with 1 document.

## Stopping and resetting

```bash
docker compose down        # stop, keep the data
docker compose down -v     # stop and delete all data (Postgres and MongoDB)
```

The MongoDB user is created by `docker/mongo/init-mongo.sh` the first time the data volume is created. If you change the MongoDB credentials in `.env`, run `docker compose down -v` so the init script runs again.

If `airflow-init` fails with a permissions error, check that `AIRFLOW_UID` in `.env` matches the output of `id -u`.

## Project layout

```
dags/                 Airflow DAGs and task logic
  utils/              Shared helpers (MongoDB connection and writes)
streamlit_app/        Dashboard (own Dockerfile)
docker/               Airflow image and MongoDB init script
scripts/init_env.sh   Generates .env
tests/                Unit tests (pytest)
docker-compose.yml    All services
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
- [ ] API selection and ingestion tasks (raw_<source>)
- [ ] Transformations (standardization, cleaning, enrichment) into processed_<source>
- [ ] Main DAG (`dags/main_pipeline.py`) with XCom usage
- [ ] Streamlit dashboard with filters and charts
- [ ] Tests for transformations, CI workflow
- [ ] Final README (APIs used, XCom explanation, screenshots)
