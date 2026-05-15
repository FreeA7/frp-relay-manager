import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  ClipboardCopy,
  LogOut,
  Monitor,
  Play,
  Plus,
  RadioTower,
  RefreshCcw,
  Server,
  ShieldCheck,
  Terminal,
} from 'lucide-react';
import './styles.css';

const API_BASE = import.meta.env.VITE_API_BASE || '';
const ADMIN_EMAIL = 'freea7@futurememetech.com';

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
            <h1>FRP Relay</h1>
            <p>{ADMIN_EMAIL}</p>
          </div>
        </div>
        <label>
          Password
          <input
            type="password"
            value={password}
            autoFocus
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Admin password from server .env"
          />
        </label>
        {error && <div className="errorBox">{error}</div>}
        <button className="primaryButton" disabled={loading || !password}>
          <ShieldCheck size={18} />
          {loading ? 'Signing in' : 'Sign in'}
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
  const [port, setPort] = useState('22');
  const [protocol, setProtocol] = useState('tcp');
  const [subdomain, setSubdomain] = useState('');
  const [note, setNote] = useState('');
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
      setClients(clientData.items || []);
      setForwards(forwardData.items || []);
      setDashboard(dashboardData);
      if (!selectedClient && clientData.items?.length) {
        setSelectedClient(clientData.items[0].client_id);
      }
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, []);

  const selected = useMemo(
    () => clients.find((client) => client.client_id === selectedClient),
    [clients, selectedClient],
  );

  async function createEnrollment() {
    setMessage('');
    setError('');
    try {
      const result = await api('/api/enrollment-tokens', {
        method: 'POST',
        body: JSON.stringify({ label: 'panel generated', expires_in_hours: 24 }),
      });
      await navigator.clipboard?.writeText(result.token);
      setMessage(`Enrollment token created and copied: ${result.token}`);
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
          protocol,
          host: '127.0.0.1',
          port: Number(port),
        }),
      });
      setMessage(`Port check queued: ${result.id}`);
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
        protocol,
        local_ip: '127.0.0.1',
        local_port: Number(port),
        note,
      };
      if (protocol === 'http') {
        body.subdomain = subdomain;
      }
      const result = await api('/api/forwards', {
        method: 'POST',
        body: JSON.stringify(body),
      });
      setMessage(`Forward created: ${result.public_addresses.join(', ')}`);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <main className="appShell">
      <header className="topBar">
        <div className="brandRow">
          <RadioTower size={26} />
          <div>
            <h1>FRP Relay</h1>
            <p>{dashboard?.panel_domain || 'panel.tunnel.freea7.fun'}</p>
          </div>
        </div>
        <div className="topActions">
          <button className="iconButton" title="Refresh" onClick={load}>
            <RefreshCcw size={18} />
          </button>
          <button className="iconButton" title="Logout" onClick={onLogout}>
            <LogOut size={18} />
          </button>
        </div>
      </header>

      {(error || message) && (
        <section className={error ? 'errorBox' : 'messageBox'}>{error || message}</section>
      )}

      <section className="metricsGrid">
        <Metric icon={<Monitor />} label="Clients" value={dashboard?.client_count ?? clients.length} />
        <Metric icon={<Activity />} label="Online" value={dashboard?.online_client_count ?? 0} />
        <Metric icon={<Server />} label="Forwards" value={dashboard?.forward_count ?? forwards.length} />
        <Metric icon={<Terminal />} label="Pending checks" value={dashboard?.pending_port_check_count ?? 0} />
      </section>

      <section className="workspaceGrid">
        <div className="panel">
          <div className="panelHeader">
            <h2>Clients</h2>
            <button className="secondaryButton" onClick={createEnrollment}>
              <ClipboardCopy size={16} />
              Token
            </button>
          </div>
          <div className="clientList">
            {clients.map((client) => (
              <button
                key={client.client_id}
                className={`clientRow ${client.client_id === selectedClient ? 'active' : ''}`}
                onClick={() => setSelectedClient(client.client_id)}
              >
                <span className={`statusDot ${client.status}`} />
                <span>
                  <strong>{client.name}</strong>
                  <small>{client.hostname} · {client.os}</small>
                </span>
              </button>
            ))}
            {!clients.length && <p className="muted">No clients registered yet.</p>}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2>Port and Forward</h2>
          </div>
          <div className="formGrid">
            <label>
              Client
              <select value={selectedClient} onChange={(event) => setSelectedClient(event.target.value)}>
                {clients.map((client) => (
                  <option key={client.client_id} value={client.client_id}>{client.name}</option>
                ))}
              </select>
            </label>
            <label>
              Protocol
              <select value={protocol} onChange={(event) => setProtocol(event.target.value)}>
                <option value="tcp">TCP</option>
                <option value="udp">UDP</option>
                <option value="http">HTTP</option>
              </select>
            </label>
            <label>
              Local port
              <input value={port} onChange={(event) => setPort(event.target.value)} inputMode="numeric" />
            </label>
            <label>
              Subdomain
              <input
                value={subdomain}
                onChange={(event) => setSubdomain(event.target.value)}
                disabled={protocol === 'tcp' || protocol === 'udp'}
                placeholder="HTTP only"
              />
            </label>
            <label className="wide">
              Note
              <input value={note} onChange={(event) => setNote(event.target.value)} placeholder="ssh, web, database..." />
            </label>
          </div>
          <div className="presetRow">
            {[22, 80, 443, 3306, 5432, 6379, 8080].map((preset) => (
              <button key={preset} onClick={() => setPort(String(preset))}>{preset}</button>
            ))}
          </div>
          <div className="actionRow">
            <button className="secondaryButton" disabled={!selected} onClick={requestPortCheck}>
              <Play size={16} />
              Probe
            </button>
            <button className="primaryButton" disabled={!selected} onClick={createForward}>
              <Plus size={16} />
              Create forward
            </button>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panelHeader">
          <h2>Forwards</h2>
        </div>
        <div className="table">
          <div className="tableHead">
            <span>Protocol</span>
            <span>Local</span>
            <span>Public address</span>
            <span>Status</span>
          </div>
          {forwards.map((forward) => (
            <div className="tableRow" key={forward.id}>
              <span>{forward.protocol.toUpperCase()}</span>
              <span>{forward.local_ip}:{forward.local_port}</span>
              <span>{forward.public_addresses.join(' · ')}</span>
              <span>{forward.status}</span>
            </div>
          ))}
          {!forwards.length && <p className="muted">No forwarding rules yet.</p>}
        </div>
      </section>
    </main>
  );
}

function Metric({ icon, label, value }) {
  return (
    <div className="metric">
      {React.cloneElement(icon, { size: 20 })}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
