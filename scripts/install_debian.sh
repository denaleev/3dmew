#!/usr/bin/env bash
# Full install on a clean Debian 12 server.
#   sudo bash scripts/install_debian.sh your-domain.ru
# What it does: system packages, Docker + PostgreSQL, Python venv, Alembic migrations,
# systemd service, nginx site and (if the domain already points here) a free HTTPS certificate.
set -euo pipefail
DOMAIN="${1:-}"
APP_DIR=/opt/kartochki
SRC="$(cd "$(dirname "$0")/.." && pwd)"

if [ "$(id -u)" != 0 ]; then echo "Запусти через sudo"; exit 1; fi
if [ -z "$DOMAIN" ]; then echo "Укажи домен: sudo bash scripts/install_debian.sh example.ru"; exit 1; fi

apt-get update
apt-get install -y python3 python3-venv python3-pip nginx curl rsync certbot python3-certbot-nginx

# 1. code -> /opt/kartochki
id kartochki >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin kartochki
mkdir -p "$APP_DIR"
if [ "$SRC" != "$APP_DIR" ]; then rsync -a --exclude .venv --exclude __pycache__ "$SRC"/ "$APP_DIR"/; fi
cd "$APP_DIR"

# 2. settings
if [ ! -f .env ]; then
  cp .env.example .env
  PW=$(python3 -c "import secrets;print(secrets.token_hex(16))")
  SK=$(python3 -c "import secrets;print(secrets.token_urlsafe(48))")
  sed -i "s|^PUBLIC_URL=.*|PUBLIC_URL=https://$DOMAIN|; s|^SECRET_KEY=.*|SECRET_KEY=$SK|; s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$PW|; s|^DATABASE_URL=.*|DATABASE_URL=postgresql+psycopg://cards:$PW@127.0.0.1:5432/cards|" .env
  echo "Создан .env с новыми паролями"
fi
chmod 600 .env

# 3. PostgreSQL in Docker
bash scripts/postgres_docker.sh

# 4. Python
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
chown -R kartochki:kartochki "$APP_DIR"

# 5. service
cp deploy/kartochki.service /etc/systemd/system/kartochki.service
systemctl daemon-reload
systemctl enable --now kartochki
sleep 3
curl -fsS http://127.0.0.1:8000/api/health && echo

# 6. nginx + HTTPS
sed "s/example.ru/$DOMAIN/g" deploy/nginx.conf > /etc/nginx/sites-available/kartochki
ln -sf /etc/nginx/sites-available/kartochki /etc/nginx/sites-enabled/kartochki
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
if certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email --redirect; then
  echo "HTTPS готов: https://$DOMAIN"
else
  echo "Сертификат не выдан: проверь, что домен $DOMAIN указывает на IP этого сервера, и запусти: certbot --nginx -d $DOMAIN"
fi
echo "Готово. Ключи соцсетей и Claude впиши в $APP_DIR/.env и выполни: systemctl restart kartochki"
