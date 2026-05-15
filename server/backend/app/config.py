from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional


def _read_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _first_existing(paths: Iterable[Optional[Path]]) -> Optional[Path]:
    for path in paths:
        if path and path.exists():
            return path
    return None


def _bool(value: str, default: bool = False) -> bool:
    if value == "":
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_dir: Path
    database_path: Path
    admin_email: str
    admin_password: str
    reset_admin_password: bool
    secret_key: str
    access_token_ttl_minutes: int
    agent_token_ttl_days: int
    allowed_origins: List[str]
    public_ip: str
    base_domain: str
    panel_domain: str
    frps_addr: str
    frps_bind_port: int
    frps_dashboard_addr: str
    frps_dashboard_port: int
    frps_vhost_http_port: int
    frps_token: str
    remote_port_min: int
    remote_port_max: int


def load_settings(env_file: Optional[Path] = None) -> Settings:
    package_root = Path(__file__).resolve().parents[1]
    project_root = Path(__file__).resolve().parents[3]

    explicit_env = Path(os.environ["FRP_RELAY_ENV_FILE"]) if os.environ.get("FRP_RELAY_ENV_FILE") else None
    selected_env = env_file or explicit_env or _first_existing(
        [
            Path.cwd() / ".env",
            Path.cwd().parent / ".env",
            package_root / ".env",
            package_root.parent / ".env",
            project_root / ".env",
        ]
    )
    file_values = _read_env_file(selected_env) if selected_env else {}

    def get(name: str, default: str = "") -> str:
        return os.environ.get(name, file_values.get(name, default))

    data_dir = Path(get("FRP_RELAY_DATA_DIR", str(project_root / "data"))).resolve()
    database_path = Path(get("FRP_RELAY_DATABASE", str(data_dir / "frp_relay.db"))).resolve()

    return Settings(
        project_root=project_root,
        data_dir=data_dir,
        database_path=database_path,
        admin_email=get("FRP_RELAY_ADMIN_EMAIL", "freea7@futurememetech.com"),
        admin_password=get("FRP_RELAY_ADMIN_PASSWORD", "change-me-now"),
        reset_admin_password=_bool(get("FRP_RELAY_RESET_ADMIN_PASSWORD", "false")),
        secret_key=get("FRP_RELAY_SECRET_KEY", "dev-only-change-this-secret"),
        access_token_ttl_minutes=int(get("FRP_RELAY_ACCESS_TOKEN_TTL_MINUTES", "720")),
        agent_token_ttl_days=int(get("FRP_RELAY_AGENT_TOKEN_TTL_DAYS", "90")),
        allowed_origins=[item.strip() for item in get("FRP_RELAY_ALLOWED_ORIGINS", "*").split(",") if item.strip()],
        public_ip=get("FRP_RELAY_PUBLIC_IP", "45.141.136.217"),
        base_domain=get("FRP_RELAY_BASE_DOMAIN", "tunnel.freea7.fun"),
        panel_domain=get("FRP_RELAY_PANEL_DOMAIN", "panel.tunnel.freea7.fun"),
        frps_addr=get("FRP_RELAY_FRPS_ADDR", "45.141.136.217"),
        frps_bind_port=int(get("FRP_RELAY_FRPS_BIND_PORT", "7000")),
        frps_dashboard_addr=get("FRP_RELAY_FRPS_DASHBOARD_ADDR", "127.0.0.1"),
        frps_dashboard_port=int(get("FRP_RELAY_FRPS_DASHBOARD_PORT", "7500")),
        frps_vhost_http_port=int(get("FRP_RELAY_FRPS_VHOST_HTTP_PORT", "8080")),
        frps_token=get("FRP_RELAY_FRPS_TOKEN", "change-me-frps-token"),
        remote_port_min=int(get("FRP_RELAY_REMOTE_PORT_MIN", "20000")),
        remote_port_max=int(get("FRP_RELAY_REMOTE_PORT_MAX", "49999")),
    )
