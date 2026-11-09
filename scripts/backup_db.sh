#!/usr/bin/env bash
# Database backup into backups/cards-YYYY-MM-DD.sql.gz (keeps the last 14).
# Add to cron:  0 3 * * *  bash /opt/kartochki/scripts/backup_db.sh
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
F="backups/cards-$(date +%F).sql.gz"
docker compose --env-file .env exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$F"
ls -1t backups/cards-*.sql.gz | tail -n +15 | xargs -r rm --
echo "saved $F"
