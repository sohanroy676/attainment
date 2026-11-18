#!/usr/bin/env bash
# Shared settings for the operations scripts. Source this file; do not run it.
#
# Variables (all can come from .env or the shell):
#   DB_CONTAINER      the PostgreSQL container; default is the compose service "db"
#   POSTGRES_USER     database superuser (default postgres)
#   POSTGRES_DB       the application database (default attainment)
#   DB_OWNER_USER     the owner role (default attainment_owner)
#   BACKUP_DIR        where backups are kept (default ./backups)
#   BACKUP_PASSPHRASE the encryption passphrase (never stored next to the backups)

: "${POSTGRES_USER:=postgres}"
: "${POSTGRES_DB:=attainment}"
: "${DB_OWNER_USER:=attainment_owner}"
: "${BACKUP_DIR:=./backups}"
: "${COMPOSE_FILES:=-f docker-compose.yml}"

db_container() {
    if [ -n "${DB_CONTAINER:-}" ]; then
        printf '%s' "$DB_CONTAINER"
    else
        # shellcheck disable=SC2086
        docker compose $COMPOSE_FILES ps -q db
    fi
}

# Run psql inside the database container as the superuser, against database $1.
psql_super() {
    local database=$1
    shift
    docker exec -i "$(db_container)" psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$database" "$@"
}

die() {
    echo "error: $*" >&2
    exit 1
}

need_passphrase() {
    [ -n "${BACKUP_PASSPHRASE:-}" ] || die "set BACKUP_PASSPHRASE (the backup encryption key)"
}
