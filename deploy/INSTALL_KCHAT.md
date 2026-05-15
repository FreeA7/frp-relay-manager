# Install on kchat

Run these steps on `kchat` after syncing `server/` and `deploy/`.

## Prepare secrets

Create `/src/frp_relay/.env` from `server/.env.example` and replace every
placeholder with a strong random value.

Never print DNSPod credentials or generated service tokens in terminal logs.

## Backend

```bash
cd /src/frp_relay/server/backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

The API service template expects:

```bash
/src/frp_relay/server/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010
```

## Frontend

Install Node LTS on the server before building the frontend.

```bash
cd /src/frp_relay/server/frontend
npm install
npm run build
```

nginx serves `/src/frp_relay/server/frontend/dist`.

## frps

Install the verified frp release, then copy `deploy/frp/frps.toml.example` to
`deploy/frp/frps.toml`. frp renders `{{ .Envs.* }}` values from the systemd
environment file at startup, so keep the real token and dashboard password in
`/src/frp_relay/.env`.

Keep the dashboard bound to `127.0.0.1:7500`.
The HTTP tunnel vhost uses `8080` so it does not collide with nginx on `80/443`;
nginx proxies wildcard tunnel domains to this local frps vhost.

## systemd

Copy templates into `/etc/systemd/system/` without the `.example` suffix:

```bash
cp /src/frp_relay/deploy/systemd/frp-relay-api.service.example /etc/systemd/system/frp-relay-api.service
cp /src/frp_relay/deploy/systemd/frps.service.example /etc/systemd/system/frps.service
systemctl daemon-reload
systemctl enable --now frp-relay-api.service frps.service
```

## nginx

Install the panel site without touching the existing `api.freea7.fun` config:

```bash
cp /src/frp_relay/deploy/nginx/panel.tunnel.freea7.fun.conf.example /etc/nginx/sites-available/panel.tunnel.freea7.fun
ln -s /etc/nginx/sites-available/panel.tunnel.freea7.fun /etc/nginx/sites-enabled/panel.tunnel.freea7.fun
cp /src/frp_relay/deploy/nginx/wildcard.tunnel.freea7.fun.conf.example /etc/nginx/sites-available/wildcard.tunnel.freea7.fun
ln -s /etc/nginx/sites-available/wildcard.tunnel.freea7.fun /etc/nginx/sites-enabled/wildcard.tunnel.freea7.fun
nginx -t
systemctl reload nginx
```

## Verify

```bash
curl -fsS http://127.0.0.1:8010/health
curl -fsS https://panel.tunnel.freea7.fun/health
systemctl is-active frp-relay-api.service
systemctl is-active frps.service
systemctl is-active vps-openai-relay.service
```

If nginx returns 500 for the panel, check parent directory permissions with:

```bash
namei -l /src/frp_relay/server/frontend/dist/index.html
```

nginx needs execute permission on each parent directory. Do not recursively set
all files under `.venv` to `644`, because systemd must execute uvicorn from the
virtualenv.
