# Edge Gateway Server Deployment

`edge-gateway` is the production SSH alias for the FRP Server. Tianshu is the
only human management console; this host owns FRPS, Agent APIs, the operator
API, and VPN observations. The repository defines releases and procedures; it does not define a
permanent production IP address.

## Connection Gate

From the parent `deep-assess-ops-center` repository, complete
`agents/hardware-ops/START_HERE.md` and the FRP Server workflow before any
server operation. At minimum, query fresh Relay state and resolve the alias:

```bash
python3 tools/hardware_ops.py doctor
python3 tools/hardware_ops.py fleet
python3 tools/hardware_ops.py releases --product frp-server
ssh -G edge-gateway
```

Confirm that the resolved `edge-gateway` destination agrees with the fresh
Relay dashboard `public_ip`, then connect with:

```bash
ssh edge-gateway
```

Stop if the alias and live Relay state disagree. Do not substitute an IP from a
Markdown file. The `kchat` alias is the legacy relay host; a working SSH or
health response from that host does not make it the production target.

## Production Paths

- Application: `/opt/deep-assess/frp-relay`
- Compose file: `/opt/deep-assess/frp-relay/deploy/docker/compose.yaml`
- Protected environment: `/etc/deep-assess/frp-relay/server.env` (`0600`)
- Generated frps configuration: `/etc/deep-assess/frp-relay/frps.toml`
- SQLite data: `/var/lib/deep-assess/frp-relay`
- frps logs: `/var/log/deep-assess/frps`
- Release Stamp: `/etc/frp-relay-manager/release.json`

Never print the protected environment, tokens, password hashes, database rows
containing credentials, or generated frps configuration.

## Read-Only Inspection

The following commands identify the installed release and current Compose
state without changing services:

```bash
ssh edge-gateway
sudo sed -n '1,240p' /etc/frp-relay-manager/release.json
sudo docker compose \
  -f /opt/deep-assess/frp-relay/deploy/docker/compose.yaml ps
curl -fsS https://panel.tunnel.freea7.fun/health
```

An inspection does not authorize a deployment, restart, DNS change, database
write, or Release Stamp update.

## Deployment Model

Deploy only a selected immutable `frp-server-v*` tag and its matching parent
Release Manifest. Follow `deploy/docker/README.md` for the Docker Compose
profile and the parent repository's `upgrade-frp-server.md` for lease, backup,
verification, observation, and rollback requirements.

The retired kchat deployment path and independent panel artifacts are not part
of this release. Preserve client records, forwarding rules, signing material,
TLS material, and unrelated ingress during every approved deployment.

## Stable Service Entry Points

- Agent and protected operator API: `https://panel.tunnel.freea7.fun`
- FRP tunnel domain: `tunnel.freea7.fun`
- FRP control port: `7000`

Operators use Tianshu for all human viewing and management. The panel domain is
retained for machine API compatibility and does not remain a human login or Web
application after the final cutover. Operators must obtain current client
forwarding addresses from Tianshu, the live Relay API, or Fleet context. These
domain names are stable service identifiers; their resolved addresses remain
live state and may change.
