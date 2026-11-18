#!/usr/bin/env bash
# Encrypted backup of the whole application database (marks, results, signed runs, proof files and
# the audit log all live in it). Writes BACKUP_DIR/attainment-<UTC time>.dump.enc and a .sha256
# file, then deletes all but the newest BACKUP_KEEP backups (default 14).
#
#   BACKUP_PASSPHRASE=... scripts/ops/backup.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
# shellcheck source=scripts/ops/common.sh
. scripts/ops/common.sh
need_passphrase

keep=${BACKUP_KEEP:-14}
mkdir -p "$BACKUP_DIR"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
out="$BACKUP_DIR/attainment-$stamp.dump.enc"

cleanup() { [ "${ok:-0}" = 1 ] || rm -f "$out"; }
trap cleanup EXIT

docker exec "$(db_container)" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl \
    | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:BACKUP_PASSPHRASE -out "$out"
[ -s "$out" ] || die "the backup file is empty"
(cd "$BACKUP_DIR" && sha256sum "$(basename "$out")" > "$(basename "$out").sha256")
ok=1

# keep the newest $keep backups
# shellcheck disable=SC2012
ls -1t "$BACKUP_DIR"/attainment-*.dump.enc 2>/dev/null | tail -n +"$((keep + 1))" | while read -r old; do
    rm -f "$old" "$old.sha256"
done
echo "$out"
