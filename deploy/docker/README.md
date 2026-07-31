# Docker Deployment

This profile runs the Relay API, `frps`, and nginx panel as one Docker Compose
project with host networking. Host networking is required because FRP binds
dynamic TCP and UDP forwarding ports. The project must not own or restart
unrelated containers and host services.

## Host Paths

- Application: `/opt/deep-assess/frp-relay`
- Protected environment: `/etc/deep-assess/frp-relay/server.env` (`0600`)
- Generated frps configuration: `/etc/deep-assess/frp-relay/frps.toml` (`0644`)
- SQLite data: `/var/lib/deep-assess/frp-relay` (`0700`, UID/GID `10001`)
- frps logs: `/var/log/deep-assess/frps` (`0750`, UID/GID `10002`)
- TLS material: `/etc/letsencrypt` (read-only in the panel container)

Do not copy a live SQLite file. Use SQLite's backup API, verify the backup, and
transfer it with mode `0600`. Preserve the signing secret, frps token, Fleet
read token, client records, forwarding rules, and administrator password hash.

## Coexistence

The migration host already owns TCP `18888` and `44999` for x-ui/xray. This
profile excludes `44999` from `frps` and requires:

```env
FRP_RELAY_RESERVED_PORTS=44999
```

Confirm the restored database does not already assign a forward to `44999`.
Do not stop, reconfigure, or include x-ui in this Compose project.

The host firewall must allow TCP `80`, `443`, and `7000`, plus TCP and UDP
`20000-49999`. Keep the host-level `44999` rule for x-ui; FRP does not bind it.
Cloud security-group rules must match the host firewall before cutover.

## Verification

Before starting, run `docker compose config` and confirm ports `80`, `443`,
`7000`, `7500`, `8010`, and `8080` are free. Build and start only this project:

```bash
./prepare-host.sh
docker compose build
docker compose up -d
./verify.sh
```

Before DNS cutover, verify TLS with `curl --resolve`, confirm the restored
client and forward counts, test an isolated client, and confirm x-ui ports and
containers remain healthy. Keep the old relay and a verified off-host backup
available for rollback.
