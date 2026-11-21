# Deployment & Setup

## Prerequisites

- Python 3.11 or later
- Node.js 18 or later
- pnpm (or npm)
- Git

## Local Development Setup

### 1. Clone the Repository

```bash
git clone <repo-url>
cd Trek-RepoGuide
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
# Or with uv:
uv sync
```

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Required: Get a free API key at https://openrouter.ai/keys
OPENROUTER_API_KEY=sk-or-v1-your-key-here

# Optional: Change the default model
OPENROUTER_MODEL=qwen/qwen-2.5-coder-32b-instruct:free

# Database: leave as-is for local SQLite
TURSO_DATABASE_URL=file:local.db
TURSO_AUTH_TOKEN=

# Frontend URL for CORS
FRONTEND_ORIGIN=http://localhost:5173
```

### 4. Start the Backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

The API is now running at `http://localhost:8000`. Visit `http://localhost:8000/docs` for the interactive Swagger UI.

### 5. Frontend Setup

```bash
cd frontend

# Install dependencies
pnpm install

# Start dev server
pnpm dev
```

The frontend is now running at `http://localhost:5173`.

---

## Project Structure

```
Trek-RepoGuide/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py          # FastAPI routes and SSE streaming
│   │   ├── ingest.py         # Repository cloning, chunking, embedding
│   │   ├── ask.py            # Semantic search, citation verification
│   │   ├── graph.py          # LangGraph workflow (3-node state machine)
│   │   └── db.py             # SQLite/Turso database layer
│   ├── tests/
│   ├── .env
│   ├── .env.example
│   ├── pyproject.toml
│   └── local.db              # Auto-created SQLite database
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   └── client.js     # API client with SSE support
│   │   ├── components/
│   │   │   ├── MarkdownRenderer.jsx
│   │   │   ├── MermaidViewer.jsx
│   │   │   ├── FileViewerModal.jsx
│   │   │   └── ui/           # Reusable UI components
│   │   ├── views/
│   │   │   ├── HomeView.jsx   # Screens 1 & 2 (paste URL, reading)
│   │   │   └── AnswerView.jsx # Screens 3 & 4 (workspace, answer)
│   │   ├── hooks/
│   │   ├── lib/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── index.css
│   ├── package.json
│   ├── vite.config.js
│   └── tailwind.config.js
└── docs/                      # This documentation
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENROUTER_API_KEY` | Yes | — | API key from OpenRouter (free tier works) |
| `OPENROUTER_MODEL` | No | `nvidia/nemotron-3-ultra-550b-a55b:free` | LLM model to use |
| `TURSO_DATABASE_URL` | No | `file:local.db` | Database URL (SQLite file or Turso cloud) |
| `TURSO_AUTH_TOKEN` | No | — | Turso auth token (empty for local SQLite) |
| `FRONTEND_ORIGIN` | No | `http://localhost:5173` | CORS origin for the frontend |
| `USE_LOCAL_DB` | No | `0` | Force local SQLite even if Turso is configured |

---

## Production Deployment

### Backend (Any Python Host)

1. Set environment variables on the host.
2. Install dependencies: `pip install -e .`
3. Run: `uvicorn app.main:app --host 0.0.0.0 --port 8000`

### Frontend (Static Hosting)

1. Build: `cd frontend && pnpm build`
2. Deploy the `frontend/dist/` folder to any static host (Vercel, Netlify, Cloudflare Pages).
3. Update `FRONTEND_ORIGIN` on the backend to match the deployment URL.

### Database (Turso Cloud)

1. Create a Turso database: `turso db create repoask`
2. Get the URL and token: `turso db show repoask --url` and `turso db tokens create repoask`
3. Set `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` in the backend environment.

