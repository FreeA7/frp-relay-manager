# Client

Client-side code for machines that connect to the relay server.

This directory is for local client development and testing. It is not copied to
`kchat` by the server deployment script.

The client package includes:

- `agent/`: the cross-platform Python agent and its tests.
- `deploy/`: the canonical Linux systemd units, production environment
  template, and installer shared by compute and mirror hosts.

See `deploy/README.md` for Linux installation and
`../docs/CLIENT_ONBOARDING.md` for enrollment and forwarding setup.
