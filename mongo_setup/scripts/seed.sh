#!/bin/sh
set -eu

: "${MONGO_ROOT_USERNAME:?MONGO_ROOT_USERNAME is required}"
: "${MONGO_ROOT_PASSWORD:?MONGO_ROOT_PASSWORD is required}"
: "${MONGO_DATABASE:?MONGO_DATABASE is required}"
: "${MONGO_COLLECTION:?MONGO_COLLECTION is required}"
: "${MONGO_HOST:?MONGO_HOST is required}"
: "${MONGO_INTERNAL_PORT:?MONGO_INTERNAL_PORT is required}"
: "${MONGO_SEED_FILE:?MONGO_SEED_FILE is required}"

if [ ! -r "${MONGO_SEED_FILE}" ]; then
  echo "Seed file is not readable: ${MONGO_SEED_FILE}" >&2
  exit 1
fi

mongo_auth_args="--host ${MONGO_HOST} --port ${MONGO_INTERNAL_PORT} --username ${MONGO_ROOT_USERNAME} --password ${MONGO_ROOT_PASSWORD} --authenticationDatabase admin"

# Index creation is idempotent and also protects the immutable snapshot key.
# shellcheck disable=SC2086
mongosh ${mongo_auth_args} --quiet /seed/scripts/create_indexes.js

# Upsert by the source _id makes repeated local starts safe while preserving
# every field from the supplied JSON document.
# shellcheck disable=SC2086
mongoimport ${mongo_auth_args} \
  --db "${MONGO_DATABASE}" \
  --collection "${MONGO_COLLECTION}" \
  --file "${MONGO_SEED_FILE}" \
  --jsonArray \
  --mode upsert \
  --upsertFields _id

# shellcheck disable=SC2086
document_count="$(mongosh ${mongo_auth_args} --quiet --eval \
  'db.getSiblingDB(process.env.MONGO_DATABASE).getCollection(process.env.MONGO_COLLECTION).countDocuments({})')"

echo "MongoDB seed completed: ${document_count} documents in ${MONGO_DATABASE}.${MONGO_COLLECTION}"
