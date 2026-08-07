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
curl --fail --silent --show-error --insecure \
  --header 'Host: panel.tunnel.freea7.fun' \
  https://127.0.0.1/health
printf '\n'

root_status="$(curl --silent --output /dev/null --write-out '%{http_code}' --insecure \
  --header 'Host: panel.tunnel.freea7.fun' https://127.0.0.1/)"
if [ "$root_status" != "404" ]; then
  echo "panel root must return 404, got: $root_status" >&2
  exit 1
fi

legacy_login_status="$(curl --silent --output /dev/null --write-out '%{http_code}' --insecure \
  --header 'Host: panel.tunnel.freea7.fun' \
  --header 'Content-Type: application/json' \
  --data '{"email":"removed@futurememetech.com","password":"removed"}' \
  https://127.0.0.1/api/auth/login)"
if [ "$legacy_login_status" != "404" ]; then
  echo "legacy FRP login must return 404, got: $legacy_login_status" >&2
  exit 1
fi

"${compose[@]}" exec -T api python -c \
  "import json,os,urllib.request; token=os.environ.get('FRP_RELAY_TIANSHU_TOKEN',''); assert len(token)>=32; request=urllib.request.Request('http://127.0.0.1:8010/api/dashboard',headers={'Authorization':'Bearer '+token,'X-Tianshu-User':'release-verifier@futurememetech.com','X-Tianshu-Role':'viewer'}); assert json.load(urllib.request.urlopen(request,timeout=5))['client_count']>=0"

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

if ss -H -lnt "sport = :18081" | grep -q .; then
  echo "removed FRP web listener is still active: 18081" >&2
  exit 1
fi

if docker ps --format '{{.Names}}' | grep -qx 'deep-assess-edge-gateway-web-1'; then
  echo "removed FRP web container is still running" >&2
  exit 1
fi

"${compose[@]}" exec -T api python -c \
  "import os,sqlite3; db=sqlite3.connect(os.environ['FRP_RELAY_DATABASE']); assert db.execute(\"SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'\").fetchone() is None"

if ! docker inspect --format '{{.State.Running}}' deep-assess-edge-ingress-ingress-1 2>/dev/null | grep -qx true; then
  echo "independent Edge ingress container is not running" >&2
  exit 1
fi

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

for status_file in \
  /run/deepassess-openvpn/core.status \
  /run/deepassess-openvpn/engine.status \
  /run/deepassess-openvpn/backup.status \
  /run/deepassess-openvpn/futureheartguard.status \
  /run/deepassess-openvpn/services.status; do
  if [ ! -r "$status_file" ]; then
    echo "OpenVPN status file is missing or unreadable: $status_file" >&2
    exit 1
  fi
done

"${compose[@]}" exec -T api python -c \
  "import json,os,urllib.request; token=os.environ['FRP_RELAY_TIANSHU_TOKEN']; request=urllib.request.Request('http://127.0.0.1:8010/api/openvpn/status',headers={'Authorization':'Bearer '+token,'X-Tianshu-User':'release-verifier@futurememetech.com','X-Tianshu-Role':'viewer'}); result=json.load(urllib.request.urlopen(request,timeout=5)); assert result['tunnel_count']==5; services=next(tunnel for tunnel in result['tunnels'] if tunnel['id']=='services'); assert services['network']=='10.254.0.32/29'"

echo "Edge Gateway Docker verification passed: $deployment_profile"
