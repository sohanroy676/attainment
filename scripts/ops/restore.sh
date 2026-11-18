#!/usr/bin/env bash
# Restore a backup into a database. By default into a scratch database (attainment_restore) so
# nothing live is touched; to replace the live database pass its name as the second argument
# and stop the app first.
#
#   BACKUP_PASSPHRASE=... scripts/ops/restore.sh backups/attainment-<time>.dump.enc [database]
#
# A wrong passphrase or a damaged file stops before the target database is touched.
# After restoring the live database run `docker compose run --rm migrate` so the application
# role's privileges are applied again.
set -euo pipefail
cd "$(dirname "$0")/../.."
# shellcheck source=scripts/ops/common.sh
. scripts/ops/common.sh
need_passphrase

file=${1:?usage: restore.sh <backup file> [target database]}
target=${2:-attainment_restore}
[ -f "$file" ] || die "no such file: $file"
case "$target" in *[!a-zA-Z0-9_]*) die "the database name may hold letters, digits and _ only" ;; esac

if [ -f "$file.sha256" ]; then
    (cd "$(dirname "$file")" && sha256sum --check --status "$(basename "$file").sha256") \
        || die "the checksum does not match: the backup is damaged"
fi

plain=$(mktemp)
trap 'rm -f "$plain"' EXIT
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE -in "$file" -out "$plain" 2>/dev/null \
    || die "could not decrypt the backup (wrong passphrase?)"
[ "$(head -c 5 "$plain")" = "PGDMP" ] || die "the decrypted file is not a database dump (wrong passphrase?)"

psql_super postgres -c "DROP DATABASE IF EXISTS \"$target\" WITH (FORCE)" \
    -c "CREATE DATABASE \"$target\" OWNER \"$DB_OWNER_USER\""
docker exec -i "$(db_container)" pg_restore -U "$POSTGRES_USER" -d "$target" \
    --no-owner --no-acl --role="$DB_OWNER_USER" --exit-on-error < "$plain"
echo "restored into $target"
