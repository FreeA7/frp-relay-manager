# kchat Server Deployment

`kchat` is the deployment target for the server side of this project.
Do not use it as the primary development workspace or Git repository.

## Target

- Host alias: `kchat`
- Server project path: `/src/frp_relay`
- Synced local directories: `server/` and `deploy/`
- Existing project to avoid: `/src/vps_server`
- Existing service to avoid: `vps-openai-relay.service`

## Reserved Runtime Plan

- Admin panel domain: `panel.tunnel.freea7.fun`
- Backend API bind: `127.0.0.1:8010`
- frps control bind: `0.0.0.0:7000`
- frps dashboard/API bind: `127.0.0.1:7500`
- frps HTTP vhost: `127.0.0.1:8080` behind nginx wildcard proxy
- TCP/UDP remote port pool: `20000-49999`
- Wildcard tunnel domain: `*.tunnel.freea7.fun`

## Guardrails

- Do not modify `/src/vps_server`.
- Do not stop, replace, or reconfigure `vps-openai-relay.service`.
- Do not break the existing `api.freea7.fun` nginx site.
- Run `nginx -t` before reloading nginx after any future config change.
- Keep the existing certbot renewal flow; do not add acme.sh or a second
  certificate renewal system.
- Keep frps dashboard/API private to localhost.

## Expected Server Files

After sync, `/src/frp_relay` should contain:

- `server/`
- `deploy/`

Use `deploy/INSTALL_KCHAT.md` as the server-side installation checklist after a
sync.

It should not contain:

- `.git/`
- `client/`
- `docs/`
- local virtual environments
- local Node dependency folders
- local databases or generated secrets

## Current Deployment Status

As of 2026-05-15, the server has been deployed and verified:

- 1GB swap enabled at `/swapfile`.
- Node `v24.15.0` and npm `11.12.1` installed.
- frp `0.68.1` installed at `/usr/local/bin/frps` and `/usr/local/bin/frpc`.
- Backend virtualenv installed under `/src/frp_relay/server/backend/.venv`.
- Frontend built under `/src/frp_relay/server/frontend/dist`.
- `/src/frp_relay/.env` generated on the server with `600 root:root`.
- `frp-relay-api.service`, `frps.service`, and nginx are active.
- `https://panel.tunnel.freea7.fun` returns the built panel.
- `https://panel.tunnel.freea7.fun/health` returns `{"status":"ok"}`.

The deployment script must not chmod runtime directories such as `.venv`,
`node_modules`, or `dist`; those are created on the server and have their own
runtime permissions.
