#!/bin/sh
# Creates the two application database roles (design 13.1). Runs once on a fresh PostgreSQL
# volume (docker-entrypoint-initdb.d) and in CI. Needs these variables in the environment:
#   POSTGRES_USER (superuser), POSTGRES_DB, DB_OWNER_USER, DB_OWNER_PASSWORD,
#   DB_APP_USER, DB_APP_PASSWORD. For CI also PGHOST, PGPORT and PGPASSWORD.
#
#   owner = owns the tables and runs migrations. May create databases (test runs only).
#   app   = serves requests. Not the owner, no BYPASSRLS, no superuser, cannot create anything.
set -eu

: "${POSTGRES_USER:?}" "${POSTGRES_DB:?}"
: "${DB_OWNER_USER:?}" "${DB_OWNER_PASSWORD:?}" "${DB_APP_USER:?}" "${DB_APP_PASSWORD:?}"

psql -v ON_ERROR_STOP=1 \
    -v owner="$DB_OWNER_USER" -v owner_pw="$DB_OWNER_PASSWORD" \
    -v app="$DB_APP_USER" -v app_pw="$DB_APP_PASSWORD" \
    -v db="$POSTGRES_DB" \
    --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
CREATE ROLE :"owner" LOGIN CREATEDB NOSUPERUSER NOCREATEROLE NOBYPASSRLS PASSWORD :'owner_pw';
CREATE ROLE :"app" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'app_pw';

ALTER DATABASE :"db" OWNER TO :"owner";
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO :"app";

ALTER SCHEMA public OWNER TO :"owner";
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"app";
SQL
