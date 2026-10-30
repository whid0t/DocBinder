#!/usr/bin/env sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DATA_DIR="$PROJECT_DIR/matrix/synapse/data"
mkdir -p "$DATA_DIR"

if [ -f "$DATA_DIR/homeserver.yaml" ]; then
  echo "Synapse configuration already exists."
  exit 0
fi

docker run --rm \
  -v "$DATA_DIR:/data" \
  -e SYNAPSE_SERVER_NAME=klinikum.example \
  -e SYNAPSE_REPORT_STATS=no \
  -e UID="$(id -u)" \
  -e GID="$(id -g)" \
  matrixdotorg/synapse:latest generate

echo "Generated $DATA_DIR/homeserver.yaml"

