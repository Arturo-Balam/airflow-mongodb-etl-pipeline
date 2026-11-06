#!/usr/bin/env bash
# Creates .env from .env.example and fills in generated secrets.
# Never overwrites an existing .env, so it is safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p logs

if [[ -f .env ]]; then
  echo ".env already exists, nothing to do."
  exit 0
fi

cp .env.example .env
fernet=$(python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")

sed -i "s|^AIRFLOW_UID=.*|AIRFLOW_UID=$(id -u)|" .env
sed -i "s|^AIRFLOW_SECRET_KEY=.*|AIRFLOW_SECRET_KEY=$(openssl rand -hex 32)|" .env
sed -i "s|^AIRFLOW_FERNET_KEY=.*|AIRFLOW_FERNET_KEY=${fernet}|" .env
sed -i "s|^MONGO_ROOT_PASSWORD=.*|MONGO_ROOT_PASSWORD=$(openssl rand -hex 16)|" .env
sed -i "s|^MONGO_APP_PASSWORD=.*|MONGO_APP_PASSWORD=$(openssl rand -hex 16)|" .env

echo ".env created. Airflow login: admin / admin (local use only)."
echo "Next: add your Banxico token to .env (BANXICO_TOKEN=...), see the README."
