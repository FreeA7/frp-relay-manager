# Backend

FastAPI backend for the server-side relay manager.

Responsibilities:

- admin authentication
- client enrollment and heartbeat handling
- port check requests and results
- forwarding rule CRUD
- frps config generation and reload coordination
- latest device identity and release observation snapshots
- scoped, read-only Fleet integration
- authenticated, read-only OpenVPN status monitoring

The production service should bind to `127.0.0.1:8010` behind nginx.
OpenVPN status-version-3 files are read from `/run/deepassess-openvpn` through
a read-only container mount. The API never reads or returns VPN key material.

## Local Run

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

The app initializes SQLite and the admin account on startup.

Set a separate `FRP_RELAY_FLEET_READ_TOKEN` of at least 32 characters before
enabling the Fleet integration endpoint. Do not reuse the admin password,
signing key, frps token, or agent token.
