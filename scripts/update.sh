#!/usr/bin/env bash
# Installs a new kartochki-server.zip in one command:
#   bash /opt/kartochki/scripts/update.sh [/root/kartochki-server.zip]
# Keeps the previous version in /opt/kartochki/.prev (rollback: bash /opt/kartochki/scripts/update.sh --rollback).
set -euo pipefail
APP=/opt/kartochki
ZIP="${1:-/root/kartochki-server.zip}"
PARTS="app static migrations tools seed scripts"
cd "$APP"

if [ "$ZIP" = "--rollback" ]; then
  [ -d .prev ] || { echo "Нет сохранённой версии"; exit 1; }
  for d in $PARTS; do [ -d ".prev/$d" ] && rm -rf "$d" && cp -r ".prev/$d" "$d"; done
  [ -f .prev/requirements.txt ] && cp .prev/requirements.txt .
  systemctl restart kartochki
  echo "✓ Вернул прошлую версию (база не откатывается)"; exit 0
fi

[ -f "$ZIP" ] || { echo "Нет архива $ZIP"; exit 1; }
echo "→ Резервная копия базы"
bash scripts/backup_db.sh 2>/dev/null || echo "  (пропущено: копия базы не сделана)"
echo "→ Сохраняю текущую версию в .prev"
rm -rf .prev && mkdir .prev
for d in $PARTS; do [ -d "$d" ] && cp -r "$d" .prev/; done
cp requirements.txt .prev/ 2>/dev/null || true

echo "→ Распаковываю $ZIP"
TMP=$(mktemp -d)
unzip -q -o "$ZIP" -d "$TMP"
for d in $PARTS; do [ -d "$TMP/server/$d" ] && rm -rf "$d" && cp -r "$TMP/server/$d" "$d"; done
cp "$TMP/server/requirements.txt" .
cp "$TMP/server/README.md" . 2>/dev/null || true
rm -rf "$TMP"

echo "→ Пакеты Python"
.venv/bin/pip install -q -r requirements.txt
echo "→ Обновляю базу"
.venv/bin/alembic upgrade head
echo "→ Перезапуск"
systemctl restart kartochki
sleep 3
if systemctl is-active --quiet kartochki; then
  echo "✓ Готово: сайт обновлён и работает"
else
  echo "✗ Сервис не запустился. Последние строки журнала:"
  journalctl -u kartochki -n 30 --no-pager
  echo "Откат: bash $APP/scripts/update.sh --rollback"
  exit 1
fi
