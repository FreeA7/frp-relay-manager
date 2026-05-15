# Local Workflow

This workspace is the source of truth for development and version management.
The `kchat` server is a deployment target only.

## Local Repository

- Repository root: `C:\Users\FreeA7\Desktop\workplace\frp-relay-manager`
- Keep Git history locally in this directory.
- Commit source code, templates, and documentation.
- Do not commit `.env`, databases, generated secrets, virtual environments,
  `node_modules`, frontend builds, or local runtime state.

## Development Order

1. Build the service skeleton under `server/`.
2. Build the client agent under `client/`.
3. Add deployment templates under `deploy/`.
4. Test server and client locally where possible.
5. Commit local changes.
6. Run the scp deployment script to copy server-side files to `kchat`.
7. SSH to `kchat` and run install, restart, and verification commands.

## Deployment Sync

Use the local PowerShell helper:

```powershell
.\scripts\deploy-server-scp.ps1
```

The script copies only:

- `server/`
- `deploy/`

to:

- `kchat:/src/frp_relay`

It intentionally leaves `client/`, `docs/`, `.git/`, local caches, and secrets
on the local machine.

## Secret Handling

- Keep real server secrets in `kchat:/src/frp_relay/.env` or another protected
  server-side location.
- Commit only `.env.example` files.
- Never print DNSPod credentials, frps auth tokens, JWT secrets, or generated
  admin passwords in logs or documentation.

## Local Backend

```powershell
cd .\server\backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Use `server/.env.example` as the template for local environment variables. Real
values should live in an untracked `.env`.

## Local Frontend

Node is not bundled in this repository. After installing Node LTS:

```powershell
cd .\server\frontend
npm install
npm run dev
```

The frontend calls the same origin by default. For local API proxying, set
`VITE_API_BASE` in an untracked frontend `.env` if needed.
