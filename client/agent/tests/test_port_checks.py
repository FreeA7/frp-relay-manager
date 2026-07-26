import subprocess
import socket
import stat
import threading

import pytest

from frp_relay_agent import AgentConfig
from frp_relay_agent import check_tcp
from frp_relay_agent import detect_hardware
from frp_relay_agent import frpc_reload_pending_path
from frp_relay_agent import hardware_from_config
from frp_relay_agent import inventory_payload
from frp_relay_agent import read_env_file
from frp_relay_agent import release_summary
from frp_relay_agent import render_frpc_config
from frp_relay_agent import sync_frpc_config
from frp_relay_agent import write_json


def test_check_tcp_reads_banner():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def handle():
        connection, _ = server.accept()
        with connection:
            connection.sendall(b"hello\r\n")
        server.close()

    thread = threading.Thread(target=handle)
    thread.start()

    result = check_tcp("127.0.0.1", port)
    thread.join(timeout=2)

    assert result["listening"] is True
    assert result["banner"] == "hello"


def test_render_frpc_config():
    rendered = render_frpc_config(
        {"server_addr": "45.141.136.217", "server_port": 7000, "auth_token": "token"},
        [
            {
                "id": "abc",
                "protocol": "tcp",
                "local_ip": "127.0.0.1",
                "local_port": 22,
                "remote_port": 20000,
                "subdomain": None,
            },
            {
                "id": "web",
                "protocol": "http",
                "local_ip": "127.0.0.1",
                "local_port": 8080,
                "remote_port": None,
                "subdomain": "dev-web",
            },
        ],
    )

    assert 'serverAddr = "45.141.136.217"' in rendered
    assert "remotePort = 20000" in rendered
    assert 'subdomain = "dev-web"' in rendered


def test_hardware_from_config_ignores_blank_and_invalid_values():
    values = {
        "FRP_RELAY_HARDWARE_CPU_MODEL": "Intel Core i5",
        "FRP_RELAY_HARDWARE_GPU_MODEL": "",
        "FRP_RELAY_HARDWARE_MEMORY_TOTAL_BYTES": "17179869184",
        "FRP_RELAY_HARDWARE_DISK_TOTAL_BYTES": "not-a-number",
        "FRP_RELAY_HARDWARE_OS_VERSION": "Ubuntu 24.04.4",
    }

    hardware = hardware_from_config(lambda name, default="": values.get(name, default), detected={})

    assert hardware == {
        "cpu_model": "Intel Core i5",
        "memory_total_bytes": 17179869184,
        "os_version": "Ubuntu 24.04.4",
    }


def test_hardware_from_config_keeps_detection_and_applies_overrides():
    detected = {
        "cpu_model": "Detected CPU",
        "gpu_model": "Detected GPU",
        "memory_total_bytes": 8589934592,
        "disk_total_bytes": 256000000000,
        "os_version": "Detected OS",
    }
    values = {
        "FRP_RELAY_HARDWARE_CPU_MODEL": "Configured CPU",
        "FRP_RELAY_HARDWARE_DISK_TOTAL_BYTES": "512000000000",
    }

    hardware = hardware_from_config(lambda name, default="": values.get(name, default), detected=detected)

    assert hardware == {
        **detected,
        "cpu_model": "Configured CPU",
        "disk_total_bytes": 512000000000,
    }


def test_detect_hardware_collects_host_capacity_and_os():
    hardware = detect_hardware()

    assert hardware["memory_total_bytes"] > 0
    assert hardware["disk_total_bytes"] > 0
    assert hardware["os_version"]


def test_read_env_file_only_removes_paired_outer_quotes(tmp_path):
    env_path = tmp_path / "agent.env"
    env_path.write_text(
        "FRP_RELAY_FRPC_RELOAD_CMD=pkill -f '[f]rpc -c /opt/frp/frpc.generated.toml'\n"
        'QUOTED_VALUE="hello world"\n'
        "SINGLE_QUOTED_VALUE='hello again'\n",
        encoding="utf-8",
    )

    values = read_env_file(env_path)

    assert values["FRP_RELAY_FRPC_RELOAD_CMD"] == "pkill -f '[f]rpc -c /opt/frp/frpc.generated.toml'"
    assert values["QUOTED_VALUE"] == "hello world"
    assert values["SINGLE_QUOTED_VALUE"] == "hello again"


