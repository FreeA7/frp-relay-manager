from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.openvpn_status import read_openvpn_status
from test_api_flow import make_settings


STATUS = """TITLE,OpenVPN 2.6.14 x86_64-pc-linux-gnu
TIME,2026-07-31 12:00:00,1785460800
HEADER,CLIENT_LIST,Common Name,Real Address,Virtual Address,Virtual IPv6 Address,Bytes Received,Bytes Sent,Connected Since,Connected Since (time_t),Username,Client ID,Peer ID,Data Channel Cipher
CLIENT_LIST,xj01-edge-core,203.0.113.20:45678,10.254.0.2,,1024,2048,2026-07-31 11:55:00,1785460500,UNDEF,0,0,AES-256-GCM
HEADER,ROUTING_TABLE,Virtual Address,Common Name,Real Address,Last Ref,Last Ref (time_t)
ROUTING_TABLE,10.254.0.2,xj01-edge-core,203.0.113.20:45678,2026-07-31 12:00:00,1785460800
GLOBAL_STATS,Max bcast/mcast queue length,0
END
"""


@pytest.mark.parametrize(
    "status_text",
    [STATUS, STATUS.replace(",", "\t")],
    ids=["comma-separated", "tab-separated"],
)
def test_reads_status_v3(monkeypatch, tmp_path: Path, status_text: str):
    (tmp_path / "core.status").write_text(status_text, encoding="utf-8")
    observed_at = datetime.fromtimestamp(1785460810, tz=timezone.utc)
    monkeypatch.setattr("app.openvpn_status.datetime", FrozenDateTime(observed_at))

    result = read_openvpn_status(tmp_path, stale_after_seconds=30)

    assert result["online_tunnel_count"] == 1
    assert result["connected_client_count"] == 1
    core = result["tunnels"][0]
    assert core["status"] == "online"
    assert core["clients"][0]["common_name"] == "xj01-edge-core"
    assert core["clients"][0]["virtual_address"] == "10.254.0.2"
    assert core["clients"][0]["bytes_sent"] == 2048
    assert result["tunnels"][1]["status"] == "unavailable"
    assert result["tunnels"][2]["id"] == "backup"
    assert result["tunnels"][2]["network"] == "10.254.0.16/29"
    assert result["tunnels"][2]["status"] == "unavailable"


def test_endpoint_requires_existing_admin_login(tmp_path: Path):
    settings = make_settings(tmp_path)
    app = create_app(settings)

    with TestClient(app) as client:
        assert client.get("/api/openvpn/status").status_code == 401
        login = client.post(
            "/api/auth/login",
            json={"email": settings.admin_email, "password": settings.admin_password},
        )
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        response = client.get("/api/openvpn/status", headers=headers)
        assert response.status_code == 200
        assert response.json()["tunnel_count"] == 3


class FrozenDateTime:
    def __init__(self, value: datetime):
        self.value = value

    def now(self, tz=None):
        return self.value

    def fromtimestamp(self, value, tz=None):
        return datetime.fromtimestamp(value, tz=tz)
