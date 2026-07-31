#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
compose=(docker compose --file "$script_dir/compose.yaml")
env_file="/etc/deep-assess/frp-relay/server.env"

if [ ! -f "$env_file" ]; then
  echo "protected server environment is missing: $env_file" >&2
  exit 1
fi

deployment_profile="$(awk -F= '$1 == "FRP_RELAY_DEPLOYMENT_PROFILE" {print substr($0, index($0, "=") + 1); exit}' "$env_file")"
deployment_profile="${deployment_profile:-x-ui-cohost}"

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

case "$deployment_profile" in
  dedicated)
    expected_frps_config="frps.dedicated.toml"
    ;;
  x-ui-cohost)
    expected_frps_config="frps.toml"
    if ! docker inspect --format '{{.State.Running}}' x-ui 2>/dev/null | grep -qx true; then
      echo "unrelated x-ui container is not running" >&2
      exit 1
    fi
    ;;
  *)
    echo "unsupported FRP_RELAY_DEPLOYMENT_PROFILE: $deployment_profile" >&2
    exit 1
    ;;
esac

if ! cmp --silent "$script_dir/$expected_frps_config" /etc/deep-assess/frp-relay/frps.toml; then
  echo "installed frps configuration does not match profile: $deployment_profile" >&2
  exit 1
fi

echo "FRP Relay Docker verification passed: $deployment_profile"
