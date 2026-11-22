# RepoAsk

> Paste any public GitHub URL. Ask questions about the repository in plain English. Get structured answers with verified citations, diagrams, and source file links.

---

## What Is RepoAsk

Developers spend most of their time **reading** code, not writing it. When they open a new GitHub repository, they face thousands of files, nested folders, and no clear entry point.

Existing tools do not solve this:
- **GitHub search** finds files and symbols but does not explain how they connect.
- **README files** go stale and cover only the surface.
- **ChatGPT / Copilot** do not have the full codebase context and hallucinate file names.

**RepoAsk** solves this. A user pastes a GitHub URL, and the system:
1. Shallow-clones the repository.
2. Splits code into language-aware chunks (18+ languages).
3. Generates vector embeddings.
4. Answers any question with a RAG pipeline that retrieves, synthesizes, and verifies every citation.

Every answer is a formatted document — with a title, short-answer callout, Mermaid diagrams (when helpful), and clickable source file links that point to real files with valid line numbers.

---

## Why This Architecture

| Decision | Rationale |
|----------|-----------|
| **OpenRouter as the only LLM gateway** | Single API for 100+ models. Free-tier models with zero cost. Swap models by changing one env variable. |
| **LangGraph state machine** | Typed state flows between 3 deterministic nodes. Easy to debug — log state after each node. Add conditional edges later without rewriting nodes. |
| **Hybrid search (Vector + BM25)** | Vector similarity finds semantically related chunks. BM25 keyword matching catches exact identifiers that embeddings miss. Combined score: 60% cosine + 40% BM25. |
| **SQLite / Turso (no vector DB)** | With a cap of 450 chunks per repo, brute-force cosine similarity finishes in under 50 ms. A dedicated vector database adds complexity not justified at this scale. |
| **FastEmbed in-process embeddings** | 33 MB model, 384 dimensions, runs on CPU. No external API calls during indexing. Batch of 450 chunks completes in under 10 seconds. |
| **AST-aware chunking** | `RecursiveCharacterTextSplitter.from_language()` splits at function and class boundaries for 18+ languages instead of breaking code at arbitrary points. |
| **ASD-STE100 writing constraints** | 13 Simplified Technical English rules in the system prompt produce consistent, scannable answers regardless of which LLM model runs. |
| **Citation verification gate** | Every file path in the answer is checked against the database. Invalid citations are removed. No dead links. No phantom files. |

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                      Browser (SPA)                       │
│  React 18 + React Router + Tailwind CSS + Mermaid        │
│  HomeView → AnswerView (3-column workspace)              │
└────────────────────────┬─────────────────────────────────┘
                         │ HTTP / SSE
                         ▼
┌──────────────────────────────────────────────────────────┐
│                   FastAPI Backend                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │ main.py  │  │ ingest.py│  │  ask.py   │  │ graph.py │ │
│  │ (Routes) │  │ (Clone & │  │ (Search & │  │(LangGraph│ │
│  │          │  │  Index)  │  │  Verify)  │  │ Workflow)│ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │
│                         │                                 │
│              ┌──────────┴──────────┐                     │
│              │      db.py          │                     │
│              │  (SQLite / Turso)   │                     │
│              └─────────────────────┘                     │
└──────────────────────────────────────────────────────────┘
                         │
              ┌──────────┴──────────┐
              │   External Services  │
              │  - GitHub (clone)    │
              │  - OpenRouter (LLM)  │
              └─────────────────────┘
```

---

## User Flow

```
Screen 1: HomeView (paste GitHub URL)
    │
    ▼  POST /api/v1/repos
Screen 2: HomeView (5-step progress checklist → indexing)
    │
    ▼  navigate(/repo/{id})
Screen 3: AnswerView (empty workspace → 3 suggestion chips)
    │
    ▼  POST /api/v1/repos/{id}/ask (SSE stream)
