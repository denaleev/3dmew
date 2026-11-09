#!/usr/bin/env bash
# Installs Docker on Debian 12 (official repository) and starts PostgreSQL 16 from docker-compose.yml.
# Run as root from the project folder:  sudo bash scripts/postgres_docker.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "Сначала создай .env:  cp .env.example .env  и впиши пароль POSTGRES_PASSWORD"; exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  apt-get update
  apt-get install -y ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  . /etc/os-release  # works on Debian and Ubuntu
  curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc

  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
  systemctl enable --now docker
fi

docker compose --env-file .env up -d db
echo "Жду, пока база запустится…"
for i in $(seq 1 60); do
  if docker compose --env-file .env exec -T db sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; then
    echo "PostgreSQL работает на 127.0.0.1:5432"; exit 0
  fi
  sleep 2
done
echo "База не ответила за 2 минуты. Посмотри журнал: docker compose logs db"; exit 1
