# Server

Server-side application code for the FRP relay system.

This tree is copied to `kchat:/src/frp_relay/server` during deployment. It is
expected to contain the backend API, frontend app, and server-side logic needed
to manage clients, port checks, forwarding rules, and frps configuration.

Runtime defaults from the handoff:

- Backend API: `127.0.0.1:8010`
- Admin panel: `panel.tunnel.freea7.fun`
- Admin user: `freea7@futurememetech.com`
- TCP/UDP port pool: `20000-49999`

Commit only source, templates, and examples. Do not commit real `.env` files,
SQLite databases, generated secrets, or build artifacts.
