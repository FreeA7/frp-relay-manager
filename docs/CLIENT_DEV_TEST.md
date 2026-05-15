# Client Development and Testing

Client-side work lives under `client/` and stays local unless a separate client
package is intentionally prepared.

## Client Role

The client machine runs:

- `frpc`
- a Python agent

The agent should eventually register with the server, send heartbeats, report
machine status, handle port checks, and update local frpc configuration.

## Local Development

Use `client/agent` for the Python agent implementation. Keep templates and local
test helpers in the client tree, but do not sync this directory to the kchat
server with the server deployment script.

Create a local config from `client/agent/agent.env.example`:

```powershell
Copy-Item .\client\agent\agent.env.example .\client\agent\agent.env
```

Then set `FRP_RELAY_SERVER_URL` and `FRP_RELAY_ENROLLMENT_TOKEN`.

Run once:

```powershell
python .\client\agent\frp_relay_agent.py --config .\client\agent\agent.env --once
```

Run continuously:

```powershell
python .\client\agent\frp_relay_agent.py --config .\client\agent\agent.env
```

## Test Flow

1. Start or mock the server API.
2. Run the client agent locally.
3. Register the client with an enrollment token.
4. Verify heartbeat and machine information reporting.
5. Test port checks against common local services such as SSH, HTTP, or a simple
   local TCP listener.
6. Apply a forwarding rule and verify frpc config generation or reload behavior.

## Connection Targets

Future client tests should connect through the public panel/API endpoint once it
exists:

- `panel.tunnel.freea7.fun`

During early local development, use localhost endpoints or mocks until the
server-side API is deployed.

## Current Test Status

As of 2026-05-15:

- Local agent registered successfully against `https://panel.tunnel.freea7.fun`.
- Local agent heartbeat succeeded.
- Server-created port-check task was processed by the local agent.
- HTTP forward rule for `local-win-test.tunnel.freea7.fun` was created.
- Local agent generated `client/agent/frpc.generated.toml`.
- Running downloaded Windows `frpc.exe` on this machine failed with Windows
  error: `The volume for a file has been externally altered so that the opened
  file is no longer valid`.

The remaining client-side end-to-end check is to run a working local `frpc`
binary with the generated config while a local HTTP service listens on the
forwarded port.
