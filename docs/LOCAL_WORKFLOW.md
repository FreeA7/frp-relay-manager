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

## Secret Handling

- Keep production server secrets in
  `edge-gateway:/etc/deep-assess/frp-relay/server.env` with mode `0600`.
- Commit only `.env.example` files.
- Never print DNSPod credentials, frps auth tokens, signing secrets, or service
  tokens in logs or documentation.

## Local Backend

```powershell
cd .\server\backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Use `server/.env.example` as the template for local environment variables. Real
values should live in an untracked `.env`.

There is no FRP frontend. Develop and test human-facing management in Tianshu.
