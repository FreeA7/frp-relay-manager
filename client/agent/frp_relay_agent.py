from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


AGENT_VERSION = "0.4.0-rc.1"
AGENT_PROTOCOL_VERSION = "2"


@dataclass
class AgentConfig:
    server_url: str
    enrollment_token: Optional[str]
    agent_token: Optional[str]
    client_id: Optional[str]
    heartbeat_interval_seconds: int
    state_path: Path
    frpc_config_path: Path
    frpc_reload_cmd: Optional[str]
    hardware: Dict[str, Any]
    device_identity_path: Path = Path("/etc/deep-assess/device-identity.json")
    hardware_release_path: Path = Path("/etc/deep-assess/release.json")
    client_release_path: Path = Path("/etc/frp-relay-agent/release.json")
    tenant_binding_path: Path = Path("/var/lib/deep-assess/tenant-binding.json")
    frpc_binary_path: Path = Path("/usr/local/bin/frpc")


def load_config(path: Path) -> AgentConfig:
    file_values = read_env_file(path)

    def get(name: str, default: str = "") -> str:
        return os.environ.get(name, file_values.get(name, default))

    state_path = resolve_config_path(path, get("FRP_RELAY_AGENT_STATE", "agent-state.json"))
    state = read_json(state_path)

    return AgentConfig(
        server_url=get("FRP_RELAY_SERVER_URL", "https://panel.tunnel.freea7.fun").rstrip("/"),
        enrollment_token=get("FRP_RELAY_ENROLLMENT_TOKEN", ""),
        agent_token=get("FRP_RELAY_AGENT_TOKEN", state.get("agent_token", "")),
        client_id=get("FRP_RELAY_CLIENT_ID", state.get("client_id", "")),
        heartbeat_interval_seconds=int(get("FRP_RELAY_HEARTBEAT_INTERVAL_SECONDS", "30")),
        state_path=state_path,
        frpc_config_path=resolve_config_path(path, get("FRP_RELAY_FRPC_CONFIG", "frpc.generated.toml")),
        frpc_reload_cmd=get("FRP_RELAY_FRPC_RELOAD_CMD", ""),
        hardware=hardware_from_config(get),
        device_identity_path=Path(
            get("FRP_RELAY_DEVICE_IDENTITY", "/etc/deep-assess/device-identity.json")
        ),
        hardware_release_path=Path(
            get("FRP_RELAY_HARDWARE_RELEASE", "/etc/deep-assess/release.json")
        ),
        client_release_path=Path(
            get("FRP_RELAY_CLIENT_RELEASE", "/etc/frp-relay-agent/release.json")
        ),
        tenant_binding_path=Path(
            get("FRP_RELAY_TENANT_BINDING", "/var/lib/deep-assess/tenant-binding.json")
        ),
        frpc_binary_path=Path(get("FRP_RELAY_FRPC_BINARY", "/usr/local/bin/frpc")),
    )


def hardware_from_config(get, detected: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    hardware = dict(detect_hardware() if detected is None else detected)
    text_fields = {
        "FRP_RELAY_HARDWARE_CPU_MODEL": "cpu_model",
        "FRP_RELAY_HARDWARE_GPU_MODEL": "gpu_model",
        "FRP_RELAY_HARDWARE_OS_VERSION": "os_version",
    }
    integer_fields = {
        "FRP_RELAY_HARDWARE_MEMORY_TOTAL_BYTES": "memory_total_bytes",
        "FRP_RELAY_HARDWARE_DISK_TOTAL_BYTES": "disk_total_bytes",
    }
    for env_name, payload_name in text_fields.items():
        value = get(env_name, "").strip()
        if value:
            hardware[payload_name] = value
    for env_name, payload_name in integer_fields.items():
        value = get(env_name, "").strip()
        if value:
            try:
                parsed = int(value)
            except ValueError:
                continue
            if parsed >= 0:
                hardware[payload_name] = parsed
    return hardware


def detect_hardware() -> Dict[str, Any]:
    detected = {
        "cpu_model": detect_cpu_model(),
        "gpu_model": detect_gpu_model(),
        "memory_total_bytes": detect_memory_total_bytes(),
        "disk_total_bytes": detect_disk_total_bytes(),
        "os_version": detect_os_version(),
    }
    return {key: value for key, value in detected.items() if value not in {None, ""}}


def detect_cpu_model() -> str:
    if sys.platform.startswith("linux"):
        try:
            fields: Dict[str, str] = {}
            for raw_line in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace").splitlines():
                if ":" not in raw_line:
                    continue
                key, value = raw_line.split(":", 1)
                fields.setdefault(key.strip().lower(), value.strip())
            for key in ("model name", "hardware", "processor"):
                if fields.get(key):
                    return fields[key]
        except OSError:
            pass
    elif sys.platform == "darwin":
        value = command_output(["sysctl", "-n", "machdep.cpu.brand_string"])
        if value:
            return value
    elif os.name == "nt":
        value = command_output(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)",
            ]
        )
        if value:
            return value

    return platform.processor().strip()


