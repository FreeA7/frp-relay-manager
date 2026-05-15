# Backend

FastAPI backend for the server-side relay manager.

Planned responsibilities:

- admin authentication
- client enrollment and heartbeat handling
- port check requests and results
- forwarding rule CRUD
- frps config generation and reload coordination

The production service should bind to `127.0.0.1:8010` behind nginx.

## Local Run

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

The app initializes SQLite and the admin account on startup.
