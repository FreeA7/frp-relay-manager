#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "prepare-host.sh must run as root" >&2
  exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
env_file="/etc/deep-assess/frp-relay/server.env"

read_env_value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key {print substr($0, index($0, "=") + 1); exit}' "$env_file"
}

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

deployment_profile="$(read_env_value FRP_RELAY_DEPLOYMENT_PROFILE)"
deployment_profile="${deployment_profile:-x-ui-cohost}"
reserved_ports="$(read_env_value FRP_RELAY_RESERVED_PORTS)"
case "$deployment_profile" in
  dedicated)
    frps_config="frps.dedicated.toml"
    ;;
  x-ui-cohost)
    frps_config="frps.toml"
    case ",${reserved_ports}," in
      *,44999,*) ;;
      *)
        echo "FRP_RELAY_RESERVED_PORTS must include host-owned port 44999 for x-ui-cohost" >&2
        exit 1
        ;;
    esac
    ;;
  *)
    echo "unsupported FRP_RELAY_DEPLOYMENT_PROFILE: $deployment_profile" >&2
    exit 1
    ;;
esac

install -d -o root -g root -m 0755 /opt/deep-assess/frp-relay
install -d -o root -g root -m 0700 /etc/deep-assess/frp-relay
install -d -o 10001 -g 10001 -m 0700 /var/lib/deep-assess/frp-relay
install -d -o 10002 -g 10002 -m 0750 /var/log/deep-assess/frps
if ! getent group 10003 >/dev/null; then
  groupadd --system --gid 10003 deepassess-vpn-status
fi
if [ "$(getent group 10003 | cut -d: -f1)" != "deepassess-vpn-status" ]; then
  echo "GID 10003 is already used by another group" >&2
  exit 1
fi
install -d -o root -g 10003 -m 0770 /run/deepassess-openvpn
install -d -o root -g root -m 0755 /var/www/certbot
install -o root -g root -m 0644 "$script_dir/$frps_config" /etc/deep-assess/frp-relay/frps.toml

docker compose --file "$script_dir/compose.yaml" config --quiet
echo "Edge Gateway Docker host preparation passed: $deployment_profile"
