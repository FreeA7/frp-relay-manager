# frp-relay-manager

This repository is the local development workspace for the FRP relay manager.
Development, documentation, and Git history live here. The `kchat` server is
only the deployment target.

## Layout

- `docs/` - project notes, handoff material, local workflow, deployment docs.
- `server/` - server-side app code for the kchat deployment.
- `client/` - client-side agent code and local connection tests.
- `deploy/` - nginx, systemd, and frp deployment templates.
- `scripts/` - local helper scripts, including scp deployment.

## Deployment Model

Only `server/` and `deploy/` are copied to `kchat:/src/frp_relay`.
Client code, local docs, Git metadata, secrets, caches, and build artifacts stay
on the local machine.

Use:

```powershell
.\scripts\deploy-server-scp.ps1
```

after committing and reviewing local changes.
