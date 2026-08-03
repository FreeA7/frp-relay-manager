# Server

Server-side application code for the FRP relay system.

This tree is packaged by the versioned Docker Compose profile deployed through
the production `edge-gateway` SSH alias. It contains the machine API and
server-side logic needed to manage clients, port checks, forwarding rules, and
frps configuration. Human operators use Tianshu; FRP has no independent Web
application or login. Follow
`../docs/SERVER_DEPLOY_EDGE_GATEWAY.md`; do not copy the working tree directly
to a server.

Runtime defaults from the handoff:

- Backend API: `127.0.0.1:8010`
- Machine API: `panel.tunnel.freea7.fun`
- Human console: Tianshu
- TCP/UDP port pool: `20000-49999`

Commit only source, templates, and examples. Do not commit real `.env` files,
SQLite databases, generated secrets, or build artifacts.
