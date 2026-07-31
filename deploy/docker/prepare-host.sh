#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "prepare-host.sh must run as root" >&2
  exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
env_file="/etc/deep-assess/frp-relay/server.env"

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "Docker Engine and the Docker Compose plugin are required" >&2
  exit 1
fi
if [ ! -f "$env_file" ]; then
  echo "protected server environment is missing: $env_file" >&2
  exit 1
fi
if [ "$(stat -c '%a' "$env_file")" != "600" ]; then
  echo "protected server environment must use mode 0600" >&2
  exit 1
fi

reserved_ports="$(awk -F= '$1 == "FRP_RELAY_RESERVED_PORTS" {print substr($0, index($0, "=") + 1)}' "$env_file")"
case ",${reserved_ports}," in
  *,44999,*) ;;
  *)
    echo "FRP_RELAY_RESERVED_PORTS must include host-owned port 44999" >&2
    exit 1
    ;;
esac

install -d -o root -g root -m 0755 /opt/deep-assess/frp-relay
install -d -o root -g root -m 0700 /etc/deep-assess/frp-relay
install -d -o 10001 -g 10001 -m 0700 /var/lib/deep-assess/frp-relay
install -d -o 10002 -g 10002 -m 0750 /var/log/deep-assess/frps
install -o root -g root -m 0644 "$script_dir/frps.toml" /etc/deep-assess/frp-relay/frps.toml

docker compose --file "$script_dir/compose.yaml" config --quiet
echo "FRP Relay Docker host preparation passed"
