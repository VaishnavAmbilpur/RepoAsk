# Architectural Decisions & Tech Stack

## Tech Stack Summary

| Layer | Technology | Why |
|---|---|---|
| **Frontend Framework** | React 18 | Component model, ecosystem, fast dev cycle |
| **Routing** | React Router v7 | File-based mental model, nested routes |
| **Styling** | Tailwind CSS 3 | Utility-first, no context-switching to CSS files |
| **Icons** | Lucide React | Consistent, tree-shakeable icon set |
| **Markdown Rendering** | react-markdown + remark-gfm | GFM tables, task lists, strikethrough |
| **Diagrams** | Mermaid 12 | Flowcharts, sequence diagrams, ER diagrams from text |
| **Sanitization** | DOMPurify | Prevent XSS from user-generated markdown |
| **Build Tool** | Vite 5 | Fast HMR, ESM-native, optimized builds |
| **Testing** | Vitest + Testing Library | Jest-compatible, Vite-native |
| **Backend Framework** | FastAPI | Async, auto-docs, Pydantic validation |
| **Language** | Python 3.11+ | LangChain/LangGraph ecosystem, ML libraries |
| **Database** | SQLite (local) / Turso (cloud) | Zero-config local dev, managed cloud option |
| **Embeddings** | FastEmbed (BAAI/bge-small-en-v1.5) | In-process, no GPU needed, 384-dim vectors |
| **Code Chunking** | LangChain Text Splitters | AST-aware splitting for 18+ languages |
| **LLM Orchestration** | LangGraph | Deterministic state machine, composable nodes |
| **LLM Gateway** | OpenRouter | Free-tier models, automated fallback |
| **Git Operations** | GitPython | Shallow clone, no auth for public repos |
| **HTTP Client** | HTTPX | Async-ready, timeout control |
| **Package Manager** | uv (backend), pnpm (frontend) | Fast installs, lockfile determinism |

---

## Architectural Decision Records

### ADR-1: SQLite + Turso as the Single Data Store

**Context:** The system needs to store repositories, files, code chunks, and vector embeddings.

**Decision:** Use SQLite for local development and Turso (managed libSQL) for production. Store embeddings as JSON text strings in a `TEXT` column, not in a dedicated vector database.

**Rationale:**
- Zero-config setup for local development — just a file on disk.
- Turso provides a hosted SQLite-compatible database with HTTP access for deployment.
- The chunk count per repository is capped at 450. At this scale, brute-force cosine similarity over JSON-parsed vectors is fast enough (under 100ms).
- A dedicated vector database (Pinecone, Weaviate, Qdrant) adds infrastructure complexity that is not justified at this scale.

**Trade-off:** No approximate nearest neighbor (ANN) indexing. If chunk counts grow beyond 10,000 per repo, a vector index or pgvector migration would be needed.

---

### ADR-2: AST-Aware Chunking with LangChain Text Splitters

**Context:** Naive text splitting breaks code at arbitrary points, splitting functions and classes in half. This produces chunks that are hard to understand in isolation.

**Decision:** Use `RecursiveCharacterTextSplitter.from_language()` from LangChain, which uses language-specific AST separators for 18+ languages.

**Configuration:**
- `chunk_size=900` characters (fits in a single embedding context window)
- `chunk_overlap=120` characters (preserves context at chunk boundaries)

**Rationale:**
- Splits at function/class/method boundaries first, then falls back to line/paragraph boundaries.
- Produces chunks that are self-contained and meaningful.
- Markdown and config files use a custom separator list: `\n## `, `\n### `, `\n\n`, `\n`.

---

### ADR-3: OpenRouter with Multi-Model Fallback

**Context:** The system needs an LLM for answer synthesis. It must work for free (no credit card) and handle rate limits and model outages.

**Decision:** Use OpenRouter as the LLM gateway with a fallback chain of free-tier models.

**Fallback order:**
1. User-configured model (env `OPENROUTER_MODEL`)
2. `nvidia/nemotron-3-ultra-550b-a55b:free`
3. `baidu/ernie-5.5-flash-preview:free`
4. `particle-ai/particle-1:free`

**Rationale:**
- OpenRouter provides a single API endpoint for 100+ models with unified pricing.
- Free-tier models have rate limits but zero cost. Good enough for a portfolio project.
- The fallback chain makes the system resilient. If one model is down or rate-limited, it tries the next.
- The system works with any OpenRouter-compatible model — the user can upgrade to paid models by changing one env variable.

---

### ADR-4: LangGraph Read-Only State Machine

**Context:** The RAG pipeline has 3 sequential stages: retrieve, synthesize, verify. These must run in order, and the state must flow between them.

**Decision:** Implement the pipeline as a LangGraph `StateGraph` with 3 deterministic nodes and linear edges (`START → retrieve → synthesize → verify → END`).

**Rationale:**
- LangGraph enforces a typed state contract (`RepoAskState`) between nodes.
- Each node is a pure function that reads from state and returns updates.
- The linear graph is easy to debug — log the state after each node.
- Future extension: add conditional edges for multi-hop retrieval or agent loops without rewriting existing nodes.

**State shape:**
```python
class RepoAskState(TypedDict, total=False):
    repo_id: str
    question: str
    retrieved_chunks: List[Dict]
    context_text: str
    repo_name: str
    raw_answer: str
    clean_answer: str
    citations: List[Dict]
    verified_files_count: int
    status_updates: List[Dict]
```

---

### ADR-5: Citation Verification Gate

**Context:** LLMs hallucinate file paths and line numbers. If the user clicks a source link that does not exist, trust is broken.

**Decision:** Implement a hard verification gate in `verify_node` that checks every citation in the answer against the `files` table in the database. Invalid citations are silently removed. If no citations survive, the system falls back to attaching the top retrieved chunk.

**Verification steps:**
1. Parse citation patterns from the answer text using regex.
2. For each citation, check if the file path exists in the `files` table.
3. Clamp line ranges to the actual file length.
4. Consolidate overlapping or adjacent ranges for the same file.
5. Cap at 5 unique citations per answer.

**Rationale:** Every citation the user sees is guaranteed to point to a real file with valid line numbers. No dead links. No phantom files.

---

### ADR-6: In-Process Embeddings with FastEmbed

**Context:** The system needs to generate vector embeddings for code chunks and query strings.

**Decision:** Use FastEmbed with the `BAAI/bge-small-en-v1.5` model, running in-process on the CPU.

**Rationale:**
- No external embedding API calls — reduces latency and eliminates API costs.
- The model is 33MB and produces 384-dimensional vectors. Good quality-to-size ratio.
- Batch embedding (batch_size=64) processes 450 chunks in under 10 seconds on a laptop CPU.
- No GPU required.

**Trade-off:** Larger models (e.g., `bge-large-en-v1.5`, OpenAI `text-embedding-3-small`) would produce better embeddings at the cost of slower inference or API fees.

---

### ADR-7: ASD-STE100 Writing Constraints

**Context:** LLM answers tend to be verbose, inconsistent, and use jargon. The user wants clear, scannable documents.

**Decision:** Constrain the LLM output with ASD-STE100 (Simplified Technical English) rules in the system prompt.

**Key constraints:**
- Maximum 20 words per instruction sentence, 25 per description sentence.
- One idea per sentence. One topic per paragraph.
- Active voice only. Simple tenses only.
- No contractions, idioms, or figurative language.
- Technical names allowed exactly as they appear in the code.
- 80% text, 20% visuals maximum.

**Rationale:** Consistent, readable answers regardless of which LLM model is used. The constraints act as a style guide that the model follows.

