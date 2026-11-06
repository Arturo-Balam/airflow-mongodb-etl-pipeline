# Official Airflow image plus the Python packages the DAGs need (see requirements.txt).
FROM apache/airflow:2.10.5

COPY requirements.txt /tmp/requirements.txt
# Pinning apache-airflow keeps pip from upgrading Airflow's own dependencies.
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /tmp/requirements.txt
