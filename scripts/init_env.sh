#!/usr/bin/env bash
# Creates .env from .env.example and fills in generated secrets.
# Never overwrites an existing .env, so it is safe to re-run.
# Works on Linux, WSL and Git Bash for Windows (needs bash, sed and openssl only).
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p logs

if [[ -f .env ]]; then
  echo ".env already exists, nothing to do."
  exit 0
fi

case "$(uname -s)" in
  MINGW* | MSYS* | CYGWIN*) airflow_uid=50000 ;;  # Git Bash: id -u is not a real Linux uid
  *) airflow_uid=$(id -u) ;;
esac
# A Fernet key is 32 random bytes in URL-safe base64.
fernet=$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n')

cp .env.example .env
sed -i "s|^AIRFLOW_UID=.*|AIRFLOW_UID=${airflow_uid}|" .env
sed -i "s|^AIRFLOW_SECRET_KEY=.*|AIRFLOW_SECRET_KEY=$(openssl rand -hex 32)|" .env
sed -i "s|^AIRFLOW_FERNET_KEY=.*|AIRFLOW_FERNET_KEY=${fernet}|" .env
sed -i "s|^MONGO_ROOT_PASSWORD=.*|MONGO_ROOT_PASSWORD=$(openssl rand -hex 16)|" .env
sed -i "s|^MONGO_APP_PASSWORD=.*|MONGO_APP_PASSWORD=$(openssl rand -hex 16)|" .env

echo ".env created. Airflow login: admin / admin (local use only)."
echo "Next: add your Banxico token to .env (BANXICO_TOKEN=...), see the README."
