# Client Onboarding Guide

This guide is for a client machine that needs to connect to the FRP Relay
Manager.

## Access Points

- Admin panel: `https://panel.tunnel.freea7.fun`
- Agent API base URL: `https://panel.tunnel.freea7.fun`
- FRP server address: `45.141.136.217`
- FRP control port: `7000`
- HTTP tunnel domain pattern: `https://<subdomain>.tunnel.freea7.fun`
- TCP/UDP tunnel address pattern: `45.141.136.217:<remote_port>`

The administrator must create an enrollment token in the panel and send it to
the client operator. The token is one-time use; request a new token if
registration fails with `Invalid enrollment token`.

## Requirements

- Python 3.10 or newer.
- `frpc` version `0.68.1` for the client OS.
- Outbound network access to:
  - `https://panel.tunnel.freea7.fun`
  - `45.141.136.217:7000`

## Download frpc

Download the matching client package from:

`https://github.com/fatedier/frp/releases/tag/v0.68.1`

Examples:

- Windows amd64: `frp_0.68.1_windows_amd64.zip`
- Linux amd64: `frp_0.68.1_linux_amd64.tar.gz`
- macOS Apple Silicon: `frp_0.68.1_darwin_arm64.tar.gz`

Extract the package and keep the `frpc` binary path ready.

## Prepare the Agent

Copy this repository's client agent directory to the client machine:

```text
client/agent/
```

Create `agent.env` from `agent.env.example`:

```powershell
Copy-Item .\agent.env.example .\agent.env
```

On Linux/macOS:

```bash
cp agent.env.example agent.env
```

Edit `agent.env`:

```env
FRP_RELAY_SERVER_URL=https://panel.tunnel.freea7.fun
FRP_RELAY_ENROLLMENT_TOKEN=replace-with-token-from-admin
FRP_RELAY_HEARTBEAT_INTERVAL_SECONDS=30
FRP_RELAY_AGENT_STATE=agent-state.json
FRP_RELAY_FRPC_CONFIG=frpc.generated.toml
FRP_RELAY_FRPC_RELOAD_CMD=
```

For the first run, `FRP_RELAY_ENROLLMENT_TOKEN` is required. After successful
registration, the agent writes `agent-state.json` and reuses its agent token.
The relay client name is always the machine hostname.

## Register and Test Agent

Run once:

```powershell
python .\frp_relay_agent.py --config .\agent.env --once
```

Linux/macOS:

```bash
python3 ./frp_relay_agent.py --config ./agent.env --once
```

Expected results:

- `agent-state.json` is created.
- `frpc.generated.toml` is created.
- The admin panel shows the client as online.

Run continuously:

```powershell
python .\frp_relay_agent.py --config .\agent.env
```

Linux/macOS:

```bash
python3 ./frp_relay_agent.py --config ./agent.env
```

## Start frpc

After the administrator creates a forwarding rule, run `frpc` with the generated
config:

Windows:

```powershell
.\frpc.exe -c .\frpc.generated.toml
```

Linux/macOS:

```bash
./frpc -c ./frpc.generated.toml
```

Keep both processes running:

- Python agent
- frpc

The agent updates `frpc.generated.toml` when forwarding rules change. Restart or
reload `frpc` after config changes unless `FRP_RELAY_FRPC_RELOAD_CMD` is set.

## Configure a Forward

Ask the administrator to:

1. Select the registered client.
2. Probe the local service port, such as `22`, `80`, `3389`, `3306`, or `8080`.
3. Create a forwarding rule.
4. Send back the public access address.

Examples:

- SSH: `ssh user@45.141.136.217 -p <remote_port>`
- HTTP: `https://<subdomain>.tunnel.freea7.fun`
- Database/TCP service: `45.141.136.217:<remote_port>`

## Troubleshooting

- `Invalid enrollment token`: token was already used or expired. Ask the
  administrator for a new token.
- Agent cannot connect: verify outbound HTTPS access to
  `https://panel.tunnel.freea7.fun`.
- frpc cannot connect: verify outbound TCP access to `45.141.136.217:7000`.
- Public address opens but service is unavailable: verify the local service is
  listening on the configured `local_ip` and `local_port`.
- HTTP tunnel returns an error: keep `frpc` running and confirm the forwarding
  rule uses protocol `http`.

Do not share `agent-state.json`, `frpc.generated.toml`, enrollment tokens, or
agent tokens publicly.
