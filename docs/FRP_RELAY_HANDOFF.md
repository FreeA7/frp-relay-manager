# FRP Relay Project Handoff

最后更新：2026-05-14 HKT

## 目标

在这台韩国 VPS 上部署一个基于 frp 的中转/内网穿透管理系统。VPS 有公网 IP，可作为国内外中转节点；多台没有独立公网 IP 的客户端电脑通过 `frpc + Python agent` 连接到本机，管理员通过 Web 页面查看在线电脑、探测客户端端口、创建/暂停/删除转发规则，并获得可从外部访问的地址。

核心要求：

- 新项目创建在 `/src` 下，建议路径：`/src/frp_relay`。
- 前后端分离：前端 React，后端 Python。
- 管理页面必须登录才能进入。
- 登录用户名固定：`freea7@futurememetech.com`。
- 登录密码后续实现时随机生成，放在项目 `.env`，不要硬编码。
- 默认转发公网可访问，暂不要求 IP 白名单。
- 客户端电脑可以安装 `frpc + Python agent`。
- 管理页需要显示哪些电脑在线、基本状态、已配置转发。
- 管理页可选择电脑，输入端口或点选常见端口预设，检查该电脑上该端口是否在监听及服务详情，再配置转发。
- 配置后页面显示外部连接地址和端口，例如 SSH、HTTP、数据库等。

注意能力边界：

- frp 适合 TCP/UDP/HTTP/HTTPS 的端口级转发。
- “所有端口和协议”应按 frp 能力理解为 TCP/UDP/HTTP/HTTPS；不是三层 VPN，ICMP/ping 或任意 IP 包不在 v1 范围内。
- “透转”可以做到字节流/协议层透明；真实源 IP 通常不会传到内网服务，除非目标服务配合 proxy protocol 等机制。

## 当前系统状态

服务器：

- OS：Ubuntu 22.04.3 LTS
- 公网 IPv4：`45.141.136.217`
- 主机名：`cloud`
- 当前用户：root
- `/src` 当前已有：`/src/vps_server`
- 现有服务：`vps-openai-relay.service`，FastAPI/uvicorn 监听 `127.0.0.1:8000`
- nginx 正在监听公网 `80/443`，当前服务 `api.freea7.fun`
- `api.freea7.fun -> 45.141.136.217`
- `*.tunnel.freea7.fun -> 45.141.136.217` 已验证可解析，例如 `test.tunnel.freea7.fun`
- `chat.freea7.fun` 是用户之前说错的，不作为本项目域名

工具链状态：

- Python 3.10 已安装
- Node/npm 未安装
- Docker 未安装
- `frps/frpc` 未安装
- `ufw`、`nft`、`iptables` 命令未安装或不可用
- 机器约 1GB RAM、无 swap、磁盘剩余约 3.6GB；实现时建议先加 1-2GB swap，避免 npm build 或安装依赖时 OOM

当前占用端口：

- `22`：系统 SSH
- `80/443`：nginx
- `127.0.0.1:8000`：现有 OpenAI relay

建议新项目默认端口：

- 后端 API：`127.0.0.1:8010`
- 前端由 React build 后交给 nginx 静态托管
- frps 控制连接：`0.0.0.0:7000`
- frps API/dashboard 仅绑定本地，例如 `127.0.0.1:7500`，不要公网暴露
- TCP/UDP 远程端口池：`20000-49999`
- HTTP 隧道外部访问：优先子域名形式，使用 `*.tunnel.freea7.fun`

## 已完成

通配证书已完成并验证自动续期。

证书：

- 证书名：`tunnel.freea7.fun`
- 覆盖域名：`tunnel.freea7.fun` 和 `*.tunnel.freea7.fun`
- 证书路径：`/etc/letsencrypt/live/tunnel.freea7.fun/fullchain.pem`
- 私钥路径：`/etc/letsencrypt/live/tunnel.freea7.fun/privkey.pem`
- 有效期：`2026-08-12 05:26:55 UTC`

DNS-01 自动化：

- DNSPod API 凭据已保存在 `/etc/letsencrypt/dnspod.env`
- 文件权限：`600 root:root`
- 不要在日志、文档、最终回复中回显 token
- 未来建议用户在 DNSPod 里换成最小权限的新 token，因为 token 曾经出现在对话里

已创建的证书辅助文件：

- `/etc/letsencrypt/dns-hooks/dnspod.py`
- `/etc/letsencrypt/dns-hooks/issue-tunnel-cert.sh`
- `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh`

验证结果：

- `certbot certonly ... --dry-run` 成功
- `/etc/letsencrypt/dns-hooks/issue-tunnel-cert.sh` 正式签发成功
- `certbot renew --dry-run` 成功，包含 `api.freea7.fun` 和 `tunnel.freea7.fun`
- `nginx -t` 成功
- 现有 `certbot.timer` 仍在工作；不要新增第二套 acme.sh/cron 续期系统

## 建议实现方案

项目结构建议：

- `/src/frp_relay/backend`：Python FastAPI 后端
- `/src/frp_relay/frontend`：React/Vite 前端
- `/src/frp_relay/client-agent`：给内网电脑运行的 Python agent
- `/src/frp_relay/deploy`：systemd/nginx/frps 配置模板和安装脚本
- `/src/frp_relay/.env`：服务端密钥、登录密码、JWT secret、frps token、端口池等

