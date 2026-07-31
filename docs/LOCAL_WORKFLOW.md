# Local Workflow

This workspace is the source of truth for development and version management.
The production deployment target is reached through the `edge-gateway` SSH
alias. Server deployment still requires an immutable release; the remote host
is never a development workspace or Git source of truth.

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
6. Publish or select the immutable `frp-server-v*` release and matching parent
   Manifest through the release workflow.
7. Complete the parent hardware-ops bootstrap and confirm `edge-gateway`
   resolves to the fresh Relay dashboard `public_ip`.
8. Deploy and verify the selected release through the approved FRP Server
   infrastructure workflow.

## Production Deployment

Read `SERVER_DEPLOY_EDGE_GATEWAY.md` and `../deploy/docker/README.md`. The
production application and Compose profile are under:

```text
/opt/deep-assess/frp-relay
/opt/deep-assess/frp-relay/deploy/docker/compose.yaml
```

Connect with `ssh edge-gateway` only after the live-state check. Do not copy a
working tree directly to production.

## Legacy kchat Sync

`scripts/deploy-server-scp.ps1` copies `server/` and `deploy/` to
`kchat:/src/frp_relay`. It is retained only for the legacy systemd deployment
and must not be pointed at `edge-gateway` or used for a production update.

The legacy sync intentionally leaves `client/`, `docs/`, `.git/`, local caches,
and secrets on the local machine.

## Secret Handling

- Keep production server secrets in
  `edge-gateway:/etc/deep-assess/frp-relay/server.env` with mode `0600`.
- Treat `kchat:/src/frp_relay/.env` as legacy host state; never copy it into a
  new deployment as a substitute for an approved secret migration.
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