def test_inventory_payload_reads_identity_releases_and_tenant_binding(tmp_path, monkeypatch):
    identity_path = tmp_path / "device-identity.json"
    hardware_release_path = tmp_path / "hardware-release.json"
    client_release_path = tmp_path / "frp-release.json"
    tenant_binding_path = tmp_path / "tenant-binding.json"
    identity_path.write_text(
        '{"deviceId":"da-compute_terminal-stable","deviceType":"compute_terminal"}',
        encoding="utf-8",
    )
    hardware_release_path.write_text(
        '{"product":"compute","version":"1.2.3","gitTag":"compute-v1.2.3"}',
        encoding="utf-8",
    )
    client_release_path.write_text(
        '{"product":"frp-client","version":"0.4.0-rc.1"}',
        encoding="utf-8",
    )
    tenant_binding_path.write_text('{"deviceUuid":"tenant-device-uuid"}', encoding="utf-8")
    config = AgentConfig(
        server_url="https://panel.tunnel.freea7.fun",
        enrollment_token=None,
        agent_token="agent-token",
        client_id="client-id",
        heartbeat_interval_seconds=30,
        state_path=tmp_path / "agent-state.json",
        frpc_config_path=tmp_path / "frpc.generated.toml",
        frpc_reload_cmd=None,
        hardware={},
        device_identity_path=identity_path,
        hardware_release_path=hardware_release_path,
        client_release_path=client_release_path,
        tenant_binding_path=tenant_binding_path,
        frpc_binary_path=tmp_path / "frpc",
    )

    monkeypatch.setattr(
        "frp_relay_agent.command_output",
        lambda command: "0.68.1" if command[-1] == "--version" else "active",
    )

    inventory = inventory_payload(config)

    assert inventory["device_id"] == "da-compute_terminal-stable"
    assert inventory["device_type"] == "compute_terminal"
    assert inventory["tenant_device_uuid"] == "tenant-device-uuid"
    assert inventory["hardware_release"]["version"] == "1.2.3"
    assert inventory["frp_client_release"]["version"] == "0.4.0-rc.1"
    assert inventory["frpc_version"] == "0.68.1"
    assert inventory["frpc_status"] == "running"


def test_release_summary_rejects_incomplete_or_invalid_json(tmp_path):
    invalid = tmp_path / "invalid.json"
    incomplete = tmp_path / "incomplete.json"
    invalid.write_text("not json", encoding="utf-8")
    incomplete.write_text('{"product":"compute"}', encoding="utf-8")

    assert release_summary(invalid) == {}
    assert release_summary(incomplete) == {}


def test_write_json_protects_agent_state(tmp_path):
    state_path = tmp_path / "agent-state.json"

    write_json(state_path, {"agent_token": "secret"})

    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600


def test_sync_frpc_config_retries_failed_reload(tmp_path, monkeypatch):
    config_path = tmp_path / "frpc.generated.toml"
    config = AgentConfig(
        server_url="https://panel.tunnel.freea7.fun",
        enrollment_token=None,
        agent_token="agent-token",
        client_id="client-id",
        heartbeat_interval_seconds=30,
        state_path=tmp_path / "agent-state.json",
        frpc_config_path=config_path,
        frpc_reload_cmd="reload-frpc",
        hardware={},
    )
    frpc = {"server_addr": "45.141.136.217", "server_port": 7000, "auth_token": "token"}
    forwards = [
        {
            "id": "voice",
            "protocol": "tcp",
            "local_ip": "127.0.0.1",
            "local_port": 26221,
            "remote_port": 26789,
            "subdomain": None,
        }
    ]
    calls = []

    def failed_reload(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], 2, stdout="", stderr="invalid command")

    monkeypatch.setattr("frp_relay_agent.subprocess.run", failed_reload)

    with pytest.raises(RuntimeError, match="exit code 2: invalid command"):
        sync_frpc_config(config, frpc, forwards)

    pending_path = frpc_reload_pending_path(config_path)
    assert config_path.exists()
    assert pending_path.exists()
    assert len(calls) == 1

    def successful_reload(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")

    monkeypatch.setattr("frp_relay_agent.subprocess.run", successful_reload)
    sync_frpc_config(config, frpc, forwards)

    assert len(calls) == 2
    assert not pending_path.exists()
