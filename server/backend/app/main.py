from __future__ import annotations

import hmac
import json
import ipaddress
import re
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import Settings, load_settings
from .repository import Repository
from .openvpn_status import read_openvpn_status
from .security import (
    create_signed_token,
    generate_secret_urlsafe,
    hash_secret,
    utc_iso,
    verify_password,
    verify_signed_token,
)


PROTOCOLS = {"tcp", "udp", "http"}
FORWARD_STATUSES = {"active", "paused"}
RESERVED_PORTS = {22, 80, 443, 7000, 7500, 8000, 8010}
CLIENT_ONLINE_GRACE_SECONDS = 120
DEFAULT_SSH_FORWARD_NOTE = "默认 SSH"
SERVICE_VERSION = "0.3.0-rc.2"


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class EnrollmentTokenCreate(BaseModel):
    label: Optional[str] = None
    expires_in_hours: int = Field(default=24, ge=1, le=24 * 30)


class EnrollmentTokenResponse(BaseModel):
    id: str
    token: str
    label: Optional[str]
    expires_at: str


class AgentHardware(BaseModel):
    cpu_model: Optional[str] = None
    gpu_model: Optional[str] = None
    memory_total_bytes: Optional[int] = Field(default=None, ge=0)
    disk_total_bytes: Optional[int] = Field(default=None, ge=0)
    os_version: Optional[str] = None


class AgentInventory(BaseModel):
    device_id: Optional[str] = Field(default=None, max_length=128)
    device_type: Optional[str] = Field(default=None, max_length=64)
    agent_protocol_version: Optional[str] = Field(default=None, max_length=80)
    frpc_version: Optional[str] = Field(default=None, max_length=80)
    frpc_status: Optional[str] = Field(default=None, max_length=32)
    hardware_release: Optional[Dict[str, Any]] = None
    frp_client_release: Optional[Dict[str, Any]] = None
    tenant_device_uuid: Optional[str] = Field(default=None, max_length=128)
    observation_updated_at: Optional[str] = Field(default=None, max_length=80)


class AgentRegisterRequest(BaseModel):
    enrollment_token: str
    hostname: str
    os: str
    arch: Optional[str] = None
    ips: List[str] = Field(default_factory=list)
    agent_version: Optional[str] = None
    hardware: Optional[AgentHardware] = None
    inventory: Optional[AgentInventory] = None


class AgentRegisterResponse(BaseModel):
    client_id: str
    agent_token: str
    heartbeat_interval_seconds: int = 30


class AgentHeartbeatRequest(BaseModel):
    hostname: str
    os: str
    arch: Optional[str] = None
    ips: List[str] = Field(default_factory=list)
    agent_version: Optional[str] = None
    hardware: Optional[AgentHardware] = None
    inventory: Optional[AgentInventory] = None


class PortCheckCreate(BaseModel):
    client_id: str
    protocol: str = "tcp"
    host: str = "127.0.0.1"
    port: int = Field(ge=1, le=65535)


class PortCheckResult(BaseModel):
    task_id: str
    status: str = "completed"
    listening: bool = False
    detail: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class ForwardCreate(BaseModel):
    client_id: str
    protocol: str
    local_ip: str = "127.0.0.1"
    local_port: int = Field(ge=1, le=65535)
    remote_port: Optional[int] = Field(default=None, ge=1, le=65535)
    subdomain: Optional[str] = None
    note: Optional[str] = None


