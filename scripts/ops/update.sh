#!/usr/bin/env bash
# Update a running installation: back up, build, migrate, restart, check health. If the health
# check fails the previous image and the backed-up database are put back.
#
#   BACKUP_PASSPHRASE=... scripts/ops/update.sh
#
# Run it from the checkout that holds docker-compose.yml, after `git pull` (or after checking out
# the tag to install). COMPOSE_FILES may add the production file:
#   COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml"
set -euo pipefail
cd "$(dirname "$0")/../.."
# shellcheck source=scripts/ops/common.sh
. scripts/ops/common.sh
need_passphrase

compose() {
    # shellcheck disable=SC2086
    docker compose $COMPOSE_FILES "$@"
}

health() {
    for _ in $(seq 1 30); do
        if compose exec -T app python -c \
            "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status == 200 else 1)" \
            >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    return 1
}

echo "1/5 backing up"
backup=$(scripts/ops/backup.sh)
previous_image=$(compose images -q app 2>/dev/null | head -n 1 || true)
if [ -n "$previous_image" ]; then docker tag "$previous_image" attainment:previous; fi

echo "2/5 building"
compose build

echo "3/5 migrating"
if ! compose run --rm migrate; then
    echo "migration failed: restoring the backup" >&2
    scripts/ops/restore.sh "$backup" "$POSTGRES_DB"
    exit 1
fi

echo "4/5 restarting"
compose up -d app caddy

echo "5/5 health check"
if health; then
    echo "updated; backup kept at $backup"
    exit 0
fi

echo "the health check failed: rolling back" >&2
compose stop app
if docker image inspect attainment:previous >/dev/null 2>&1; then
    docker tag attainment:previous "$(compose config --images app | head -n 1)"
fi
scripts/ops/restore.sh "$backup" "$POSTGRES_DB"
compose up -d app caddy
die "the update was rolled back; the backup is $backup"
