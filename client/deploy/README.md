# Linux client deployment

This directory is the canonical Linux deployment package for the FRP relay
agent and its managed `frpc` process. Compute hosts and mirror hosts use the
same package.

Install `frpc` version `0.68.1` at `/usr/local/bin/frpc`, stage the complete
`client/` directory on the target, and run:

```bash
sudo client/deploy/install-client.sh
```

The installer writes the agent, systemd units, and a new environment template.
It preserves an existing `/etc/frp-relay-agent/agent.env` so upgrades do not
overwrite enrollment or agent credentials. It does not enable or start the
services. Complete registration first, then run:

```bash
sudo python3 /opt/frp-relay-agent/frp_relay_agent.py \
  --config /etc/frp-relay-agent/agent.env --once
sudo systemctl enable --now frp-relay-agent frp-relay-frpc
```

Never commit `agent.env`, `agent-state.json`, or `frpc.generated.toml`.
