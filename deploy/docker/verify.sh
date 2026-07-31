#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
compose=(docker compose --file "$script_dir/compose.yaml")

"${compose[@]}" ps
curl --fail --silent --show-error http://127.0.0.1:8010/health
printf '\n'

frps_version="$("${compose[@]}" exec -T frps frps --version)"
if [ "$frps_version" != "0.68.1" ]; then
  echo "unexpected frps version: $frps_version" >&2
  exit 1
fi

for port in 80 443 7000 7500 8010 8080; do
  if ! ss -H -lnt "sport = :${port}" | grep -q .; then
    echo "required TCP listener is missing: $port" >&2
    exit 1
  fi
done

if ! docker inspect --format '{{.State.Running}}' x-ui 2>/dev/null | grep -qx true; then
  echo "unrelated x-ui container is not running" >&2
  exit 1
fi

echo "FRP Relay Docker verification passed"
