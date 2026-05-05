# Roblox Join Coordinator

A web-based coordination tool that connects multiple Roblox instances and lets you trigger a mass "Join" click across all of them from a single dashboard.

## Architecture

```
┌─────────────────┐     HTTP polling      ┌──────────────────┐     WebSocket     ┌─────────────────┐
│  Roblox Script   │ ◄──────────────────► │  FastAPI Backend  │ ◄──────────────► │  Web Dashboard   │
│  (Lua / per      │   /api/register      │  (Python)         │  /ws/dashboard   │  (HTML/JS)       │
│   instance)      │   /api/heartbeat     │                   │                  │                  │
│                  │   /api/result        │  In-memory state  │                  │  Shows clients   │
│  Clicks "Join"   │   /api/disconnect    │  Command queue    │                  │  MASS JOIN btn   │
│  buttons on cmd  │                      │                   │                  │  Activity log    │
└─────────────────┘                       └──────────────────┘                  └─────────────────┘
```

## How It Works

1. **Execute the Lua script** in each Roblox instance — it registers with the backend and starts polling for commands
2. **Open the web dashboard** — see all connected instances in real-time with their status
3. **Click "MASS JOIN"** — the server queues a `join` command for every online instance
4. **Each Roblox script** receives the command, scans all visible GUI elements for text containing "Join", and clicks matching buttons using VirtualInputManager
5. **Results** are reported back to the dashboard showing success/failure per instance

## Quick Start

### 1. Install & run the backend

```bash
pip install fastapi uvicorn[standard] websockets
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 2. Open the dashboard

Navigate to `http://localhost:8000` in your browser.

### 3. Set up the Roblox script

1. Open `roblox_script.lua`
2. Change `SERVER_URL` to your deployed backend URL
3. Execute the script in your Roblox instance(s)

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/register` | POST | Register a new Roblox instance |
| `/api/heartbeat` | POST | Heartbeat + poll for commands |
| `/api/result` | POST | Report command execution result |
| `/api/disconnect` | POST | Unregister an instance |
| `/api/clients` | GET | List all connected clients |
| `/api/join` | POST | Trigger mass join command |
| `/api/health` | GET | Health check |
| `/ws/dashboard` | WS | Real-time dashboard updates |

## Deployment

The backend can be deployed to any platform that supports Python (Fly.io, Railway, Render, etc.). The frontend is served by the backend as static files.

**Important:** The Roblox script uses `HttpService:RequestAsync`, which requires the game to have HttpService enabled. In Roblox Studio, go to Game Settings → Security → Allow HTTP Requests.

## Project Structure

```
├── backend/
│   └── main.py           # FastAPI server
├── frontend/
│   └── index.html        # Web dashboard (single-page)
├── roblox_script.lua      # Standalone Lua script for Roblox
├── pyproject.toml
└── README.md
```
