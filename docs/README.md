# RepoAsk — Documentation Index

> Paste any public GitHub URL and ask questions about the repository in plain English. Get structured answers with verified citations, diagrams, and source file links.

## Reading Order

| # | Document | What It Covers |
|---|---|---|
| 1 | [Idea & Solution](01-idea-and-solution.md) | The problem, the solution, target users, success metrics |
| 2 | [Architecture](02-architecture.md) | System diagram, data flows for indexing and asking, SSE protocol, screen flow |
| 3 | [User Flow](03-user-flow.md) | Screen-by-screen walkthrough of every user interaction |
| 4 | [Architectural Decisions & Tech Stack](04-architectural-decisions-and-tech-stack.md) | Full tech stack table, 7 ADRs with rationale and trade-offs |
| 5 | [AI Model Pipeline](05-ai-model-pipeline.md) | RAG pipeline details: retrieval, synthesis, verification, embeddings, scoring |
| 6 | [Data Model](06-data-model.md) | Database schema, entity relationships, indexing limits, filtered content |
| 7 | [API Reference](07-api-reference.md) | Every endpoint with request/response examples |
| 8 | [Deployment & Setup](08-deployment-and-setup.md) | Local dev setup, project structure, environment variables, production deployment |
| 9 | [Security & Limitations](09-security-and-limitations.md) | Security model, known limitations by category |
| 10 | [Roadmap](10-roadmap.md) | Completed features, short-term improvements, medium-term vision |
| **U1** | **[Upgrade 01 — AI Pipeline Overhaul](Upgrade_01.md)** | **9-phase plan to use LangChain & LangGraph at full potential, with alternatives for each decision** |

## Quick Start

```bash
# Backend
cd backend
cp .env.example .env     # Add your OpenRouter API key
uv sync                  # or: pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
pnpm install
pnpm dev
```

Then open `http://localhost:5173`, paste a GitHub URL, and ask a question.

