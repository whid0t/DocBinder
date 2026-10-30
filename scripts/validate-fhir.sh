#!/usr/bin/env sh
set -eu

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 path/to/resource.json [more.json ...]"
  exit 1
fi
if [ ! -f validator_cli.jar ]; then
  echo "validator_cli.jar is missing in the repository root."
  echo "Download it from the official hapifhir/org.hl7.fhir.core releases."
  exit 1
fi

for resource in "$@"; do
  echo "Validating $resource"
  java -jar validator_cli.jar "$resource" -version 4.0
done
