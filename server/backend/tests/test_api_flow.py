from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "test.db",
        admin_email="freea7@futurememetech.com",
        admin_password="test-password",
        reset_admin_password=False,
        secret_key="test-secret",
        access_token_ttl_minutes=60,
        agent_token_ttl_days=7,
        allowed_origins=["*"],
        public_ip="45.141.136.217",
        base_domain="tunnel.freea7.fun",
        panel_domain="panel.tunnel.freea7.fun",
        frps_addr="45.141.136.217",
        frps_bind_port=7000,
        frps_dashboard_addr="127.0.0.1",
        frps_dashboard_port=7500,
        frps_vhost_http_port=8080,
        frps_token="frps-token",
        remote_port_min=20000,
        remote_port_max=20010,
    )


def test_admin_agent_forward_flow(tmp_path):
    app = create_app(make_settings(tmp_path))

    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={"email": "freea7@futurememetech.com", "password": "test-password"},
        )
        assert login.status_code == 200
        admin_headers = {"Authorization": "Bearer " + login.json()["access_token"]}

        enrollment = client.post(
            "/api/enrollment-tokens",
            json={"label": "local test", "expires_in_hours": 1},
            headers=admin_headers,
        )
        assert enrollment.status_code == 200

        registered = client.post(
            "/api/agent/register",
            json={
                "enrollment_token": enrollment.json()["token"],
                "name": "ignored-custom-name",
                "hostname": "devbox",
                "os": "Windows",
                "ips": ["127.0.0.1"],
                "agent_version": "test",
            },
        )
        assert registered.status_code == 200
        client_id = registered.json()["client_id"]
        agent_headers = {"Authorization": "Bearer " + registered.json()["agent_token"]}

        listed_after_register = client.get("/api/clients", headers=admin_headers)
        assert listed_after_register.status_code == 200
        assert listed_after_register.json()["items"][0]["name"] == "devbox"

        heartbeat = client.post(
            "/api/agent/heartbeat",
            json={"hostname": "renamed-devbox", "os": "Windows", "ips": ["127.0.0.1"], "frpc_status": "running"},
            headers=agent_headers,
        )
        assert heartbeat.status_code == 200

        listed_after_heartbeat = client.get("/api/clients", headers=admin_headers)
        assert listed_after_heartbeat.status_code == 200
        assert listed_after_heartbeat.json()["items"][0]["name"] == "renamed-devbox"

        check = client.post(
            "/api/port-checks",
            json={"client_id": client_id, "protocol": "tcp", "host": "127.0.0.1", "port": 22},
            headers=admin_headers,
        )
        assert check.status_code == 200

        tasks = client.get("/api/agent/tasks", headers=agent_headers)
        assert tasks.status_code == 200
        assert len(tasks.json()["port_checks"]) == 1
        assert tasks.json()["frpc"]["server_addr"] == "45.141.136.217"

        result = client.post(
            "/api/agent/port-check-results",
            json={"task_id": check.json()["id"], "listening": False, "detail": {"banner": ""}},
            headers=agent_headers,
        )
        assert result.status_code == 200

        forward = client.post(
            "/api/forwards",
            json={"client_id": client_id, "protocol": "tcp", "local_port": 22, "note": "ssh"},
            headers=admin_headers,
        )
        assert forward.status_code == 200
        assert forward.json()["remote_port"] == 20000
        assert "45.141.136.217:20000" in forward.json()["public_addresses"]

        tasks_after_forward = client.get("/api/agent/tasks", headers=agent_headers)
        assert tasks_after_forward.status_code == 200
        assert tasks_after_forward.json()["forwards"][0]["remote_port"] == 20000
