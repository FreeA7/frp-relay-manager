from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


AGENT_VERSION = "0.1.0"


@dataclass
class AgentConfig:
    server_url: str
    enrollment_token: Optional[str]
    agent_token: Optional[str]
    client_id: Optional[str]
    name: Optional[str]
    heartbeat_interval_seconds: int
    state_path: Path
    frpc_config_path: Path
    frpc_reload_cmd: Optional[str]


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
        name=get("FRP_RELAY_CLIENT_NAME", socket.gethostname()),
        heartbeat_interval_seconds=int(get("FRP_RELAY_HEARTBEAT_INTERVAL_SECONDS", "30")),
        state_path=state_path,
        frpc_config_path=resolve_config_path(path, get("FRP_RELAY_FRPC_CONFIG", "frpc.generated.toml")),
        frpc_reload_cmd=get("FRP_RELAY_FRPC_RELOAD_CMD", ""),
    )


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
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


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


def machine_payload(config: AgentConfig) -> Dict[str, Any]:
    return {
        "name": config.name,
        "hostname": socket.gethostname(),
        "os": "{} {}".format(platform.system(), platform.release()).strip(),
        "arch": platform.machine(),
        "ips": local_ips(),
        "agent_version": AGENT_VERSION,
    }


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
    payload["frpc_status"] = frpc_status()
    request_json("POST", config.server_url + "/api/agent/heartbeat", payload, token=config.agent_token)


def frpc_status() -> str:
    # v1 uses a conservative process-name check. Future versions can query frpc admin API.
    return "unknown"


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
    if current == rendered:
        return

    config.frpc_config_path.parent.mkdir(parents=True, exist_ok=True)
    config.frpc_config_path.write_text(rendered, encoding="utf-8")
    if config.frpc_reload_cmd:
        subprocess.run(config.frpc_reload_cmd, shell=True, check=False)


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
