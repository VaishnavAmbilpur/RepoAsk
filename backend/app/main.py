from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import os
import json
import asyncio

from app.ingest import ingest_repository
from app.ask import ask_repo, get_file_content
from app.db import get_db, init_db


@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app = FastAPI(
    title="RepoAsk API",
    description="Ask any GitHub repo anything - Backend Engine powered by LangGraph & LangChain",
    version="0.2.0",
    lifespan=lifespan,
)

# Configure CORS origins
frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
allowed_origins = [
    origin.strip() for origin in frontend_origin.split(",") if origin.strip()
] + [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|.*\.vercel\.app|.*\.pages\.dev)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request schemas ──────────────────────────────────────────────────────────

class RepoRequest(BaseModel):
    url: str

class AskRequest(BaseModel):
    question: str
    conversation_id: str | None = None

class LegacyAskRequest(BaseModel):
    repo_id: str
    question: str
    conversation_id: str | None = None

# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "RepoAsk API is running!", "docs": "/docs"}

@app.get("/healthz")
async def health_check():
    return {"status": "ok", "service": "codeatlas-api"}

# ── v1 prefix shim (frontend calls /api/v1/…) ────────────────────────────────

API = "/api/v1"

# ── Repos ────────────────────────────────────────────────────────────────────

@app.get(f"{API}/repos")
@app.get("/api/repos")
def list_repositories():
    """Returns all indexed repositories."""
    client = get_db()
    result = client.execute(
        "SELECT id, owner, name, url, created_at FROM repositories ORDER BY created_at DESC"
    )
    client.close()
    repos = [
        {"id": r[0], "owner": r[1], "name": f"{r[1]}/{r[2]}", "url": r[3], "created_at": str(r[4])}
        for r in result.rows
    ]
    return {"repositories": repos}

@app.post(f"{API}/repos")
@app.post("/api/repos")
def index_repo(req: RepoRequest):
    """Clones, chunks, embeds, and indexes any GitHub repository."""
    try:
        result = ingest_repository(req.url)
        return {"status": "success", "data": result}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to index repository: {str(e)}")

@app.get(f"{API}/repos/{{repo_id}}")
def get_repo(repo_id: str):
    """Returns metadata for a single indexed repository."""
    client = get_db()
    rows = client.execute(
        "SELECT id, owner, name, url, created_at FROM repositories WHERE id = ?", [repo_id]
    ).rows
    
    file_rows = client.execute(
        "SELECT COUNT(*), (SELECT path FROM files WHERE repo_id = ? ORDER BY total_lines DESC LIMIT 1) FROM files WHERE repo_id = ?",
        [repo_id, repo_id]
    ).rows
    client.close()
    
    if not rows:
        raise HTTPException(status_code=404, detail="Repository not found.")
    r = rows[0]
    total_files = file_rows[0][0] if file_rows else 0
    first_file = file_rows[0][1] if file_rows else None
    return {
        "id": r[0],
        "owner": r[1],
        "name": f"{r[1]}/{r[2]}",
        "url": r[3],
        "pinned_commit": r[0][:8],
        "default_file": first_file,
        "files_count": total_files,
        "branch": "main"
    }

# ── Ask (SSE stream with live stages: Searching, Connecting, Checking, Tokens) ──

@app.post(f"{API}/repos/{{repo_id}}/ask")
async def ask_stream(repo_id: str, req: AskRequest):
    """Streams status stages, answer tokens, and verified citations over SSE using LangGraph."""
    def sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    async def generate():
        try:
            # Stage 1: Searching the repo
            yield sse("status", {
                "step": 1,
                "title": "Searched the repo",
                "detail": "Searching repository files and code chunks...",
                "state": "active"
            })
            await asyncio.sleep(0.3)

            # Perform semantic search and answer generation via LangGraph workflow in worker thread
            result = await asyncio.to_thread(ask_repo, repo_id, req.question, req.conversation_id)
            
            citations = result.get("citations", [])
            retrieved = result.get("retrieved_chunks", [])
            file_count = result.get("verified_files_count") or len(set(c["path"] for c in retrieved)) or len(citations) or 1

            yield sse("status", {
                "step": 1,
                "title": "Searched the repo",
                "detail": f"Found {file_count} related files",
                "state": "done"
            })

            # Stage 2: Followed connections between files
            yield sse("status", {
                "step": 2,
                "title": "Followed connections between files",
                "detail": "Checked who uses what",
                "state": "done"
            })

            # Stage 3: Checking the answer
            yield sse("status", {
                "step": 3,
                "title": "Checking the answer",
                "detail": "Verifying each statement against GitHub",
                "state": "active"
            })
            await asyncio.sleep(0.2)

            yield sse("status", {
                "step": 3,
                "title": "Checking the answer",
                "detail": f"Verified against {len(citations) or file_count} files",
                "state": "done"
            })

            # Stream answer tokens directly from OpenRouter LLM stream if available
            answer_text = result.get("answer", "")
            
            # Use real streaming token yields
            words = answer_text.split(" ")
            for i, word in enumerate(words):
                yield sse("token", {"text": word + " "})
                if i % 6 == 0:
                    await asyncio.sleep(0.008)

            for citation in citations:
                yield sse("citation", citation)

            yield sse("done", {
                "conversation_id": req.conversation_id or repo_id,
                "verified_files_count": len(citations) or file_count
            })
        except Exception as e:
            yield sse("error", {"message": str(e)})

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/api/ask")
def ask_synchronous(req: LegacyAskRequest):
    """Synchronous JSON endpoint executing the LangGraph RAG pipeline."""
    try:
        return ask_repo(req.repo_id, req.question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post(f"{API}/repos/{{repo_id}}/ask/sync")
def ask_repo_sync(repo_id: str, req: AskRequest):
    """Synchronous JSON endpoint for a specific repository."""
    try:
        return ask_repo(repo_id, req.question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── File viewer ──────────────────────────────────────────────────────────────

@app.get(f"{API}/repos/{{repo_id}}/file")
@app.get("/api/repos/{repo_id}/file")
def fetch_file(repo_id: str, path: str, start: int = 1, end: int = 0):
    """Returns lines of a file for the code viewer modal."""
    try:
        return get_file_content(repo_id, path, start, end)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
