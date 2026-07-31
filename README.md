# DeepAssess Edge Gateway

This repository contains the DeepAssess public edge console and FRP relay.
The authenticated console keeps the existing FRP device and forwarding
workflow and adds read-only OpenVPN tunnel and client monitoring.

## Layout

- `docs/` - project notes, handoff material, local workflow, deployment docs.
- `server/` - server-side application code packaged by the Edge Gateway profile.
- `client/` - client-side agent code and local connection tests.
- `deploy/` - nginx, systemd, and frp deployment templates.
- `scripts/` - local helper scripts, including the legacy kchat scp helper.

## Fleet Boundary

The FRP subsystem is authoritative for current client heartbeat state and forwarding
rules. DEEP-Assess Fleet is authoritative for stable device identity, desired
and observed releases, deployments, and verification history.

Agent protocol v2 reports the stable `deviceId`, Tenant `deviceUuid`, Agent and
`frpc` versions, service state, and local release stamps. The relay stores only
the latest snapshot. Fleet reads that snapshot from the scoped endpoint:

```text
GET /api/integrations/fleet/clients
Authorization: Bearer <FRP_RELAY_FLEET_READ_TOKEN>
```

This endpoint does not return agent tokens, enrollment tokens, local IPs, or
forwarding configuration.

## Deployment Model

The production server uses the versioned Docker Compose profile under
`deploy/docker/` and the SSH alias `edge-gateway`. Read
`docs/SERVER_DEPLOY_EDGE_GATEWAY.md` before connecting. Resolve the alias
against fresh Relay state instead of copying an IP address from documentation.

Deploy only an immutable `frp-server-v*` release and its matching Manifest.
Client code, local docs, Git metadata, secrets, caches, and build artifacts stay
outside the production application directory.

The `kchat` host, `scripts/deploy-server-scp.ps1`, and
`deploy/INSTALL_KCHAT.md` belong to the legacy systemd deployment. They must
not be used to update production.