Screen 4: AnswerView (thinking → answer document)
```

**Screen 3 — AnswerView** uses a 3-column layout:
- **Left sidebar (240 px, collapsible):** Question history and "New question" button.
- **Center column (flex):** Answer document with Preview/Markdown toggle, Copy .md, Download .md.
- **Right sidebar (280 px):** Table of contents and source file links to GitHub.

---

## AI Pipeline (LangGraph)

The pipeline is a deterministic state machine with 3 nodes. Every question runs through all 3 nodes in order.

```
START → retrieve_node → synthesize_node → verify_node → END
```

### Stage 1 — Retrieve

1. Embed the user question with the same model used during indexing (BAAI/bge-small-en-v1.5, 384 dimensions).
2. Load all chunks for the repository from the database.
3. Compute cosine similarity between the query vector and each chunk vector.
4. Apply scoring boosts: README (+0.65 for overview queries), manifest files (+0.25), architecture docs (+0.35).
5. Penalize short chunks (under 30 characters): −0.40.
6. Sort by adjusted score and return the top K results.

**Dual-Track Retrieval:**
- **Track A — Local (K = 5):** For specific questions ("How does verifySignature work?"). Uses hybrid search: 60% Vector + 40% BM25.
- **Track B — Global (K = 12–16):** For set-aggregation questions ("List all schemas"). Runs a SQL file-tree pattern scan, then harvests one definition chunk per matching file.

### Stage 2 — Synthesize

1. Build a system prompt with ASD-STE100 rules (13 constraints).
2. Build a user prompt with retrieved context and the question.
3. Call OpenRouter with a fallback chain of up to 4 models:
   - User-configured model → `nvidia/nemotron-3-ultra-550b-a55b:free` → `baidu/ernie-5.5-flash-preview:free` → `particle-ai/particle-1:free`
4. Temperature: 0.2. Max tokens: 1,600. Timeout: 12 seconds per model.
5. If all models fail, return a hardcoded fallback answer from the first retrieved chunk.

### Stage 3 — Verify

1. Parse citation patterns from the answer text with regex.
2. Check each file path against the `files` table in the database.
3. Try suffix matching if the exact path does not exist.
4. Clamp line ranges to the actual file length.
5. Merge overlapping ranges (gap tolerance: 15 lines).
6. Cap at 5 unique citations per answer.
7. Remove invalid citations. If none survive, attach the top retrieved chunk as fallback.

---

## Challenges Faced

### Challenge 1 — The Global Query Problem

**What happened:** A user asked "Tell me all schemas in the repository." The system returned only 2 chunks (README and one utility file). It missed `models/organization.js`, `models/webhook.js`, and `models/user.js`.

**Root cause:**
1. **Point-Lookup vs. Set-Aggregation mismatch.** Vector similarity finds the nearest single chunk. It cannot gather distributed sets across different files.
2. **Semantic granularity gap.** `models/user.js` contains field names (`email`, `passwordHash`) but not the phrase "this is a schema." The README scored higher because it contained the word "schemas."
3. **Fixed K = 4 window.** A repository with 10 schemas across 10 files cannot fit in 4 chunks.

**Solution — Dual-Track Retrieval Engine:**
- A query-intent classifier separates specific questions (Track A — Local) from collection questions (Track B — Global).
- Track B runs a SQL `LIKE` scan on the file tree, harvests one chunk per matching file, and expands K to 12–16.
- Priority protection in `ingest.py` ensures schema, model, and route directories are never dropped during chunk-budget trimming.

See [docs/12-challenges-global-query-dual-track.md](docs/12-challenges-global-query-dual-track.md) for the full analysis with flowcharts.

### Challenge 2 — 512 MB RAM Limit on Render Free Tier

ONNX Runtime + FastEmbed consumed more than 512 MB. The service crashed on boot with OOM.

**Solution:** Moved primary embeddings to the OpenRouter cloud embeddings API (zero local RAM). Kept FastEmbed as a fallback for local development.

### Challenge 3 — SSE Stream Disconnection

Render's reverse proxy killed idle TCP connections after approximately 15 seconds. During LLM generation, the stream had no data flowing and was terminated.

**Solution:** Implemented heartbeat `: ping` events every 2.5 seconds and added the `X-Accel-Buffering: no` header to disable proxy buffering.

### Challenge 4 — UI Flickering on Question Input

CSS Grid `transition-all` combined with shared `question` state caused full-page re-renders when the user typed.

**Solution:** Isolated the `QuestionBar` into its own React component and switched the layout from CSS Grid to Flexbox with locked sidebar widths.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 18, React Router v7, Tailwind CSS 3, Mermaid 12, react-markdown, DOMPurify |
| Backend | FastAPI, Python 3.11+, LangGraph, LangChain, HTTPX |
| Embeddings | OpenRouter Cloud Embeddings (primary), FastEmbed BAAI/bge-small-en-v1.5 (fallback) |
| Search | Cosine similarity + BM25 hybrid, brute-force over 450 chunks |
| Database | SQLite (local dev), Turso Cloud LibSQL (production) |
| LLM Gateway | OpenRouter — free-tier models with 4-model fallback chain |
| Git | GitPython — shallow clone (depth=1) |
| Package Managers | uv (backend), pnpm (frontend) |
| Build | Vite 5 |
| Deployment | Render (backend), Vercel (frontend), GitHub Actions keep-alive cron |

---

## Project Structure

```
RepoAsk/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI routes and SSE streaming
│   │   ├── ingest.py         # Repository cloning, chunking, embedding
│   │   ├── ask.py            # Semantic search, citation verification
│   │   ├── graph.py          # LangGraph workflow (3-node state machine)
│   │   └── db.py             # SQLite / Turso database layer
│   ├── .env.example
│   ├── requirements.txt
│   └── Procfile
├── frontend/
│   ├── src/
│   │   ├── views/
│   │   │   ├── HomeView.jsx   # Screens 1 & 2 (paste URL, progress)
│   │   │   └── AnswerView.jsx # Screens 3 & 4 (workspace, answer)
│   │   ├── components/
│   │   │   ├── MarkdownRenderer.jsx
│   │   │   ├── MermaidViewer.jsx
│   │   │   └── FileViewerModal.jsx
│   │   └── api/
│   │       └── client.js     # API client with SSE support
│   ├── package.json
│   ├── vite.config.js
│   └── tailwind.config.js
└── docs/                      # 13 documentation files
```

---

## Quick Start (Local Development)

### Prerequisites
- Python 3.11+
- Node.js 18+
- pnpm
- Git

### Backend

```bash
cd backend
python -m venv .venv

# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
# Or with uv:
uv sync

cp .env.example .env
# Edit .env → add your OpenRouter API key (free at https://openrouter.ai/keys)

uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

Open `http://localhost:5173`, paste a GitHub URL, and ask a question.

> **Do not commit the `.env` file.** It contains secret API keys.

---

## Deployment

| Component | Service | Cost |
|-----------|---------|------|
| Backend | Render Web Service | Free |
| Frontend | Vercel | Free |
| Database | Turso Cloud | Free (9 GB) |
| Keep-alive | GitHub Actions cron (every 14 min) | Free |

See [docs/11-deployment-guide.md](docs/11-deployment-guide.md) for step-by-step instructions.

---

## Roadmap

### Completed
- Repository cloning and indexing pipeline
- Language-aware AST chunking (18+ languages)
- LangGraph RAG pipeline (retrieve → synthesize → verify)
- Citation verification gate
- SSE streaming with live status updates
- Mermaid diagram rendering
- File viewer modal with line highlighting
- Multi-model LLM fallback chain
- Dual-Track retrieval engine (Local + Global)
- ASD-STE100 writing constraints

### Planned
- **HyDE query translation** — Turn a question into a synthetic document before retrieval.
- **AST-aware chunking with Tree-Sitter** — Symbol-level code splitting for more precise chunks.
- **Corrective RAG (CRAG)** — Self-reflection loop to detect and repair inaccurate answers.
- **In-app split-screen code viewer** — Show the code snippet alongside the answer.
- **Lightweight call graph** — Store import relationships in Turso for impact analysis.
- **Conversation memory** — Pass previous Q&A as context for follow-up questions.
- **Private repository support** — Accept a GitHub PAT for authenticated cloning.

See [docs/10-roadmap.md](docs/10-roadmap.md) for the full list.

---

## Documentation

| # | Document | Topic |
|---|----------|-------|
| 1 | [Idea & Solution](docs/01-idea-and-solution.md) | Problem, solution, target users, success metrics |
| 2 | [Architecture](docs/02-architecture.md) | System diagram, data flows, SSE protocol |
| 3 | [User Flow](docs/03-user-flow.md) | Screen-by-screen walkthrough |
| 4 | [Architectural Decisions & Tech Stack](docs/04-architectural-decisions-and-tech-stack.md) | 7 ADRs with rationale and trade-offs |
| 5 | [AI Model Pipeline](docs/05-ai-model-pipeline.md) | RAG pipeline details, embeddings, scoring |
| 6 | [Data Model](docs/06-data-model.md) | Database schema, entity relationships, limits |
| 7 | [API Reference](docs/07-api-reference.md) | Every endpoint with request/response examples |
| 8 | [Deployment & Setup](docs/08-deployment-and-setup.md) | Local dev, project structure, env variables |
| 9 | [Security & Limitations](docs/09-security-and-limitations.md) | Security model, known limitations |
| 10 | [Roadmap](docs/10-roadmap.md) | Completed features, short-term and medium-term plans |
| 11 | [Deployment Guide](docs/11-deployment-guide.md) | Free zero cold-start deployment guide |
| 12 | [Challenges: Global Query & Dual-Track](docs/12-challenges-global-query-dual-track.md) | Root cause analysis and Dual-Track solution |
| U1 | [Upgrade 01 — AI Pipeline Overhaul](docs/Upgrade_01.md) | 9-phase plan for LangChain and LangGraph |

---

## License

This project is for educational and portfolio purposes.
