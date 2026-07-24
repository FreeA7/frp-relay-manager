# Client Agent

Python agent for client machines.

Planned responsibilities:

- register with the server using an enrollment token
- send heartbeats and machine status
- probe local ports on request
- manage local frpc configuration
- reload or restart frpc after forwarding rule changes

The agent automatically reports CPU, display/GPU controller, total physical
memory, root filesystem capacity, and OS version on registration and every
heartbeat. `FRP_RELAY_HARDWARE_*` values remain available as explicit
overrides for appliances whose platform tools cannot identify a component.

Agent `0.3.0` preserves shell quoting in `agent.env`, reports reload command
failures, and retries a failed frpc reload on later polling cycles. A successful
reload removes the adjacent `frpc.generated.toml.reload-pending` marker.

For client setup instructions, see `docs/CLIENT_ONBOARDING.md`.
