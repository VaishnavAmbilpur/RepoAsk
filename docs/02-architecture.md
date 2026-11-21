# Architectural Flow

## System Overview

RepoAsk is a monorepo with 2 main services: a **React SPA frontend** and a **FastAPI backend**. The backend handles repository ingestion, vector search, and LLM-powered answer generation through a LangGraph state machine.

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
│  │ (Routes) │  │ (Clone & │  │ (Search &│  │(LangGraph│ │
│  │          │  │  Index)  │  │ Verify)  │  │ Workflow)│ │
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

## Data Flow: Indexing a Repository

```
User pastes URL
      │
      ▼
  POST /api/v1/repos  { url }
      │
      ▼
  parse_github_url()         ← Validate and extract owner/name
      │
      ▼
  git.Repo.clone_from()      ← Shallow clone (depth=1)
      │
      ▼
  Walk file tree              ← Skip: node_modules, .git, binaries, images, locks
      │
      ▼
  Store each file             ← INSERT INTO files (id, repo_id, path, lines, content)
      │
      ▼
  Language-aware chunking     ← RecursiveCharacterTextSplitter.from_language()
      │                         chunk_size=900, overlap=120
      ▼
  Priority balancing          ← Cap at 450 chunks. Keep README, entry points first.
      │
      ▼
  FastEmbed embedding         ← BAAI/bge-small-en-v1.5, batch_size=64
      │
      ▼
  Batch INSERT into chunks    ← 50 statements per batch
      │
      ▼
  Cleanup clone directory
      │
      ▼
  Return { repo_id, files_indexed, chunks_indexed }
```

## Data Flow: Asking a Question (RAG Pipeline)

```
User types question
      │
      ▼
  POST /api/v1/repos/{id}/ask  { question }
      │
      ▼
  SSE stream begins
      │
      ▼
  ┌─────────────────────────────────────────┐
  │         LangGraph State Machine         │
  │                                         │
  │  START                                  │
  │    │                                    │
  │    ▼                                    │
  │  retrieve_node                          │
  │    ├─ Embed the question                │
  │    ├─ Fetch all chunks for this repo    │
  │    ├─ Compute cosine similarity         │
  │    ├─ Boost README for overview queries │
  │    └─ Return top 10 chunks + context    │
  │    │                                    │
  │    ▼                                    │
  │  synthesize_node                        │
  │    ├─ Build system prompt (STE rules)   │
  │    ├─ Build user prompt (context + Q)   │
  │    ├─ Call OpenRouter with fallback     │
  │    └─ Return raw markdown answer        │
  │    │                                    │
  │    ▼                                    │
  │  verify_node                            │
  │    ├─ Parse citations from answer       │
  │    ├─ Check each path exists in DB      │
  │    ├─ Consolidate overlapping ranges    │
  │    └─ Return clean answer + citations   │
  │    │                                    │
  │    ▼                                    │
  │   END                                   │
  └─────────────────────────────────────────┘
      │
      ▼
  Stream status events → token events → citation events → done event
```

## SSE Event Protocol

The `/ask` endpoint streams Server-Sent Events in this order:

| Event | Payload | Description |
|---|---|---|
| `status` | `{ step, title, detail, state }` | Progress updates (3 steps: search, connect, verify) |
| `token` | `{ text }` | Individual words of the answer, streamed for typing effect |
| `citation` | `{ path, start_line, end_line }` | Each verified source file reference |
| `done` | `{ conversation_id, verified_files_count }` | Signals completion |
| `error` | `{ message }` | Error details if the pipeline fails |

## Frontend Screen Flow

```
Screen 1: HomeView (paste URL)
    │
    ▼  POST /repos
Screen 2: HomeView (reading/progress)
    │
    ▼  navigate(/repo/{id})
Screen 3: AnswerView (empty state → ask question)
    │
    ▼  POST /repos/{id}/ask (SSE)
Screen 4: AnswerView (thinking → answer document)
```

The AnswerView uses a **3-column layout**:
- **Left sidebar (240px, collapsible):** Question history + "New question" button
- **Center column (flex):** Answer document with toolbar, Mermaid diagrams, follow-up suggestions
- **Right sidebar (280px):** Table of contents + source file links

