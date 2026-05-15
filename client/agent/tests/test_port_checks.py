import socket
import threading

from frp_relay_agent import check_tcp
from frp_relay_agent import render_frpc_config


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
