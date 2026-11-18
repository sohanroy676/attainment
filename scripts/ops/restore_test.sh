#!/usr/bin/env bash
# The scheduled restore test: restore the newest backup into a scratch database, re-apply the
# application role's privileges, check the audit chain of every college, then drop the scratch
# database. A backup nobody has restored is not a backup. Exit status 1 means it failed.
#
#   BACKUP_PASSPHRASE=... scripts/ops/restore_test.sh [backup file]
set -euo pipefail
cd "$(dirname "$0")/../.."
# shellcheck source=scripts/ops/common.sh
. scripts/ops/common.sh
need_passphrase

file=${1:-$(ls -1t "$BACKUP_DIR"/attainment-*.dump.enc 2>/dev/null | head -n 1)}
[ -n "$file" ] || die "there is no backup to test"
scratch=attainment_restore_test

scripts/ops/restore.sh "$file" "$scratch"
trap 'psql_super postgres -c "DROP DATABASE IF EXISTS \"$scratch\" WITH (FORCE)" >/dev/null' EXIT

# shellcheck disable=SC2086
docker compose $COMPOSE_FILES run --rm -e POSTGRES_DB="$scratch" migrate
# shellcheck disable=SC2086
docker compose $COMPOSE_FILES --profile ops run --rm -e POSTGRES_DB="$scratch" ops \
    python manage.py verify_audit --all
echo "restore test passed: $file"
