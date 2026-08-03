# Backend

FastAPI backend for the server-side relay manager.

Responsibilities:

- client enrollment and heartbeat handling
- port check requests and results
- forwarding rule CRUD
- frps config generation and reload coordination
- latest device identity and release observation snapshots
- scoped, read-only Fleet integration
- authenticated, read-only OpenVPN status monitoring
- scoped Tianshu operator access with server-side role enforcement and write auditing

The production service should bind to `127.0.0.1:8010` behind nginx.
OpenVPN status-version-3 files are read from `/run/deepassess-openvpn` through
a read-only container mount. The API never reads or returns VPN key material.

## Local Run

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

The app initializes SQLite and removes the retired local `users` table on
startup. It has no local human account or login endpoint.

`FRP_RELAY_TIANSHU_TOKEN` enables the server-to-server management path used by
Tianshu. Tianshu supplies the authenticated operator in `X-Tianshu-User` and
`X-Tianshu-Role`; viewer and editor roles are read-only, while mutations require
the admin role. The integration token never belongs in browser storage.

Set a separate `FRP_RELAY_FLEET_READ_TOKEN` of at least 32 characters before
enabling the Fleet integration endpoint. Do not reuse the Tianshu service
token, signing key, frps token, or agent token.
