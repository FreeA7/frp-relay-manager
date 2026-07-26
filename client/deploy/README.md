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

Agent protocol v2 reads these non-secret observation files when present:

```text
/etc/deep-assess/device-identity.json
/etc/deep-assess/release.json
/etc/frp-relay-agent/release.json
/var/lib/deep-assess/tenant-binding.json
```

Missing files are reported as unversioned or unlinked; the Agent never invents
a version or stable device identity. Release stamps are written by the release
workflow only after installation and verification succeed.

Never commit `agent.env`, `agent-state.json`, or `frpc.generated.toml`.
