from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.security import utc_now


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
        fleet_read_token="fleet-read-token-0123456789abcdef",
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
                "inventory": {
                    "device_id": "da-compute_terminal-stable",
                    "device_type": "compute_terminal",
                    "agent_protocol_version": "2",
                    "frpc_version": "0.68.1",
                    "frpc_status": "running",
                    "frp_client_release": {"product": "frp-client", "version": "0.4.0-rc.1"},
                    "tenant_device_uuid": "tenant-device-uuid",
                },
                "hardware": {
                    "cpu_model": "Intel Core i5",
                    "gpu_model": "Intel UHD",
                    "memory_total_bytes": 17179869184,
                    "disk_total_bytes": 512110190592,
                    "os_version": "Windows 11 Pro",
                },
            },
            headers={"X-Real-IP": "203.0.113.10"},
        )
        assert registered.status_code == 200
        client_id = registered.json()["client_id"]
        agent_headers = {"Authorization": "Bearer " + registered.json()["agent_token"]}

        listed_after_register = client.get("/api/clients", headers=admin_headers)
        assert listed_after_register.status_code == 200
        assert listed_after_register.json()["items"][0]["name"] == "devbox"
        assert listed_after_register.json()["items"][0]["last_remote_ip"] == "203.0.113.10"
        assert listed_after_register.json()["items"][0]["hardware"]["cpu_model"] == "Intel Core i5"
        assert listed_after_register.json()["items"][0]["hardware"]["memory_total_bytes"] == 17179869184

        fleet_without_token = client.get("/api/integrations/fleet/clients")
        assert fleet_without_token.status_code == 401
        fleet_snapshot = client.get(
            "/api/integrations/fleet/clients",
            headers={"Authorization": "Bearer fleet-read-token-0123456789abcdef"},
        )
        assert fleet_snapshot.status_code == 200
        fleet_client = fleet_snapshot.json()["clients"][0]
        assert fleet_client["device_id"] == "da-compute_terminal-stable"
        assert fleet_client["frpc_version"] == "0.68.1"
        assert fleet_client["frp_client_release"] == "0.4.0-rc.1"
        assert fleet_client["tenant_device_uuid"] == "tenant-device-uuid"

        heartbeat = client.post(
            "/api/agent/heartbeat",
            json={
                "hostname": "renamed-devbox",
                "os": "Windows",
                "ips": ["127.0.0.1"],
                "hardware": {
                    "cpu_model": "Intel Core i7",
                    "gpu_model": "NVIDIA RTX 4060",
                    "memory_total_bytes": 34359738368,
                    "disk_total_bytes": 1024209543168,
                    "os_version": "Windows 11 Pro 24H2",
                },
                "inventory": {
                    "device_id": "da-compute_terminal-stable",
                    "device_type": "compute_terminal",
                    "agent_protocol_version": "2",
                    "frpc_version": "0.68.2",
                    "frpc_status": "running",
                    "hardware_release": {"product": "compute", "version": "1.0.0-rc.1"},
                    "frp_client_release": {"product": "frp-client", "version": "0.4.0-rc.1"},
                    "tenant_device_uuid": "tenant-device-uuid",
                },
            },
            headers={**agent_headers, "X-Real-IP": "203.0.113.11"},
        )
        assert heartbeat.status_code == 200

        listed_after_heartbeat = client.get("/api/clients", headers=admin_headers)
        assert listed_after_heartbeat.status_code == 200
        assert listed_after_heartbeat.json()["items"][0]["name"] == "renamed-devbox"
        assert listed_after_heartbeat.json()["items"][0]["last_remote_ip"] == "203.0.113.11"
        assert listed_after_heartbeat.json()["items"][0]["last_remote_ip_seen_at"]
        assert listed_after_heartbeat.json()["items"][0]["hardware"]["cpu_model"] == "Intel Core i7"
        assert listed_after_heartbeat.json()["items"][0]["hardware"]["gpu_model"] == "NVIDIA RTX 4060"
        assert listed_after_heartbeat.json()["items"][0]["hardware"]["disk_total_bytes"] == 1024209543168
        assert listed_after_heartbeat.json()["items"][0]["hardware"]["updated_at"]

        fleet_after_heartbeat = client.get(
            "/api/integrations/fleet/clients",
            headers={"Authorization": "Bearer fleet-read-token-0123456789abcdef"},
        ).json()["clients"][0]
        assert fleet_after_heartbeat["hardware_release"] == "1.0.0-rc.1"
        assert fleet_after_heartbeat["frpc_version"] == "0.68.2"

        conflicting_identity = client.post(
            "/api/agent/heartbeat",
            json={
                "hostname": "renamed-devbox",
                "os": "Windows",
                "inventory": {"device_id": "da-compute_terminal-different"},
            },
            headers=agent_headers,
        )
        assert conflicting_identity.status_code == 409

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
        remote_port = forward.json()["remote_port"]
        assert 20000 <= remote_port <= 20010
        assert forward.json()["note"] == "默认 SSH"
        assert f"45.141.136.217:{remote_port}" in forward.json()["public_addresses"]

        tasks_after_forward = client.get("/api/agent/tasks", headers=agent_headers)
        assert tasks_after_forward.status_code == 200
        assert tasks_after_forward.json()["forwards"][0]["remote_port"] == remote_port


def test_stale_heartbeat_is_reported_offline(tmp_path):
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
            json={"label": "stale test", "expires_in_hours": 1},
            headers=admin_headers,
        )
        assert enrollment.status_code == 200

        registered = client.post(
            "/api/agent/register",
            json={
                "enrollment_token": enrollment.json()["token"],
                "hostname": "ali",
                "os": "Linux",
                "ips": ["127.0.0.1"],
            },
        )
        assert registered.status_code == 200
        client_id = registered.json()["client_id"]

        stale_seen_at = (utc_now() - timedelta(minutes=10)).isoformat()
        app.state.repo.execute(
            "UPDATE clients SET last_seen_at = ?, status = 'online' WHERE client_id = ?",
            (stale_seen_at, client_id),
        )

        listed = client.get("/api/clients", headers=admin_headers)
        assert listed.status_code == 200
        assert listed.json()["items"][0]["status"] == "offline"

        dashboard = client.get("/api/dashboard", headers=admin_headers)
        assert dashboard.status_code == 200
        assert dashboard.json()["client_count"] == 1
        assert dashboard.json()["online_client_count"] == 0
