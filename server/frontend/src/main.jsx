import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  ClipboardCopy,
  Copy,
  Globe2,
  LogOut,
  Monitor,
  Play,
  Plus,
  RadioTower,
  RefreshCcw,
  Server,
  ShieldCheck,
  Terminal,
  X,
} from 'lucide-react';
import './styles.css';

const API_BASE = import.meta.env.VITE_API_BASE || '';
const ADMIN_EMAIL = 'freea7@futurememetech.com';
const MACHINE_PAGE_SIZE = 5;

function api(path, options = {}) {
  const token = localStorage.getItem('frp_relay_token');
  const headers = {
    Accept: 'application/json',
    ...(options.body ? { 'Content-Type': 'application/json' } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };

  return fetch(`${API_BASE}${path}`, { ...options, headers }).then(async (response) => {
    const text = await response.text();
    const data = text ? JSON.parse(text) : {};
    if (!response.ok) {
      throw new Error(data.detail || `Request failed: ${response.status}`);
    }
    return data;
  });
}

function App() {
  const [token, setToken] = useState(localStorage.getItem('frp_relay_token') || '');

  if (!token) {
    return <Login onLogin={setToken} />;
  }

  return <Panel onLogout={() => {
    localStorage.removeItem('frp_relay_token');
    setToken('');
  }} />;
}

function Login({ onLogin }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      const result = await api('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email: ADMIN_EMAIL, password }),
      });
      localStorage.setItem('frp_relay_token', result.access_token);
      onLogin(result.access_token);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="loginShell">
      <form className="loginPanel" onSubmit={submit}>
        <div className="brandRow">
          <RadioTower size={28} />
          <div>
            <h1>FRP 远程接入</h1>
            <p>{ADMIN_EMAIL}</p>
          </div>
        </div>
        <label>
          管理密码
          <input
            type="password"
            value={password}
            autoFocus
            onChange={(event) => setPassword(event.target.value)}
            placeholder="输入服务端配置的管理密码"
          />
        </label>
        {error && <div className="errorBox">{error}</div>}
        <button className="primaryButton" disabled={loading || !password}>
          <ShieldCheck size={18} />
          {loading ? '正在登录' : '登录面板'}
        </button>
      </form>
    </main>
  );
}

