# API Reference

## Base URL

```
http://localhost:8000/api/v1
```

---

## Endpoints

### Health Check

```
GET /
```

**Response:**
```json
{ "message": "RepoAsk API is running!", "docs": "/docs" }
```

```
GET /healthz
```

**Response:**
```json
{ "status": "ok", "service": "codeatlas-api" }
```

---

### List Repositories

```
GET /api/v1/repos
```

Returns all indexed repositories, ordered by most recent first.

**Response:**
```json
{
  "repositories": [
    {
      "id": "a1b2c3d4",
      "owner": "pallets",
      "name": "pallets/flask",
      "url": "https://github.com/pallets/flask",
      "created_at": "2026-11-21 14:30:00"
    }
  ]
}
```

---

### Index a Repository

```
POST /api/v1/repos
```

Clones, chunks, embeds, and indexes a public GitHub repository.

**Request body:**
```json
{ "url": "https://github.com/pallets/flask" }
```

**Response (success):**
```json
{
  "status": "success",
  "data": {
    "repo_id": "a1b2c3d4",
    "repo_name": "flask",
    "files_indexed": 142,
    "chunks_indexed": 387
  }
}
```

**Error responses:**
- `400` — Invalid GitHub URL or empty repository
- `500` — Clone failure or internal error

**Behavior:** If the same URL was previously indexed, the existing data is replaced (re-indexed).

---

### Get Repository Metadata

```
GET /api/v1/repos/{repo_id}
```

**Response:**
```json
{
  "id": "a1b2c3d4",
  "owner": "pallets",
  "name": "pallets/flask",
  "url": "https://github.com/pallets/flask",
  "pinned_commit": "a1b2c3d4",
  "default_file": "src/flask/app.py",
  "files_count": 142,
  "branch": "main"
}
```

**Error:** `404` if repository not found.

---

### Ask a Question (SSE Stream)

```
POST /api/v1/repos/{repo_id}/ask
```

Streams the answer as Server-Sent Events.

**Request body:**
```json
{
  "question": "How does request routing work?",
  "conversation_id": null
}
```

**Response:** `text/event-stream` with events:

```
event: status
data: {"step": 1, "title": "Searched the repo", "detail": "Found 8 related files", "state": "done"}

event: status
data: {"step": 2, "title": "Followed connections between files", "detail": "Checked who uses what", "state": "done"}

event: status
data: {"step": 3, "title": "Checking the answer", "detail": "Verified against 5 files", "state": "done"}

event: token
data: {"text": "# "}

event: token
data: {"text": "Request "}

event: citation
data: {"path": "src/flask/app.py", "start_line": 1, "end_line": 45}

event: done
data: {"conversation_id": "a1b2c3d4", "verified_files_count": 5}
```

---

### Ask a Question (Synchronous)

```
POST /api/v1/repos/{repo_id}/ask/sync
```

Returns the full answer as JSON (no streaming).

**Request body:**
```json
{
  "question": "What is this repo about?",
  "conversation_id": null
}
```

**Response:**
```json
{
  "answer": "# Repository Overview\n\n> **Short answer:** ...",
  "citations": [
    { "path": "README.md", "start_line": 1, "end_line": 30 }
  ],
  "retrieved_chunks": [
    { "path": "README.md", "lines": "1-30" }
  ],
  "verified_files_count": 3
}
```

---

### Get File Content

```
GET /api/v1/repos/{repo_id}/file?path=app/main.py&start=1&end=50
```

Returns lines of an indexed file for the source viewer modal.

**Query parameters:**
- `path` (required) — Relative file path
- `start` (optional, default 1) — First line number
- `end` (optional, default 0 = all) — Last line number

**Response:**
```json
{
  "path": "app/main.py",
  "start_line": 1,
  "end_line": 50,
  "lines": [
    { "n": 1, "text": "from fastapi import FastAPI" },
    { "n": 2, "text": "from app.ingest import ingest_repository" }
  ]
}
```

**Error:** `404` if file not found.

---

## CORS Configuration

The backend allows requests from:
- `http://localhost:5173` (Vite dev server)
- `http://127.0.0.1:5173`
- `http://localhost:3000`
- `http://127.0.0.1:3000`
- Any `localhost` or `127.0.0.1` origin via regex

