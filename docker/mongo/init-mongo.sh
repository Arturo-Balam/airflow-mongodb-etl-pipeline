#!/bin/bash
# Runs once, the first time the mongo-data volume is created.
# Creates a least-privilege user for the pipeline and dashboard (readWrite on one database).
# To run it again: docker compose down -v (this deletes the stored data).
set -e

mongosh --quiet \
  -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" \
  --authenticationDatabase admin \
  --eval "
    const appDb = db.getSiblingDB('${MONGO_DB}');
    appDb.createUser({
      user: '${MONGO_APP_USER}',
      pwd: '${MONGO_APP_PASSWORD}',
      roles: [{ role: 'readWrite', db: '${MONGO_DB}' }]
    });
  "
