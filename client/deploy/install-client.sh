#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "install-client.sh must run as root" >&2
  exit 1
fi

deploy_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
client_dir="$(cd "$deploy_dir/.." && pwd)"
agent_source="$client_dir/agent/frp_relay_agent.py"
env_source="$deploy_dir/agent.env.example"
systemd_source="$deploy_dir/systemd"

if [ ! -f "$agent_source" ]; then
  echo "FRP relay agent source not found: $agent_source" >&2
  exit 1
fi
if [ ! -x /usr/local/bin/frpc ]; then
  echo "frpc must be installed at /usr/local/bin/frpc before installing the client services" >&2
  exit 1
fi

install -d -o root -g root -m 0755 /opt/frp-relay-agent
install -o root -g root -m 0755 "$agent_source" /opt/frp-relay-agent/frp_relay_agent.py

install -d -o root -g root -m 0700 /etc/frp-relay-agent
if [ ! -e /etc/frp-relay-agent/agent.env ]; then
  install -o root -g root -m 0600 "$env_source" /etc/frp-relay-agent/agent.env
else
  chown root:root /etc/frp-relay-agent/agent.env
  chmod 0600 /etc/frp-relay-agent/agent.env
fi

install -o root -g root -m 0644 \
  "$systemd_source/frp-relay-agent.service" \
  /etc/systemd/system/frp-relay-agent.service
install -o root -g root -m 0644 \
  "$systemd_source/frp-relay-frpc.service" \
  /etc/systemd/system/frp-relay-frpc.service
systemctl daemon-reload

echo "FRP relay client installed. Configure /etc/frp-relay-agent/agent.env before registration."