class ForwardUpdate(BaseModel):
    status: Optional[str] = None
    note: Optional[str] = None


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    resolved_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI):
        repo: Repository = app.state.repo
        repo.init_db()
        repo.ensure_admin(
            user_id="admin",
            email=resolved_settings.admin_email,
            password=resolved_settings.admin_password,
            reset_password=resolved_settings.reset_admin_password,
        )
        yield

    app = FastAPI(title="DeepAssess Edge Gateway API", version=SERVICE_VERSION, lifespan=lifespan)
    app.state.settings = resolved_settings
    app.state.repo = Repository(resolved_settings.database_path)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok", "version": SERVICE_VERSION}

    @app.get("/api/integrations/fleet/clients")
    def fleet_clients(
        repo: Repository = Depends(get_repo),
        fleet_reader: None = Depends(require_fleet_reader),
    ) -> Dict[str, Any]:
        del fleet_reader
        rows = repo.fetchall("SELECT * FROM clients ORDER BY hostname, created_at")
        return {"observed_at": utc_iso(), "clients": [format_fleet_client(row) for row in rows]}

    @app.post("/api/auth/login", response_model=TokenResponse)
    def login(payload: LoginRequest, repo: Repository = Depends(get_repo), settings_dep: Settings = Depends(get_settings)) -> TokenResponse:
        user = repo.fetchone("SELECT * FROM users WHERE email = ?", (payload.email,))
        if not user or not verify_password(payload.password, user["password_hash"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

        token = create_signed_token(
            settings_dep.secret_key,
            subject=user["id"],
            token_type="admin",
            expires_delta=timedelta(minutes=settings_dep.access_token_ttl_minutes),
            extra={"email": user["email"]},
        )
        return TokenResponse(access_token=token)

    @app.get("/api/me")
    def me(admin: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
        return {"id": admin["sub"], "email": admin.get("email")}

    @app.get("/api/dashboard")
    def dashboard(
        repo: Repository = Depends(get_repo),
        settings_dep: Settings = Depends(get_settings),
        admin: Dict[str, Any] = Depends(require_admin),
    ) -> Dict[str, Any]:
        clients = repo.fetchall("SELECT * FROM clients ORDER BY last_seen_at DESC, created_at DESC")
        forwards = repo.fetchall("SELECT * FROM forwards ORDER BY created_at DESC")
        pending_checks = repo.fetchall("SELECT * FROM port_check_tasks WHERE status = 'pending' ORDER BY created_at DESC")
        formatted_clients = [format_client(client) for client in clients]
        return {
            "client_count": len(clients),
            "online_client_count": len([client for client in formatted_clients if client["status"] == "online"]),
            "forward_count": len(forwards),
            "pending_port_check_count": len(pending_checks),
            "public_ip": settings_dep.public_ip,
            "base_domain": settings_dep.base_domain,
            "panel_domain": settings_dep.panel_domain,
        }

    @app.get("/api/openvpn/status")
    def openvpn_status(
        settings_dep: Settings = Depends(get_settings),
        admin: Dict[str, Any] = Depends(require_admin),
    ) -> Dict[str, Any]:
        del admin
        return read_openvpn_status(
            settings_dep.openvpn_status_dir,
            settings_dep.openvpn_status_stale_seconds,
        )

    @app.post("/api/enrollment-tokens", response_model=EnrollmentTokenResponse)
    def create_enrollment_token(
        payload: EnrollmentTokenCreate,
        repo: Repository = Depends(get_repo),
        admin: Dict[str, Any] = Depends(require_admin),
    ) -> EnrollmentTokenResponse:
        token_id = str(uuid.uuid4())
        raw_token = "enr_" + generate_secret_urlsafe(32)
        expires_at = (utc_datetime_plus(hours=payload.expires_in_hours))
        repo.execute(
            """
            INSERT INTO enrollment_tokens (id, token_hash, label, expires_at, used_at, created_at)
            VALUES (?, ?, ?, ?, NULL, ?)
            """,
            (token_id, hash_secret(raw_token), payload.label, expires_at, utc_iso()),
        )
        return EnrollmentTokenResponse(id=token_id, token=raw_token, label=payload.label, expires_at=expires_at)

    @app.post("/api/agent/register", response_model=AgentRegisterResponse)
    def register_agent(
        payload: AgentRegisterRequest,
        request: Request,
        repo: Repository = Depends(get_repo),
        settings_dep: Settings = Depends(get_settings),
    ) -> AgentRegisterResponse:
        token_hash = hash_secret(payload.enrollment_token)
        enrollment = repo.fetchone(
            "SELECT * FROM enrollment_tokens WHERE token_hash = ? AND used_at IS NULL",
            (token_hash,),
        )
        if not enrollment or is_expired(enrollment["expires_at"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid enrollment token")

        client_id = str(uuid.uuid4())
        now = utc_iso()
        remote_ip = request_remote_ip(request)
        hardware = hardware_values(payload.hardware, now)
        repo.execute(
            """
            INSERT INTO clients (
                client_id, name, hostname, os, arch, ips_json, agent_version,
                cpu_model, gpu_model, memory_total_bytes, disk_total_bytes,
                os_version, hardware_updated_at, status, last_seen_at,
                last_remote_ip, last_remote_ip_seen_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_id,
                payload.hostname,
                payload.hostname,
                payload.os,
                payload.arch,
                json.dumps(payload.ips),
                payload.agent_version,
                hardware["cpu_model"],
                hardware["gpu_model"],
                hardware["memory_total_bytes"],
                hardware["disk_total_bytes"],
                hardware["os_version"],
                hardware["hardware_updated_at"],
                "online",
                now,
                remote_ip,
                now if remote_ip else None,
                now,
            ),
        )
        update_client_inventory(repo, client_id, payload.inventory, now)
        repo.execute("UPDATE enrollment_tokens SET used_at = ? WHERE id = ?", (now, enrollment["id"]))
        agent_token = create_signed_token(
            settings_dep.secret_key,
            subject=client_id,
            token_type="agent",
            expires_delta=timedelta(days=settings_dep.agent_token_ttl_days),
        )
        return AgentRegisterResponse(client_id=client_id, agent_token=agent_token)

    @app.post("/api/agent/heartbeat")
    def agent_heartbeat(
        payload: AgentHeartbeatRequest,
        request: Request,
        repo: Repository = Depends(get_repo),
        agent: Dict[str, Any] = Depends(require_agent),
    ) -> Dict[str, str]:
        now = utc_iso()
        remote_ip = request_remote_ip(request)
        hardware = hardware_values(payload.hardware, now)
        if hardware["hardware_updated_at"]:
            repo.execute(
                """
                UPDATE clients
                SET name = ?, hostname = ?, os = ?, arch = ?, ips_json = ?, agent_version = ?,
                    cpu_model = ?, gpu_model = ?, memory_total_bytes = ?, disk_total_bytes = ?,
                    os_version = ?, hardware_updated_at = ?,
                    status = 'online', last_seen_at = ?,
                    last_remote_ip = ?, last_remote_ip_seen_at = ?
                WHERE client_id = ?
                """,
                (
                    payload.hostname,
                    payload.hostname,
                    payload.os,
                    payload.arch,
                    json.dumps(payload.ips),
                    payload.agent_version,
                    hardware["cpu_model"],
                    hardware["gpu_model"],
                    hardware["memory_total_bytes"],
                    hardware["disk_total_bytes"],
                    hardware["os_version"],
                    hardware["hardware_updated_at"],
                    now,
                    remote_ip,
                    now if remote_ip else None,
                    agent["sub"],
                ),
            )
        else:
            repo.execute(
                """
                UPDATE clients
                SET name = ?, hostname = ?, os = ?, arch = ?, ips_json = ?, agent_version = ?,
                    status = 'online', last_seen_at = ?,
                    last_remote_ip = ?, last_remote_ip_seen_at = ?
                WHERE client_id = ?
                """,
                (
                    payload.hostname,
                    payload.hostname,
                    payload.os,
                    payload.arch,
                    json.dumps(payload.ips),
                    payload.agent_version,
                    now,
                    remote_ip,
                    now if remote_ip else None,
                    agent["sub"],
                ),
            )
        update_client_inventory(repo, agent["sub"], payload.inventory, now)
        return {"status": "ok"}

    @app.get("/api/agent/tasks")
    def agent_tasks(
        repo: Repository = Depends(get_repo),
        settings_dep: Settings = Depends(get_settings),
        agent: Dict[str, Any] = Depends(require_agent),
    ) -> Dict[str, Any]:
        client_id = agent["sub"]
        checks = repo.fetchall(
            "SELECT * FROM port_check_tasks WHERE client_id = ? AND status = 'pending' ORDER BY created_at ASC",
            (client_id,),
        )
        forwards = repo.fetchall(
            "SELECT * FROM forwards WHERE client_id = ? AND status = 'active' ORDER BY created_at ASC",
            (client_id,),
        )
        return {
            "frpc": {
                "server_addr": settings_dep.frps_addr,
                "server_port": settings_dep.frps_bind_port,
                "auth_token": settings_dep.frps_token,
            },
            "port_checks": [format_port_check(row) for row in checks],
            "forwards": [format_forward(row, settings_dep) for row in forwards],
        }

    @app.post("/api/agent/port-check-results")
    def submit_port_check_result(
        payload: PortCheckResult,
        repo: Repository = Depends(get_repo),
        agent: Dict[str, Any] = Depends(require_agent),
    ) -> Dict[str, str]:
        task = repo.fetchone(
            "SELECT * FROM port_check_tasks WHERE id = ? AND client_id = ?",
            (payload.task_id, agent["sub"]),
        )
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Port check task not found")

        status_value = "failed" if payload.error or payload.status == "failed" else "completed"
        repo.execute(
            """
            UPDATE port_check_tasks
            SET status = ?, result_json = ?, error = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                status_value,
                json.dumps({"listening": payload.listening, "detail": payload.detail}),
                payload.error,
                utc_iso(),
                payload.task_id,
            ),
        )
        return {"status": "ok"}

    @app.get("/api/clients")
    def list_clients(repo: Repository = Depends(get_repo), admin: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
        rows = repo.fetchall("SELECT * FROM clients ORDER BY last_seen_at DESC, created_at DESC")
        return {"items": [format_client(row) for row in rows]}

    @app.post("/api/port-checks")
    def create_port_check(
        payload: PortCheckCreate,
        repo: Repository = Depends(get_repo),
        admin: Dict[str, Any] = Depends(require_admin),
    ) -> Dict[str, Any]:
        protocol = payload.protocol.lower()
        if protocol not in PROTOCOLS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported protocol")
        ensure_client_exists(repo, payload.client_id)

        task_id = str(uuid.uuid4())
        now = utc_iso()
        repo.execute(
            """
            INSERT INTO port_check_tasks (id, client_id, protocol, host, port, status, result_json, error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'pending', NULL, NULL, ?, ?)
            """,
            (task_id, payload.client_id, protocol, payload.host, payload.port, now, now),
        )
        return format_port_check(repo.fetchone("SELECT * FROM port_check_tasks WHERE id = ?", (task_id,)))

    @app.get("/api/port-checks/{task_id}")
    def get_port_check(
        task_id: str,
        repo: Repository = Depends(get_repo),
        admin: Dict[str, Any] = Depends(require_admin),
    ) -> Dict[str, Any]:
        task = repo.fetchone("SELECT * FROM port_check_tasks WHERE id = ?", (task_id,))
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Port check task not found")
        return format_port_check(task)

    @app.get("/api/forwards")
    def list_forwards(
        repo: Repository = Depends(get_repo),
        settings_dep: Settings = Depends(get_settings),
        admin: Dict[str, Any] = Depends(require_admin),
    ) -> Dict[str, Any]:
        rows = repo.fetchall("SELECT * FROM forwards ORDER BY created_at DESC")
        return {"items": [format_forward(row, settings_dep) for row in rows]}

    @app.post("/api/forwards")
    def create_forward(
        payload: ForwardCreate,
        repo: Repository = Depends(get_repo),
        settings_dep: Settings = Depends(get_settings),
        admin: Dict[str, Any] = Depends(require_admin),
    ) -> Dict[str, Any]:
        protocol = payload.protocol.lower()
        if protocol not in PROTOCOLS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported protocol")
        ensure_client_exists(repo, payload.client_id)

        remote_port = payload.remote_port
        subdomain = payload.subdomain
        if protocol in {"tcp", "udp"}:
            remote_port = remote_port or allocate_remote_port(repo, settings_dep)
            validate_remote_port(repo, settings_dep, remote_port)
        else:
            subdomain = ensure_unique_subdomain(repo, subdomain or default_subdomain(payload.client_id, protocol, payload.local_port))

        note = normalized_forward_note(protocol, payload.local_port, payload.note)
        forward_id = str(uuid.uuid4())
        now = utc_iso()
        repo.execute(
            """
            INSERT INTO forwards (
                id, client_id, protocol, local_ip, local_port, remote_port,
                subdomain, status, note, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (
                forward_id,
                payload.client_id,
                protocol,
                payload.local_ip,
                payload.local_port,
                remote_port,
                subdomain,
                note,
                now,
                now,
            ),
        )
        return format_forward(repo.fetchone("SELECT * FROM forwards WHERE id = ?", (forward_id,)), settings_dep)

    @app.patch("/api/forwards/{forward_id}")
    def update_forward(
        forward_id: str,
        payload: ForwardUpdate,
        repo: Repository = Depends(get_repo),
        settings_dep: Settings = Depends(get_settings),
        admin: Dict[str, Any] = Depends(require_admin),
    ) -> Dict[str, Any]:
        existing = repo.fetchone("SELECT * FROM forwards WHERE id = ?", (forward_id,))
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forward not found")
        if payload.status and payload.status not in FORWARD_STATUSES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported forward status")

        repo.execute(
            """
            UPDATE forwards
            SET status = COALESCE(?, status), note = COALESCE(?, note), updated_at = ?
            WHERE id = ?
            """,
            (payload.status, payload.note, utc_iso(), forward_id),
        )
        return format_forward(repo.fetchone("SELECT * FROM forwards WHERE id = ?", (forward_id,)), settings_dep)

    @app.delete("/api/forwards/{forward_id}")
    def delete_forward(
        forward_id: str,
        repo: Repository = Depends(get_repo),
        admin: Dict[str, Any] = Depends(require_admin),
    ) -> Dict[str, str]:
        existing = repo.fetchone("SELECT id FROM forwards WHERE id = ?", (forward_id,))
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Forward not found")
        repo.execute("DELETE FROM forwards WHERE id = ?", (forward_id,))
        return {"status": "deleted"}

    return app


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_repo(request: Request) -> Repository:
    return request.app.state.repo


def require_admin(
    authorization: Optional[str] = Header(default=None),
    settings_dep: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    token = bearer_token(authorization)
    try:
        return verify_signed_token(settings_dep.secret_key, token, expected_type="admin")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def require_agent(
    authorization: Optional[str] = Header(default=None),
    settings_dep: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    token = bearer_token(authorization)
    try:
        return verify_signed_token(settings_dep.secret_key, token, expected_type="agent")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def require_fleet_reader(
    authorization: Optional[str] = Header(default=None),
    settings_dep: Settings = Depends(get_settings),
) -> None:
    if len(settings_dep.fleet_read_token) < 32:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Fleet integration is disabled")
    supplied = bearer_token(authorization)
    if not hmac.compare_digest(supplied, settings_dep.fleet_read_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Fleet read token")


def bearer_token(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return authorization.split(" ", 1)[1].strip()


def ensure_client_exists(repo: Repository, client_id: str) -> None:
    if not repo.fetchone("SELECT client_id FROM clients WHERE client_id = ?", (client_id,)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")


def allocate_remote_port(repo: Repository, settings: Settings) -> int:
    used = {
        int(row["remote_port"])
        for row in repo.fetchall("SELECT remote_port FROM forwards WHERE remote_port IS NOT NULL")
    }
    candidates = [
        port
        for port in range(settings.remote_port_min, settings.remote_port_max + 1)
        if port not in used and port not in RESERVED_PORTS and port not in settings.reserved_ports
    ]
    if candidates:
        return candidates[secrets.randbelow(len(candidates))]
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No remote ports available")


def normalized_forward_note(protocol: str, local_port: int, note: Optional[str]) -> Optional[str]:
    if protocol == "tcp" and local_port == 22:
        return DEFAULT_SSH_FORWARD_NOTE
    return clean_optional_text(note)


def validate_remote_port(repo: Repository, settings: Settings, remote_port: Optional[int]) -> None:
    if remote_port is None:
        return
    if (
        remote_port < settings.remote_port_min
        or remote_port > settings.remote_port_max
        or remote_port in RESERVED_PORTS
        or remote_port in settings.reserved_ports
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Remote port is outside the allowed pool")
    existing = repo.fetchone("SELECT id FROM forwards WHERE remote_port = ?", (remote_port,))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Remote port is already in use")


def default_subdomain(client_id: str, protocol: str, local_port: int) -> str:
    return slugify("{}-{}-{}".format(client_id[:8], protocol, local_port))


def ensure_unique_subdomain(repo: Repository, requested: str) -> str:
    base = slugify(requested)
    candidate = base
    suffix = 2
    while repo.fetchone("SELECT id FROM forwards WHERE subdomain = ?", (candidate,)):
        candidate = "{}-{}".format(base, suffix)
        suffix += 1
    return candidate


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    if not slug:
        slug = "service"
    return slug[:48]


def is_expired(value: Optional[str]) -> bool:
    if not value:
        return False
    return value < utc_iso()


def hardware_values(hardware: Optional[AgentHardware], updated_at: str) -> Dict[str, Any]:
    if hardware is None:
        return {
            "cpu_model": None,
            "gpu_model": None,
            "memory_total_bytes": None,
            "disk_total_bytes": None,
            "os_version": None,
            "hardware_updated_at": None,
        }

    values = {
        "cpu_model": clean_optional_text(hardware.cpu_model),
        "gpu_model": clean_optional_text(hardware.gpu_model),
        "memory_total_bytes": hardware.memory_total_bytes,
        "disk_total_bytes": hardware.disk_total_bytes,
        "os_version": clean_optional_text(hardware.os_version),
    }
    has_value = any(value not in {None, ""} for value in values.values())
    return {**values, "hardware_updated_at": updated_at if has_value else None}


def release_version(value: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(value, dict):
        return None
    return clean_optional_text(str(value.get("version") or ""))


def update_client_inventory(
    repo: Repository,
    client_id: str,
    inventory: Optional[AgentInventory],
    updated_at: str,
) -> None:
    if inventory is None:
        return
    existing = repo.fetchone("SELECT device_id FROM clients WHERE client_id = ?", (client_id,))
    next_device_id = clean_optional_text(inventory.device_id)
    if existing and existing.get("device_id") and next_device_id not in {None, existing["device_id"]}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stable deviceId cannot change")

    payload = inventory.model_dump(mode="json", exclude_none=True)
    repo.execute(
        """
        UPDATE clients
        SET device_id = COALESCE(?, device_id),
            device_type = ?,
            agent_protocol_version = ?,
            frpc_version = ?,
            frpc_status = ?,
            hardware_release = ?,
            frp_client_release = ?,
            tenant_device_uuid = ?,
            inventory_json = ?,
            observation_updated_at = ?
        WHERE client_id = ?
        """,
        (
            next_device_id,
            clean_optional_text(inventory.device_type),
            clean_optional_text(inventory.agent_protocol_version),
            clean_optional_text(inventory.frpc_version),
            clean_optional_text(inventory.frpc_status),
            release_version(inventory.hardware_release),
            release_version(inventory.frp_client_release),
            clean_optional_text(inventory.tenant_device_uuid),
            json.dumps(payload, ensure_ascii=True),
            clean_optional_text(inventory.observation_updated_at) or updated_at,
            client_id,
        ),
    )


def clean_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.strip()
    return text or None


def request_remote_ip(request: Request) -> Optional[str]:
    x_real_ip = normalize_ip_candidate(request.headers.get("x-real-ip", ""))
    if x_real_ip:
        return x_real_ip

    for candidate in request.headers.get("x-forwarded-for", "").split(","):
        forwarded_ip = normalize_ip_candidate(candidate)
        if forwarded_ip:
            return forwarded_ip

    if request.client and request.client.host:
        return normalize_ip_candidate(request.client.host)
    return None


def normalize_ip_candidate(value: str) -> Optional[str]:
    raw = value.strip()
    if not raw:
        return None
    if raw.startswith("[") and "]" in raw:
        raw = raw[1 : raw.find("]")]
    elif raw.count(":") == 1 and "." in raw.rsplit(":", 1)[0] and raw.rsplit(":", 1)[1].isdigit():
        raw = raw.rsplit(":", 1)[0]
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return None


def current_client_status(row: Dict[str, Any]) -> str:
    last_seen_at = row.get("last_seen_at")
    if not last_seen_at:
        return "offline"

    try:
        last_seen = datetime.fromisoformat(last_seen_at)
    except ValueError:
        return "offline"

    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)

    age_seconds = (datetime.now(timezone.utc) - last_seen).total_seconds()
    if age_seconds <= CLIENT_ONLINE_GRACE_SECONDS:
        return "online"
    return "offline"


def utc_datetime_plus(hours: int) -> str:
    from datetime import timedelta

    from .security import utc_now

    return (utc_now() + timedelta(hours=hours)).isoformat()


def format_client(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "client_id": row["client_id"],
        "name": row["name"],
        "hostname": row["hostname"],
        "os": row["os"],
        "arch": row["arch"],
        "ips": json.loads(row["ips_json"] or "[]"),
        "agent_version": row["agent_version"],
        "hardware": {
            "cpu_model": row.get("cpu_model"),
            "gpu_model": row.get("gpu_model"),
            "memory_total_bytes": row.get("memory_total_bytes"),
            "disk_total_bytes": row.get("disk_total_bytes"),
            "os_version": row.get("os_version"),
            "updated_at": row.get("hardware_updated_at"),
        },
        "status": current_client_status(row),
        "last_seen_at": row["last_seen_at"],
        "last_remote_ip": row.get("last_remote_ip"),
        "last_remote_ip_seen_at": row.get("last_remote_ip_seen_at"),
        "created_at": row["created_at"],
    }


def format_fleet_client(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "client_id": row["client_id"],
        "hostname": row["hostname"],
        "status": current_client_status(row),
        "last_seen_at": row["last_seen_at"],
        "device_id": row.get("device_id"),
        "device_type": row.get("device_type"),
        "agent_version": row.get("agent_version"),
        "agent_protocol_version": row.get("agent_protocol_version"),
        "frpc_version": row.get("frpc_version"),
        "frpc_status": row.get("frpc_status"),
        "hardware_release": row.get("hardware_release"),
        "frp_client_release": row.get("frp_client_release"),
        "tenant_device_uuid": row.get("tenant_device_uuid"),
        "observation_updated_at": row.get("observation_updated_at"),
        "hardware": {
            "cpu_model": row.get("cpu_model"),
            "gpu_model": row.get("gpu_model"),
            "memory_total_bytes": row.get("memory_total_bytes"),
            "disk_total_bytes": row.get("disk_total_bytes"),
            "os_version": row.get("os_version"),
            "updated_at": row.get("hardware_updated_at"),
        },
    }


def format_port_check(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "client_id": row["client_id"],
        "protocol": row["protocol"],
        "host": row["host"],
        "port": row["port"],
        "status": row["status"],
        "result": json.loads(row["result_json"]) if row.get("result_json") else None,
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def format_forward(row: Dict[str, Any], settings: Settings) -> Dict[str, Any]:
    addresses: List[str] = []
    if row["protocol"] in {"tcp", "udp"} and row["remote_port"]:
        addresses = [
            "{}:{}".format(settings.public_ip, row["remote_port"]),
            "{}:{}".format(settings.base_domain, row["remote_port"]),
        ]
    elif row["subdomain"]:
        host = "{}.{}".format(row["subdomain"], settings.base_domain)
        addresses = ["http://{}".format(host), "https://{}".format(host)]

    return {
        "id": row["id"],
        "client_id": row["client_id"],
        "protocol": row["protocol"],
        "local_ip": row["local_ip"],
        "local_port": row["local_port"],
        "remote_port": row["remote_port"],
        "subdomain": row["subdomain"],
        "status": row["status"],
        "note": row["note"],
        "public_addresses": addresses,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


app = create_app()
