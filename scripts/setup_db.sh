#!/usr/bin/env bash
# Create (or recreate) the SALUS database, apply schema + logic, and seed it.
# Uses the standard libpq env vars: PGHOST, PGPORT, PGUSER, PGPASSWORD.
#   PGUSER=postgres PGPASSWORD=postgres ./scripts/setup_db.sh
set -euo pipefail
cd "$(dirname "$0")/.."

DB="${SALUS_DB:-salus}"
export PGHOST="${PGHOST:-localhost}" PGUSER="${PGUSER:-postgres}"

echo "==> (re)creating database $DB"
psql -v ON_ERROR_STOP=1 -q -d postgres -c "DROP DATABASE IF EXISTS $DB WITH (FORCE)" -c "CREATE DATABASE $DB"

echo "==> schema"
psql -v ON_ERROR_STOP=1 -q -d "$DB" -f db/01_schema.sql
echo "==> functions, triggers, views"
psql -v ON_ERROR_STOP=1 -q -d "$DB" -f db/02_functions.sql
echo "==> accounts, diary, doctor profiles"
psql -v ON_ERROR_STOP=1 -q -d "$DB" -f db/06_accounts_diary_profiles.sql
echo "==> pg_cron jobs"
if ! psql -v ON_ERROR_STOP=1 -q -d "$DB" -f db/03_cron.sql >/dev/null 2>&1; then
  echo "    pg_cron not available - skipped. The API will run the reminder jobs itself."
fi

echo "==> seed data"
export DATABASE_URL="postgresql://${PGUSER}:${PGPASSWORD:-}@${PGHOST}:${PGPORT:-5432}/${DB}"
python3 scripts/seed.py
echo "Done."
