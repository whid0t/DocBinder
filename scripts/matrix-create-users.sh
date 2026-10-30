#!/usr/bin/env sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ ! -f "$PROJECT_DIR/.env" ]; then
  echo "Copy .env.example to .env first."
  exit 1
fi
set -a
. "$PROJECT_DIR/.env"
set +a

create_user() {
  username=$1
  password=$2
  if docker compose -f "$PROJECT_DIR/docker-compose.yml" exec -T synapse \
    register_new_matrix_user http://localhost:8008 -c /config/local.yaml \
    -u "$username" -p "$password" --no-admin; then
    echo "Created @$username:klinikum.example"
  else
    echo "Could not create @$username (it may already exist)."
  fi
}

create_user "lena.hofer" "$DOCTOR_MATRIX_PASSWORD"
create_user "carebridge" "$BOT_MATRIX_PASSWORD"

