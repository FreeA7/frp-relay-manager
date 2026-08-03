# Docker Deployment

This profile runs only the Edge Gateway API and `frps` with host networking.
Human viewing and management belong exclusively to Tianshu. The independent
Edge ingress owns ports 80 and 443, proxies the protected machine API, and
returns 404 for ordinary paths on `panel.tunnel.freea7.fun`.

## Host Paths

- Application: `/opt/deep-assess/frp-relay`
- Protected environment: `/etc/deep-assess/frp-relay/server.env` (`0600`)
- Generated frps configuration: `/etc/deep-assess/frp-relay/frps.toml` (`0644`)
- SQLite data: `/var/lib/deep-assess/frp-relay` (`0700`, UID/GID `10001`)
- frps logs: `/var/log/deep-assess/frps` (`0750`, UID/GID `10002`)
- OpenVPN status files: `/run/deepassess-openvpn` (Core, Engine, Backup, and Future Heart Guard; read-only in the API container, group GID `10003`)
- Edge ingress source: `services/edge-ingress/` in the parent operations repository

The protected environment must contain a distinct
`FRP_RELAY_TIANSHU_TOKEN` with at least 32 characters before this release is
started. Do not reuse any Fleet, FRPS, Agent, or signing secret.

Do not copy a live SQLite file. Use SQLite's backup API, verify the backup, and
transfer it with mode `0600`. Preserve the signing secret, frps token, Fleet
read token, client records, forwarding rules, and audit history. The release
drops only the retired local `users` table.

## Deployment Profiles

Set one explicit host profile in the protected environment:

```env
FRP_RELAY_DEPLOYMENT_PROFILE=dedicated
```

The `dedicated` profile does not require an unrelated service or a reserved
FRP forwarding port. It installs `frps.dedicated.toml`, which allows the full
TCP/UDP `20000-49999` pool. Keep VPN ports outside that pool.

For a host that already runs x-ui/xray on TCP `18888` and `44999`, use:

```env
FRP_RELAY_DEPLOYMENT_PROFILE=x-ui-cohost
FRP_RELAY_RESERVED_PORTS=44999
```

The `x-ui-cohost` profile excludes `44999` from `frps`. Confirm the restored
database does not already assign a forward to that port, and do not stop,
reconfigure, or include x-ui in this Compose project. It installs the
coexistence template at `frps.toml`.

The independent Edge ingress requires TCP `80` and `443`; FRPS requires TCP
`7000` and TCP/UDP `20000-49999`; OpenVPN uses ports outside the FRP pool. TCP
`80` serves redirects and HTTP certificate challenges. TCP `18081` must be
closed after the retired Web container is removed. For
`x-ui-cohost`, keep the host-level `44999` rule for x-ui; FRP does not bind it.
Cloud security-group rules must match the host firewall before cutover.

## Verification

Before starting, run `docker compose config` and confirm ports `80`, `443`,
`7000`, `7500`, `8010`, and `8080` are free. Build and start only this project:

```bash
./prepare-host.sh
docker compose build
docker compose up -d --remove-orphans
./verify.sh
```

Verify TLS, panel root and legacy login 404 responses, the Tianshu viewer
contract, all four VPN status files, the restored client and forward counts,
and an isolated client.
For `x-ui-cohost`, also
confirm x-ui ports and containers remain healthy. Keep the old relay and a
verified off-host backup available for rollback.