def detect_gpu_model() -> str:
    models: List[str] = []
    if sys.platform.startswith("linux"):
        output = command_output(["lspci", "-mm"])
        for raw_line in output.splitlines():
            try:
                fields = shlex.split(raw_line)
            except ValueError:
                continue
            if len(fields) < 4 or not any(label in fields[1].lower() for label in ("vga", "3d", "display")):
                continue
            model = " ".join(part for part in (fields[2].strip(), fields[3].strip()) if part)
            if model and model not in models:
                models.append(model)
    elif sys.platform == "darwin":
        output = command_output(["system_profiler", "SPDisplaysDataType"])
        for raw_line in output.splitlines():
            if "Chipset Model:" not in raw_line:
                continue
            model = raw_line.split("Chipset Model:", 1)[1].strip()
            if model and model not in models:
                models.append(model)
    elif os.name == "nt":
        output = command_output(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -join '; '",
            ]
        )
        if output:
            models.append(output)
    return "; ".join(models)


def detect_memory_total_bytes() -> Optional[int]:
    if os.name == "nt":
        try:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong),
                    ("available_physical", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("available_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.total_physical)
        except (AttributeError, OSError):
            return None

    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        page_count = int(os.sysconf("SC_PHYS_PAGES"))
        total = page_size * page_count
        return total if total > 0 else None
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def detect_disk_total_bytes() -> Optional[int]:
    try:
        filesystem_root = Path.home().anchor or os.path.abspath(os.sep)
        total = int(shutil.disk_usage(filesystem_root).total)
        return total if total > 0 else None
    except OSError:
        return None


def detect_os_version() -> str:
    if sys.platform.startswith("linux"):
        try:
            release = platform.freedesktop_os_release()
            value = release.get("PRETTY_NAME") or release.get("NAME")
            if value:
                return value.strip()
        except (AttributeError, OSError):
            pass
    return platform.platform(aliased=True).strip()


def command_output(command: List[str]) -> str:
    try:
        result = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def resolve_config_path(config_path: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (config_path.parent / path).resolve()


def read_env_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}

    values: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = parse_env_value(value)
    return values


def parse_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_optional_json(path: Path) -> Dict[str, Any]:
    try:
        payload = read_json(path)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
        path.chmod(0o600)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def request_json(method: str, url: str, payload: Optional[Dict[str, Any]] = None, token: Optional[str] = None) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError("{} {} failed: {}".format(method, url, detail)) from exc


def nested_string(payload: Dict[str, Any], keys: set[str]) -> str:
    for key, value in payload.items():
        if key in keys and isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            found = nested_string(value, keys)
            if found:
                return found
    return ""


def release_summary(path: Path) -> Dict[str, Any]:
    payload = read_optional_json(path)
    product = str(payload.get("product") or "").strip()
    version = str(payload.get("version") or "").strip()
    if not product or not version:
        return {}
    result = {"product": product, "version": version}
    for key in ("gitTag", "gitCommit", "manifestChecksum", "profile", "installedAt"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            result[key] = value.strip()
    return result


def tenant_device_uuid(config: AgentConfig) -> str:
    candidates = [
        config.tenant_binding_path,
        Path("/home/deploy/.config/deep-assess-mirror/tenant-device-self.json"),
        Path("/home/deploy/.config/deep-assess-admin/tenant-device-binding.json"),
        Path("/home/deploy/.config/deep-assess-admin/device-binding.json"),
    ]
    for path in candidates:
        value = nested_string(read_optional_json(path), {"deviceUuid", "device_uuid"})
        if value:
            return value
    return ""


def frpc_status() -> str:
    state = command_output(["systemctl", "is-active", "frp-relay-frpc.service"])
    if state == "active":
        return "running"
    if state in {"inactive", "failed", "deactivating"}:
        return "stopped"
    return "unknown"


def inventory_payload(config: AgentConfig) -> Dict[str, Any]:
    identity = read_optional_json(config.device_identity_path)
    hardware_release = release_summary(config.hardware_release_path)
    client_release = release_summary(config.client_release_path)
    inventory: Dict[str, Any] = {
        "agent_protocol_version": AGENT_PROTOCOL_VERSION,
        "frpc_version": command_output([str(config.frpc_binary_path), "--version"]),
        "frpc_status": frpc_status(),
        "observation_updated_at": datetime.now(timezone.utc).isoformat(),
    }
    device_id = nested_string(identity, {"deviceId", "device_id"})
    device_type = nested_string(identity, {"deviceType", "device_type"})
    current_tenant_device_uuid = tenant_device_uuid(config)
    if device_id:
        inventory["device_id"] = device_id
    if device_type:
        inventory["device_type"] = device_type
    if current_tenant_device_uuid:
        inventory["tenant_device_uuid"] = current_tenant_device_uuid
    if hardware_release:
        inventory["hardware_release"] = hardware_release
    if client_release:
        inventory["frp_client_release"] = client_release
    return {key: value for key, value in inventory.items() if value is not None and value != ""}


def machine_payload(config: AgentConfig) -> Dict[str, Any]:
    payload = {
        "hostname": socket.gethostname(),
        "os": "{} {}".format(platform.system(), platform.release()).strip(),
        "arch": platform.machine(),
        "ips": local_ips(),
        "agent_version": AGENT_VERSION,
        "inventory": inventory_payload(config),
    }
    if config.hardware:
        payload["hardware"] = config.hardware
    return payload


def local_ips() -> List[str]:
    ips = {"127.0.0.1"}
    hostname = socket.gethostname()
    try:
        for item in socket.getaddrinfo(hostname, None):
            address = item[4][0]
            if ":" not in address:
                ips.add(address)
    except socket.gaierror:
        pass
    return sorted(ips)


def register(config: AgentConfig) -> AgentConfig:
    if not config.enrollment_token:
        raise RuntimeError("FRP_RELAY_ENROLLMENT_TOKEN is required for first registration")

    payload = machine_payload(config)
    payload["enrollment_token"] = config.enrollment_token
    response = request_json("POST", config.server_url + "/api/agent/register", payload)
    config.agent_token = response["agent_token"]
    config.client_id = response["client_id"]
    config.heartbeat_interval_seconds = int(response.get("heartbeat_interval_seconds", config.heartbeat_interval_seconds))
    write_json(
        config.state_path,
        {
            "client_id": config.client_id,
            "agent_token": config.agent_token,
            "heartbeat_interval_seconds": config.heartbeat_interval_seconds,
        },
    )
    return config


def heartbeat(config: AgentConfig) -> None:
    payload = machine_payload(config)
    request_json("POST", config.server_url + "/api/agent/heartbeat", payload, token=config.agent_token)


def poll_tasks(config: AgentConfig) -> None:
    tasks = request_json("GET", config.server_url + "/api/agent/tasks", token=config.agent_token)
    sync_frpc_config(config, tasks.get("frpc", {}), tasks.get("forwards", []))
    for task in tasks.get("port_checks", []):
        result = run_port_check(task)
        request_json("POST", config.server_url + "/api/agent/port-check-results", result, token=config.agent_token)


def sync_frpc_config(config: AgentConfig, frpc: Dict[str, Any], forwards: List[Dict[str, Any]]) -> None:
    if not frpc:
        return

    rendered = render_frpc_config(frpc, forwards)
    current = config.frpc_config_path.read_text(encoding="utf-8") if config.frpc_config_path.exists() else ""
    config_changed = current != rendered
    pending_path = frpc_reload_pending_path(config.frpc_config_path)

    if config_changed:
        config.frpc_config_path.parent.mkdir(parents=True, exist_ok=True)
        if config.frpc_reload_cmd:
            pending_path.touch()
        write_text_atomic(config.frpc_config_path, rendered)

    if not config.frpc_reload_cmd or not pending_path.exists():
        return

    run_frpc_reload(config.frpc_reload_cmd)
    pending_path.unlink(missing_ok=True)


def frpc_reload_pending_path(config_path: Path) -> Path:
    return config_path.with_name(config_path.name + ".reload-pending")


def write_text_atomic(path: Path, content: str) -> None:
    temporary_path = path.with_name(".{}.{}.tmp".format(path.name, os.getpid()))
    try:
        temporary_path.write_text(content, encoding="utf-8")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def run_frpc_reload(command: str) -> None:
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("frpc reload command could not complete: {}".format(exc)) from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "no output").strip()[:500]
        raise RuntimeError(
            "frpc reload command failed with exit code {}: {}".format(result.returncode, detail)
        )


def render_frpc_config(frpc: Dict[str, Any], forwards: List[Dict[str, Any]]) -> str:
    lines = [
        'serverAddr = "{}"'.format(frpc["server_addr"]),
        "serverPort = {}".format(int(frpc["server_port"])),
        "",
        'auth.token = "{}"'.format(escape_toml(frpc["auth_token"])),
        "",
    ]

    for forward in forwards:
        name = "relay-{}".format(forward["id"])
        lines.extend(
            [
                "[[proxies]]",
                'name = "{}"'.format(escape_toml(name)),
                'type = "{}"'.format(escape_toml(forward["protocol"])),
                'localIP = "{}"'.format(escape_toml(forward["local_ip"])),
                "localPort = {}".format(int(forward["local_port"])),
            ]
        )
        if forward["protocol"] in {"tcp", "udp"}:
            lines.append("remotePort = {}".format(int(forward["remote_port"])))
        else:
            lines.append('subdomain = "{}"'.format(escape_toml(forward["subdomain"])))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def escape_toml(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def run_port_check(task: Dict[str, Any]) -> Dict[str, Any]:
    protocol = task.get("protocol", "tcp").lower()
    host = task.get("host", "127.0.0.1")
    port = int(task["port"])

    try:
        if protocol in {"http", "https"}:
            result = check_http(protocol, host, port)
        elif protocol == "udp":
            result = check_udp(host, port)
        else:
            result = check_tcp(host, port)
        return {
            "task_id": task["id"],
            "status": "completed",
            "listening": result["listening"],
            "detail": result,
        }
    except Exception as exc:  # noqa: BLE001 - agent should report probe failure instead of crashing.
        return {
            "task_id": task["id"],
            "status": "failed",
            "listening": False,
            "detail": {},
            "error": str(exc),
        }


def check_tcp(host: str, port: int) -> Dict[str, Any]:
    started = time.time()
    with socket.create_connection((host, port), timeout=3) as sock:
        sock.settimeout(1)
        banner = ""
        try:
            banner = sock.recv(160).decode("utf-8", errors="replace").strip()
        except socket.timeout:
            pass
    return {"listening": True, "kind": "tcp", "latency_ms": round((time.time() - started) * 1000), "banner": banner}


def check_udp(host: str, port: int) -> Dict[str, Any]:
    started = time.time()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(1)
        sock.sendto(b"\x00", (host, port))
        try:
            data, _ = sock.recvfrom(160)
            response = data.decode("utf-8", errors="replace").strip()
        except socket.timeout:
            response = ""
    return {"listening": bool(response), "kind": "udp", "latency_ms": round((time.time() - started) * 1000), "banner": response}


def check_http(protocol: str, host: str, port: int) -> Dict[str, Any]:
    started = time.time()
    url = "{}://{}:{}/".format(protocol, host, port)
    request = urllib.request.Request(url, headers={"User-Agent": "frp-relay-agent/" + AGENT_VERSION})
    with urllib.request.urlopen(request, timeout=5) as response:
        body = response.read(4096).decode("utf-8", errors="replace")
        title = ""
        lower = body.lower()
        start = lower.find("<title>")
        end = lower.find("</title>")
        if start >= 0 and end > start:
            title = body[start + len("<title>") : end].strip()
        return {
            "listening": True,
            "kind": protocol,
            "latency_ms": round((time.time() - started) * 1000),
            "status_code": response.status,
            "title": title,
        }


def run_once(config: AgentConfig) -> None:
    if not config.agent_token:
        config = register(config)
    heartbeat(config)
    poll_tasks(config)


def run_loop(config: AgentConfig) -> None:
    if not config.agent_token:
        config = register(config)

    while True:
        try:
            heartbeat(config)
            poll_tasks(config)
        except Exception as exc:  # noqa: BLE001 - keep the agent alive across transient failures.
            print("agent error: {}".format(exc), file=sys.stderr)
        time.sleep(config.heartbeat_interval_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="FRP relay client agent")
    parser.add_argument("--config", default="agent.env", help="Path to agent env file")
    parser.add_argument("--once", action="store_true", help="Run one heartbeat/task poll and exit")
    args = parser.parse_args()

    config = load_config(Path(args.config).resolve())
    if args.once:
        run_once(config)
    else:
        run_loop(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