function Panel({ onLogout }) {
  const [clients, setClients] = useState([]);
  const [forwards, setForwards] = useState([]);
  const [dashboard, setDashboard] = useState(null);
  const [selectedClient, setSelectedClient] = useState('');
  const [machinePage, setMachinePage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [forwardForm, setForwardForm] = useState(defaultForwardForm());
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function load() {
    setError('');
    try {
      const [clientData, forwardData, dashboardData] = await Promise.all([
        api('/api/clients'),
        api('/api/forwards'),
        api('/api/dashboard'),
      ]);
      const nextClients = clientData.items || [];
      setClients(nextClients);
      setForwards(forwardData.items || []);
      setDashboard(dashboardData);
      setSelectedClient((current) => {
        if (current && nextClients.some((client) => client.client_id === current)) {
          return current;
        }
        return nextClients[0]?.client_id || '';
      });
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!modalOpen) {
      return undefined;
    }
    function onKeyDown(event) {
      if (event.key === 'Escape') {
        setModalOpen(false);
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [modalOpen]);

  const sortedClients = useMemo(
    () => [...clients].sort((a, b) => {
      const aSeenAt = Date.parse(a.last_seen_at || '');
      const bSeenAt = Date.parse(b.last_seen_at || '');
      if (!Number.isNaN(aSeenAt) && !Number.isNaN(bSeenAt) && aSeenAt !== bSeenAt) {
        return bSeenAt - aSeenAt;
      }
      if (!Number.isNaN(aSeenAt)) {
        return -1;
      }
      if (!Number.isNaN(bSeenAt)) {
        return 1;
      }
      return deviceLabel(a).localeCompare(deviceLabel(b), 'zh-Hans-CN');
    }),
    [clients],
  );

  const totalMachinePages = Math.max(1, Math.ceil(sortedClients.length / MACHINE_PAGE_SIZE));
  const visibleMachinePage = Math.min(machinePage, totalMachinePages);
  const machinePageStart = (visibleMachinePage - 1) * MACHINE_PAGE_SIZE;
  const pagedClients = sortedClients.slice(machinePageStart, machinePageStart + MACHINE_PAGE_SIZE);
  const machinePageStartLabel = sortedClients.length ? machinePageStart + 1 : 0;
  const machinePageEndLabel = Math.min(machinePageStart + MACHINE_PAGE_SIZE, sortedClients.length);

  useEffect(() => {
    setMachinePage((current) => Math.min(Math.max(current, 1), totalMachinePages));
  }, [totalMachinePages]);

  const onlineCount = useMemo(
    () => clients.filter((client) => client.status === 'online').length,
    [clients],
  );

  const forwardsByClient = useMemo(() => {
    const groups = new Map();
    forwards.forEach((forward) => {
      const key = forward.client_id || '__unknown__';
      const current = groups.get(key) || [];
      current.push(forward);
      groups.set(key, current);
    });
    return groups;
  }, [forwards]);

  const selected = useMemo(
    () => clients.find((client) => client.client_id === selectedClient),
    [clients, selectedClient],
  );

  const selectedForwards = selected ? forwardsByClient.get(selected.client_id) || [] : [];

  async function createEnrollment() {
    setMessage('');
    setError('');
    try {
      const result = await api('/api/enrollment-tokens', {
        method: 'POST',
        body: JSON.stringify({ label: 'panel generated', expires_in_hours: 24 }),
      });
      await navigator.clipboard?.writeText(result.token);
      setMessage(`接入令牌已生成并复制：${result.token}`);
    } catch (err) {
      setError(err.message);
    }
  }

  async function requestPortCheck() {
    setMessage('');
    setError('');
    try {
      const result = await api('/api/port-checks', {
        method: 'POST',
        body: JSON.stringify({
          client_id: selectedClient,
          protocol: forwardForm.protocol,
          host: forwardForm.localIp || '127.0.0.1',
          port: Number(forwardForm.port),
        }),
      });
      setMessage(`端口探测已下发：${result.id}`);
    } catch (err) {
      setError(err.message);
    }
  }

  async function createForward() {
    setMessage('');
    setError('');
    try {
      const body = {
        client_id: selectedClient,
        protocol: forwardForm.protocol,
        local_ip: forwardForm.localIp || '127.0.0.1',
        local_port: Number(forwardForm.port),
        note: forwardForm.note,
      };
      if (forwardForm.protocol === 'http') {
        body.subdomain = forwardForm.subdomain;
      }
      const result = await api('/api/forwards', {
        method: 'POST',
        body: JSON.stringify(body),
      });
      setMessage(`转发已创建：${result.public_addresses.join(' / ')}`);
      setModalOpen(false);
      setForwardForm(defaultForwardForm());
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function copyText(value) {
    try {
      await navigator.clipboard?.writeText(value);
      setMessage(`已复制：${value}`);
    } catch (err) {
      setError(err.message || '复制失败');
    }
  }

  function openForwardModal(clientId = selectedClient) {
    setSelectedClient(clientId);
    setForwardForm(defaultForwardForm());
    setMessage('');
    setError('');
    setModalOpen(true);
  }

  function changeMachinePage(nextPage) {
    const clampedPage = Math.min(Math.max(nextPage, 1), totalMachinePages);
    setMachinePage(clampedPage);
    const nextClient = sortedClients[(clampedPage - 1) * MACHINE_PAGE_SIZE];
    if (nextClient) {
      setSelectedClient(nextClient.client_id);
    }
  }

  return (
    <main className="appShell">
      <header className="topBar">
        <div className="brandRow">
          <RadioTower size={26} />
          <div>
            <h1>FRP 远程接入</h1>
            <p>{dashboard?.panel_domain || 'panel.tunnel.freea7.fun'}</p>
          </div>
        </div>
        <div className="topActions">
          <button className="secondaryButton" onClick={createEnrollment}>
            <ClipboardCopy size={16} />
            生成接入令牌
          </button>
          <button className="iconButton" title="刷新" onClick={load}>
            <RefreshCcw size={18} />
          </button>
          <button className="iconButton" title="退出" onClick={onLogout}>
            <LogOut size={18} />
          </button>
        </div>
      </header>

      {(error || message) && (
        <section className={error ? 'errorBox' : 'messageBox'}>{error || message}</section>
      )}

      <section className="metricsGrid">
        <Metric icon={<Monitor />} label="全部机器" value={dashboard?.client_count ?? clients.length} />
        <Metric icon={<Activity />} label="在线机器" value={dashboard?.online_client_count ?? onlineCount} tone="ok" />
        <Metric icon={<Server />} label="转发规则" value={dashboard?.forward_count ?? forwards.length} />
        <Metric icon={<Terminal />} label="探测任务" value={dashboard?.pending_port_check_count ?? 0} />
      </section>

      <section className="workspaceLayout">
        <aside className="machinePane">
          <div className="sectionHeader">
            <div>
              <h2>设备名称</h2>
              <p>每页 5 台，点击设备查看详情</p>
            </div>
          </div>

          <div className="machineStack">
            {pagedClients.map((client) => {
              const clientForwards = forwardsByClient.get(client.client_id) || [];
              return (
                <button
                  key={client.client_id}
                  className={`machineCard ${client.client_id === selectedClient ? 'active' : ''}`}
                  onClick={() => setSelectedClient(client.client_id)}
                >
                  <div className="machineTopLine">
                    <span className={`statusBadge ${client.status}`}>{statusLabel(client.status)}</span>
                    <span className="forwardCount">{clientForwards.length} 个转发</span>
                  </div>
                  <strong>{deviceLabel(client)}</strong>
                  <small>最后在线：{formatDateTime(client.last_seen_at)}</small>
                </button>
              );
            })}
            {!clients.length && <div className="emptyState">暂无已注册机器</div>}
          </div>
          {sortedClients.length > MACHINE_PAGE_SIZE ? (
            <div className="paginationBar">
              <button className="pageButton" title="上一页" disabled={visibleMachinePage <= 1} onClick={() => changeMachinePage(visibleMachinePage - 1)}>
                ‹
              </button>
              <div className="pageNumbers">
                {Array.from({ length: totalMachinePages }, (_, index) => index + 1).map((page) => (
                  <button
                    key={page}
                    className={`pageNumber ${page === visibleMachinePage ? 'active' : ''}`}
                    onClick={() => changeMachinePage(page)}
                  >
                    {page}
                  </button>
                ))}
              </div>
              <button className="pageButton" title="下一页" disabled={visibleMachinePage >= totalMachinePages} onClick={() => changeMachinePage(visibleMachinePage + 1)}>
                ›
              </button>
              <div className="pageStatus">
                {machinePageStartLabel}-{machinePageEndLabel} / {sortedClients.length}
              </div>
            </div>
          ) : null}
        </aside>

        <section className="detailPanel">
          <div className="sectionHeader compact">
            <div>
              <h2>{selected ? deviceLabel(selected) : '未选择机器'}</h2>
              <p>{selected ? `${statusLabel(selected.status)} · 最后在线 ${formatDateTime(selected.last_seen_at)}` : '从左侧选择一台机器'}</p>
            </div>
            <button className="primaryButton" disabled={!selected} onClick={() => openForwardModal()}>
              <Plus size={16} />
              新增转发
            </button>
          </div>

          {selected ? (
            <div className="selectedBody">
              <div className="infoStrip">
                <InfoItem label="操作系统" value={selected.hardware?.os_version || selected.os || '--'} />
                <InfoItem label="CPU" value={selected.hardware?.cpu_model || '--'} />
                <InfoItem label="GPU" value={selected.hardware?.gpu_model || '--'} />
                <InfoItem label="内存" value={formatBytes(selected.hardware?.memory_total_bytes)} />
                <InfoItem label="硬盘" value={formatBytes(selected.hardware?.disk_total_bytes)} />
                <InfoItem label="主机名" value={selected.hostname || '--'} />
                <InfoItem label="架构" value={selected.arch || '--'} />
                <InfoItem label="代理版本" value={selected.agent_version || '--'} />
                <InfoItem label="最后心跳" value={formatDateTime(selected.last_seen_at)} />
                <InfoItem label="访问公网 IP" value={selected.last_remote_ip || '--'} />
                <InfoItem label="硬件更新时间" value={formatDateTime(selected.hardware?.updated_at)} />
                <InfoItem label="Client ID" value={selected.client_id || '--'} />
              </div>
              <div className="forwardPanelHeader">
                <div>
                  <h3>转发信息</h3>
                  <p>这台设备当前有 {selectedForwards.length} 个转发入口</p>
                </div>
              </div>
              <ForwardList forwards={selectedForwards} emptyText="这台机器还没有转发规则" onCopy={copyText} />
            </div>
          ) : (
            <div className="emptyState">请选择机器后查看详情</div>
          )}
        </section>
      </section>

      {modalOpen && (
        <div className="modalOverlay" role="presentation" onMouseDown={() => setModalOpen(false)}>
          <section className="modalPanel" role="dialog" aria-modal="true" aria-labelledby="forward-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="modalHeader">
              <div>
                <h2 id="forward-title">新增转发</h2>
                <p>{selected?.name || '未选择机器'}</p>
              </div>
              <button className="iconButton" title="关闭" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>

            <div className="formGrid">
              <label>
                目标机器
                <select value={selectedClient} onChange={(event) => setSelectedClient(event.target.value)}>
                  {sortedClients.map((client) => (
                    <option key={client.client_id} value={client.client_id}>{client.name}</option>
                  ))}
                </select>
              </label>
              <label>
                协议
                <select
                  value={forwardForm.protocol}
                  onChange={(event) => setForwardForm((form) => ({ ...form, protocol: event.target.value }))}
                >
                  <option value="tcp">TCP</option>
                  <option value="udp">UDP</option>
                  <option value="http">HTTP</option>
                </select>
              </label>
              <label>
                本机地址
                <input
                  value={forwardForm.localIp}
                  onChange={(event) => setForwardForm((form) => ({ ...form, localIp: event.target.value }))}
                  placeholder="127.0.0.1"
                />
              </label>
              <label>
                本机端口
                <input
                  value={forwardForm.port}
                  onChange={(event) => setForwardForm((form) => ({ ...form, port: event.target.value }))}
                  inputMode="numeric"
                />
              </label>
              <label>
                HTTP 子域名
                <input
                  value={forwardForm.subdomain}
                  onChange={(event) => setForwardForm((form) => ({ ...form, subdomain: event.target.value }))}
                  disabled={forwardForm.protocol !== 'http'}
                  placeholder="仅 HTTP 需要"
                />
              </label>
              <label>
                备注
                <input
                  value={forwardForm.note}
                  onChange={(event) => setForwardForm((form) => ({ ...form, note: event.target.value }))}
                  placeholder="SSH / DevTools / Web 服务"
                />
              </label>
            </div>

            <div className="presetRow">
              {[22, 80, 443, 3306, 5432, 6379, 8080, 9223].map((preset) => (
                <button key={preset} onClick={() => setForwardForm((form) => ({ ...form, port: String(preset) }))}>{preset}</button>
              ))}
            </div>

            <div className="modalActions">
              <button className="secondaryButton" disabled={!selected || !forwardForm.port} onClick={requestPortCheck}>
                <Play size={16} />
                探测端口
              </button>
              <button className="primaryButton" disabled={!selected || !forwardForm.port} onClick={createForward}>
                <Plus size={16} />
                创建转发
              </button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}

function ForwardList({ forwards, emptyText = '暂无转发规则', onCopy }) {
  if (!forwards.length) {
    return <div className="emptyState slim">{emptyText}</div>;
  }

  return (
    <div className="forwardList">
      {forwards.map((forward) => (
        <div className="forwardRow" key={forward.id}>
          <div className="forwardProtocol">
            <span className={`protocolPill ${forward.protocol}`}>{String(forward.protocol || '').toUpperCase()}</span>
            <span className={`statePill ${forward.status}`}>{forwardStatusLabel(forward.status)}</span>
          </div>
          <div className="forwardMain">
            <strong>{forward.note || `${forward.local_ip}:${forward.local_port}`}</strong>
            <span>{forward.local_ip}:{forward.local_port}</span>
          </div>
          <div className="addressList">
            {(forward.public_addresses || []).map((address) => (
              <button key={address} className="addressButton" onClick={() => onCopy?.(address)} title="复制地址">
                <Globe2 size={14} />
                <span>{address}</span>
                <Copy size={13} />
              </button>
            ))}
            {!forward.public_addresses?.length && <span className="muted">暂无公网地址</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

function InfoItem({ label, value }) {
  return (
    <div className="infoItem">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Metric({ icon, label, value, tone = '' }) {
  return (
    <div className={`metric ${tone}`}>
      {React.cloneElement(icon, { size: 20 })}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function defaultForwardForm() {
  return {
    protocol: 'tcp',
    localIp: '127.0.0.1',
    port: '22',
    subdomain: '',
    note: '',
  };
}

function statusLabel(status) {
  if (status === 'online') return '在线';
  if (status === 'offline') return '离线';
  return status || '未知';
}

function forwardStatusLabel(status) {
  if (status === 'active') return '启用';
  if (status === 'paused') return '暂停';
  return status || '未知';
}

function deviceLabel(client) {
  return client?.hostname || client?.name || '--';
}

function formatBytes(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return '--';
  }
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let current = bytes;
  let unitIndex = 0;
  while (current >= 1024 && unitIndex < units.length - 1) {
    current /= 1024;
    unitIndex += 1;
  }
  const digits = current >= 10 || unitIndex === 0 ? 0 : 1;
  return `${current.toFixed(digits)} ${units[unitIndex]}`;
}

function formatDateTime(value) {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

createRoot(document.getElementById('root')).render(<App />);
