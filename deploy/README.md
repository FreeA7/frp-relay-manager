# Deploy

Deployment templates and server-side operational files.

This tree contains the legacy kchat systemd templates and the versioned Docker
Compose profile under `docker/`. Deployment assets must come from the selected
immutable server release tag.

Production operations use `ssh edge-gateway` and the Docker profile. Read
`../docs/SERVER_DEPLOY_EDGE_GATEWAY.md` first. The kchat templates remain only
for historical rollback analysis and must not be applied to production.

Do not commit real secrets or generated production configs containing tokens.
