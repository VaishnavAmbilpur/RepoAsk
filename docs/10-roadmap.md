# Roadmap & Future Improvements

## Completed ✅

- [x] Repository cloning and indexing pipeline
- [x] Language-aware AST chunking (18+ languages)
- [x] In-process vector embeddings with FastEmbed
- [x] LangGraph RAG pipeline (retrieve → synthesize → verify)
- [x] Citation verification gate
- [x] SSE streaming with live status updates
- [x] Mermaid diagram rendering
- [x] File viewer modal with line highlighting
- [x] Question history (session-scoped)
- [x] Collapsible left sidebar
- [x] ASD-STE100 writing constraints
- [x] Multi-model LLM fallback chain

---

## Short-Term Improvements 🔜

### Backend
- [ ] **Conversation memory** — Store conversation history and pass previous Q&A as context for follow-up questions
- [ ] **Keyword + semantic hybrid search** — Combine BM25 keyword matching with vector similarity for better retrieval
- [ ] **Multi-hop retrieval** — Follow `import` and `require` statements to retrieve related files in a second pass
- [ ] **Incremental re-indexing** — Detect which files changed and only re-embed those chunks
- [ ] **Branch selection** — Let the user choose which branch to index
- [ ] **Private repository support** — Accept a GitHub PAT for authenticated cloning

### Frontend
- [ ] **Persistent question history** — Save Q&A history to localStorage or the backend database
- [ ] **Mobile-responsive layout** — Collapse both sidebars on small screens
- [ ] **Dark/light theme toggle** — Support both color schemes
- [ ] **Collapsible right sidebar** — Match the left sidebar toggle behavior
- [ ] **Search within answers** — Ctrl+F-style search across all past answers
- [ ] **Export to PDF** — Generate PDF documents from answers

### AI Pipeline
- [ ] **Streaming token generation** — Stream tokens directly from the LLM instead of batching the full answer
- [ ] **Custom embedding models** — Let users configure the embedding model
- [ ] **Answer caching** — Cache answers for identical question+repo pairs
- [ ] **Multi-language prompts** — Support non-English questions

---

## Medium-Term Features 🔮

- [ ] **Repository comparison** — Index 2 repos and ask "how does X handle Y differently from Z?"
- [ ] **Code change impact analysis** — "What would break if I changed this file?"
- [ ] **Interactive code tours** — Generate step-by-step walkthroughs of specific flows
- [ ] **Team workspaces** — Share indexed repos and answers across a team
- [ ] **Webhook-based auto-reindex** — Automatically re-index when new commits are pushed
- [ ] **Plugin system** — Allow custom chunking strategies and prompt templates

---

## Infrastructure Ideas 🏗️

- [ ] **pgvector migration** — Move to PostgreSQL with pgvector for ANN search at scale
- [ ] **Redis caching layer** — Cache embeddings and LLM responses
- [ ] **Celery task queue** — Move long-running indexing jobs to background workers
- [ ] **Rate limiting** — Token bucket rate limiting per IP or API key
- [ ] **Authentication** — OAuth2 / API key authentication
- [ ] **Observability** — OpenTelemetry tracing for the full pipeline
- [ ] **Cost tracking** — Track LLM token usage and costs per query