服务端组件：

- 安装 frp 最新稳定版，已查到当前 release 为 `v0.68.1`，Linux amd64 包：
  `https://github.com/fatedier/frp/releases/download/v0.68.1/frp_0.68.1_linux_amd64.tar.gz`
- 使用官方 sha256 校验：`4a4e88987d39561e1b3b3b23d0ede48a457eebf76a87231999957e870f5f02b6`
- `frps` 由 systemd 管理。
- 后端 FastAPI 由 systemd 管理，监听 `127.0.0.1:8010`。
- nginx 使用 `panel.tunnel.freea7.fun` 作为管理面板入口，证书使用 `/etc/letsencrypt/live/tunnel.freea7.fun/...`。
- nginx 继续保留现有 `api.freea7.fun` 配置，不要破坏 `/src/vps_server` 和 `vps-openai-relay.service`。

管理后台建议能力：

- 登录/退出，JWT 或安全 session 均可。
- 在线客户端列表：名称、client_id、hostname、系统、内网 IP、agent 版本、frpc 状态、最后心跳时间。
- 端口探测：输入端口/协议或点选预设，agent 在客户端本机探测并返回 listening 状态、banner/HTTP title/SSH banner 等轻量详情。
- 转发规则 CRUD：客户端、协议、local_ip、local_port、remote_port、subdomain、状态、备注。
- 对 TCP/UDP 服务显示：`45.141.136.217:<remote_port>` 和 `tunnel.freea7.fun:<remote_port>`。
- 对 HTTP 服务显示：`http://<name>.tunnel.freea7.fun`；后续可加 HTTPS。
- 对 SSH 预设显示示例：`ssh user@tunnel.freea7.fun -p <remote_port>`。

客户端 agent 建议能力：

- 客户端主动连接后端，使用服务端生成的 enrollment token 注册。
- 定期心跳，上报机器信息和 frpc 状态。
- 接收端口探测请求，返回监听状态和服务详情。
- 接收转发规则，生成/更新 frpc 配置并热重载 frpc。
- Linux 客户端优先支持 systemd；Windows/macOS 可先提供手动运行说明或后续脚本。

数据存储建议：

- v1 使用 SQLite，路径例如 `/src/frp_relay/data/frp_relay.db`。
- 表/模型建议包含：users、clients、enrollment_tokens、port_checks、forwards、audit_logs。
- 密码只存哈希，不存明文。
- frps auth token、JWT secret、管理员初始密码放 `.env`。

端口与域名策略：

- TCP/UDP 默认从 `20000-49999` 自动分配，也允许管理员手动指定。
- 禁止占用系统和现有服务端口：`22`、`80`、`443`、`7000`、`7500`、`8000`、`8010` 等。
- HTTP 子域名建议规则：`<client-slug>-<service>.tunnel.freea7.fun`，避免冲突。
- 默认公网可访问，不做 IP 白名单；但保留字段和 UI 状态，方便后续加访问控制。

安全建议：

- frps dashboard/API 不公网暴露，只让后端本机访问。
- frps 使用强随机 token，写入 `.env` 和 frps 配置。
- 客户端 agent 和服务端 API 使用 HTTPS/WSS。
- enrollment token 一次性或可过期。
- `.env`、DNSPod 凭据、frps token 文件权限限制为 root 或 deploy 可读。
- 远程端口默认公网开放，UI 要明确显示风险。

## 下一步清单

建议后续 agent 按这个顺序推进：

1. 在 `/src/frp_relay` 创建项目骨架，不要修改 `/src/vps_server`。
2. 给系统加 1-2GB swap。
3. 安装 Node LTS；已查到当前 LTS 为 `v24.15.0 (Krypton)`。
4. 下载并校验 frp `v0.68.1`，安装 `frps/frpc` 到 `/usr/local/bin`。
5. 生成 `/src/frp_relay/.env`：管理员随机密码、JWT secret、frps token、端口池、域名配置。
6. 实现 FastAPI 后端：认证、客户端注册/心跳、端口探测接口、转发规则 CRUD、frps 配置生成/热重载。
7. 实现 React 前端：登录页、客户端列表、端口探测、转发规则管理、连接地址展示。
8. 实现 Python client-agent：注册、心跳、端口检查、frpc 配置同步和 reload。
9. 写 systemd：`frp-relay-api.service`、`frps.service`，客户端侧提供 agent/frpc service 模板。
10. 写 nginx 站点：`panel.tunnel.freea7.fun` 使用 wildcard 证书，反代 API/WebSocket 到 `127.0.0.1:8010`，静态托管前端。
11. 端到端验证：本机模拟一个客户端，配置 SSH/HTTP/TCP/UDP 转发，确认页面显示地址可访问。

## 操作注意

- 不要破坏现有 `api.freea7.fun`、`/src/vps_server`、`vps-openai-relay.service`。
- 修改 nginx 前先 `nginx -t`，再 reload。
- 证书续期已经复用 certbot，不要再装 acme.sh。
- 不要在回复、日志或新文档中泄露 DNSPod token。
- 如果需要查看 token，只读取 `/etc/letsencrypt/dnspod.env`，不要打印到终端输出。
