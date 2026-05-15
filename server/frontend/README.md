# Frontend

React/Vite frontend for the admin panel.

The built frontend will be served by nginx for `panel.tunnel.freea7.fun`.
The UI must require login before showing client status, port checks, forwarding
rules, or public connection addresses.

## Local Run

```powershell
npm install
npm run dev
```

Build output goes to `dist/`, which is ignored by Git and served by nginx on the
server.
