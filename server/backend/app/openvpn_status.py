from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


TUNNELS = (
    ("core", "Core", "10.254.0.0/29"),
    ("engine", "Engine", "10.254.0.8/29"),
)


def read_openvpn_status(status_dir: Path, stale_after_seconds: int) -> Dict[str, Any]:
    observed_at = datetime.now(timezone.utc)
    tunnels = [
        _read_tunnel(status_dir / f"{tunnel_id}.status", tunnel_id, label, network, observed_at, stale_after_seconds)
        for tunnel_id, label, network in TUNNELS
    ]
    return {
        "observed_at": observed_at.isoformat(),
        "tunnel_count": len(tunnels),
        "online_tunnel_count": sum(1 for tunnel in tunnels if tunnel["status"] == "online"),
        "connected_client_count": sum(tunnel["connected_client_count"] for tunnel in tunnels),
        "tunnels": tunnels,
    }


def _read_tunnel(
    path: Path,
    tunnel_id: str,
    label: str,
    network: str,
    observed_at: datetime,
    stale_after_seconds: int,
) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "id": tunnel_id,
        "label": label,
        "network": network,
        "status": "unavailable",
        "last_update": None,
        "age_seconds": None,
        "connected_client_count": 0,
        "clients": [],
        "error": None,
    }
    try:
        stat = path.stat()
        rows = list(csv.reader(path.read_text(encoding="utf-8", errors="replace").splitlines()))
    except FileNotFoundError:
        base["error"] = "status file is missing"
        return base
    except OSError:
        base["error"] = "status file is unreadable"
        return base

    updated_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    clients: List[Dict[str, Any]] = []
    headers: Dict[str, List[str]] = {}
    for row in rows:
        if len(row) >= 3 and row[0] == "TIME":
            try:
                updated_at = datetime.fromtimestamp(int(row[2]), tz=timezone.utc)
            except (TypeError, ValueError, OSError):
                pass
        elif len(row) >= 3 and row[0] == "HEADER":
            headers[row[1]] = row[2:]
        elif len(row) >= 2 and row[0] == "CLIENT_LIST":
            clients.append(_format_client(headers.get("CLIENT_LIST", []), row[1:], observed_at))

    age_seconds = max(0, int((observed_at - updated_at).total_seconds()))
    base.update(
        {
            "status": "online" if age_seconds <= stale_after_seconds else "stale",
            "last_update": updated_at.isoformat(),
            "age_seconds": age_seconds,
            "connected_client_count": len(clients),
            "clients": clients,
        }
    )
    return base


def _format_client(headers: List[str], values: List[str], observed_at: datetime) -> Dict[str, Any]:
    row = dict(zip(headers, values))
    connected_at = _timestamp(row.get("Connected Since (time_t)"))
    return {
        "common_name": row.get("Common Name") or "unknown",
        "virtual_address": row.get("Virtual Address") or None,
        "remote_address": row.get("Real Address") or None,
        "bytes_received": _integer(row.get("Bytes Received")),
        "bytes_sent": _integer(row.get("Bytes Sent")),
        "connected_since": connected_at.isoformat() if connected_at else row.get("Connected Since") or None,
        "uptime_seconds": max(0, int((observed_at - connected_at).total_seconds())) if connected_at else None,
        "cipher": row.get("Data Channel Cipher") or None,
    }


def _integer(value: str | None) -> int:
    try:
        return int(value or 0)
    except ValueError:
        return 0


def _timestamp(value: str | None) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value or ""), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
