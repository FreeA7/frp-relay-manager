# DeepAssess Edge Gateway

This repository contains the DeepAssess public edge console and FRP relay.
The authenticated console keeps the existing FRP device and forwarding
workflow and adds read-only OpenVPN tunnel and client monitoring.

## Layout

- `docs/` - project notes, handoff material, local workflow, deployment docs.
- `server/` - server-side app code for the kchat deployment.
- `client/` - client-side agent code and local connection tests.
- `deploy/` - nginx, systemd, and frp deployment templates.
- `scripts/` - local helper scripts, including scp deployment.

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

Only `server/` and `deploy/` are copied to `kchat:/src/frp_relay`.
Client code, local docs, Git metadata, secrets, caches, and build artifacts stay
on the local machine.

Use:

```powershell
.\scripts\deploy-server-scp.ps1
```

after committing and reviewing local changes.
