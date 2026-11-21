# Upgrade 01 — AI Pipeline Overhaul with LangChain & LangGraph (OpenRouter Edition)

> Transform RepoAsk from a linear 3-function pipeline into a production-grade RAG system using OpenRouter exclusively for all LLM inference: conversation memory, hybrid search, multi-hop retrieval, true OpenRouter token streaming, and structured output.

---

## Current State vs Target State

```
CURRENT (v0.2)                           TARGET (v1.0)
─────────────────                         ─────────────────
Raw httpx calls to OpenRouter      →      ChatOpenAI with streaming + fallback
Manual FastEmbed calls             →      LangChain Embeddings interface
Hand-rolled cosine similarity      →      VectorStore with hybrid search
Brute-force JSON embeddings        →      ChromaDB / FAISS with ANN index
Regex citation parsing             →      Structured LLM output (Pydantic)
No conversation memory             →      LangGraph MemorySaver checkpointing
Linear graph (A → B → C)          →      Conditional graph with loops
Fake word-by-word streaming        →      True LLM token streaming
No observability                   →      LangChain callbacks + tracing
os.walk file discovery             →      LangChain GitLoader
```

---

## Phase 1: LLM Gateway (Replace raw HTTP with ChatOpenAI)

### What Changes

Replace the hand-rolled `_call_llm_gateway()` function in `graph.py` (50+ lines of httpx code, manual retry loop, JSON parsing) with LangChain's `ChatOpenAI`.

### Current Code (graph.py)

```python
# 50 lines of manual HTTP, retry logic, JSON parsing
def _call_llm_gateway(messages, temperature=0.2, max_tokens=1500):
    for model_name in models_to_try:
        with httpx.Client(timeout=12.0) as client:
            res = client.post("https://openrouter.ai/api/v1/chat/completions", ...)
            # manual status check, JSON parse, error handling
```

### New Code

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    model=os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free"),
    temperature=0.2,
    max_tokens=1600,
    streaming=True,
    request_timeout=15,
    default_headers={
        "HTTP-Referer": "http://localhost:5173",
        "X-Title": "RepoAsk",
    },
)
```

### Why ChatOpenAI for OpenRouter

| Reason | Detail |
|---|---|
| **Direct OpenRouter Compatibility** | OpenRouter provides an OpenAI-compatible API (`/api/v1/chat/completions`). `ChatOpenAI` connects seamlessly with custom `base_url` and `default_headers` |
| **Streaming Built-in** | True token streaming through OpenRouter's SSE streams with `streaming=True` |
| **Automatic Retries & Exponential Backoff** | Handles transient OpenRouter rate limits (HTTP 429) and upstream provider 5xx outages automatically |
| **Token Usage Tracking** | Direct access to OpenRouter `usage` stats via `response.usage_metadata` (prompt tokens, completion tokens) |
| **Single Key, 100+ Models** | No provider lock-in. Switch between open-weight models (Qwen, Llama, Nemotron, Mistral) on OpenRouter without changing code |

### Alternative Methods Considered (OpenRouter Gateway)

| Method | Pros | Cons | Verdict |
|---|---|---|---|
| **ChatOpenAI pointing to OpenRouter (LangChain)** | Native streaming, automatic retries, callbacks, token metadata, works with any OpenRouter model | Minor overhead of langchain-openai wrapper | ✅ **Selected** |
| **Raw httpx to OpenRouter (current)** | No extra dependency, manual control | 50 lines of boilerplate, fake word-splitting streaming, manual retry loops | ❌ Current pain |
| **Direct Provider SDKs (OpenAI, Anthropic, Gemini)** | Direct provider features | Requires managing multiple API keys and billing accounts; breaks our OpenRouter-only rule | ❌ Discarded (OpenRouter only) |
| **LiteLLM Proxy** | Multi-provider fallback proxy | Extra proxy server/layer needed; unnecessary since OpenRouter already routes all models under one endpoint | ❌ Unnecessary complexity |

### Fallback Strategy (OpenRouter-Only Fallback Chain)

OpenRouter hosts hundreds of models. When one model is congested or rate-limited on the free tier, LangChain's `.with_fallbacks()` automatically tries alternative OpenRouter models:

```python
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel

def get_openrouter_llm_with_fallback() -> BaseChatModel:
    headers = {
        "HTTP-Referer": "http://localhost:5173",
        "X-Title": "RepoAsk",
    }
    
    # Primary model configured by user
    primary = ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        model=os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free"),
        temperature=0.2,
        max_tokens=1600,
        streaming=True,
        request_timeout=15,
        default_headers=headers,
    )
    
    # Free-tier fallback models on OpenRouter
    fallback_1 = ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        model="baidu/ernie-5.5-flash-preview:free",
        temperature=0.2,
        max_tokens=1600,
        streaming=True,
        request_timeout=15,
        default_headers=headers,
    )
    
    fallback_2 = ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        model="particle-ai/particle-1:free",
        temperature=0.2,
        max_tokens=1600,
        streaming=True,
        request_timeout=15,
        default_headers=headers,
    )
    
    # LangChain executes fallbacks sequentially if primary raises an exception or 429
    return primary.with_fallbacks([fallback_1, fallback_2])
```

### Estimated Effort: 1–2 hours

---

## Phase 2: Embeddings Interface (Swappable Embedding Models)

### What Changes

Replace direct FastEmbed calls in `ingest.py` and `ask.py` with LangChain's embeddings interface. Both files currently have duplicate `get_embedding_model()` functions.

### Current Code (duplicated in ingest.py AND ask.py)

```python
from fastembed import TextEmbedding

_embedding_model = None
def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    return _embedding_model
```

### New Code (single file: embeddings.py)

```python
from langchain_community.embeddings import FastEmbedEmbeddings

embeddings = FastEmbedEmbeddings(
    model_name="BAAI/bge-small-en-v1.5",
    batch_size=64,
)

# Usage — identical interface regardless of provider:
vectors = embeddings.embed_documents(["chunk 1 text", "chunk 2 text"])
query_vector = embeddings.embed_query("how does routing work?")
```

### Why LangChain Embeddings Interface

| Reason | Detail |
|---|---|
| **Single source of truth** | One `embeddings.py` instead of duplicate globals in 2 files |
| **Swappable** | Change to OpenAI, Cohere, HuggingFace, or Ollama by changing one class |
| **VectorStore compatible** | Required for Phase 3 — VectorStores expect a LangChain `Embeddings` object |
| **Async support** | `aembed_documents()` for non-blocking embedding during indexing |

### Alternative Methods Considered

| Method | Pros | Cons | Verdict |
|---|---|---|---|
| **FastEmbedEmbeddings (LangChain)** | Wraps FastEmbed in LangChain interface, in-process, free | Slightly slower than raw FastEmbed due to wrapper | ✅ **Selected** |
| **OpenAIEmbeddings** | Higher quality (text-embedding-3-small), 1536 dims | Costs money, API latency | ❌ Not default |
| **HuggingFaceEmbeddings** | Many model choices, local | Needs torch, heavy install | ❌ Too heavy |
| **OllamaEmbeddings** | Local, private, free | Needs Ollama server running | ❌ Extra dependency |
| **Raw FastEmbed (current)** | Fast, no wrapper overhead | Not swappable, duplicated code, no VectorStore compat | ❌ Current pain |

### Estimated Effort: 30 minutes

---

## Phase 3: Vector Store (Replace Brute-Force Search)

### What Changes

Replace the manual "load all embeddings → compute cosine similarity → sort" logic in `ask.py` with a proper vector store.

### Current Code (ask.py — 35 lines of manual search)

```python
def search_code(repo_id, query, top_k=10):
    query_vector = list(get_embedding_model().embed([query]))[0].tolist()
    result = client.execute("SELECT ... embedding FROM chunks WHERE repo_id = ?", [repo_id])
    for row in result.rows:
        chunk_vec = json.loads(emb_str)        # Parse JSON string to list
        score = cosine_similarity(query_vector, chunk_vec)  # Manual numpy dot product
    scored_chunks.sort(key=lambda x: x["score"], reverse=True)
    return scored_chunks[:top_k]
```

### New Code

```python
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

# At indexing time:
docs = [
    Document(
        page_content=chunk_text,
        metadata={"repo_id": repo_id, "path": path, "start_line": start, "end_line": end}
    )
    for chunk_text, path, start, end in chunks
]
vectorstore = Chroma.from_documents(docs, embeddings, collection_name=f"repo_{repo_id}")

# At query time:
retriever = vectorstore.as_retriever(
    search_type="mmr",                # Maximal Marginal Relevance — diversity + relevance
    search_kwargs={"k": 10, "filter": {"repo_id": repo_id}}
)
results = retriever.invoke(question)
```

### Why a Vector Store

| Reason | Detail |
|---|---|
| **ANN indexing** | Approximate nearest neighbor search is O(log n) instead of O(n). Matters when scaling beyond 450 chunks |
| **MMR search** | Maximal Marginal Relevance balances relevance AND diversity — prevents 10 chunks from the same function |
| **Metadata filtering** | Filter by `repo_id` at the index level, not in Python after loading everything |
| **Persistence** | Chroma saves to disk. No need to re-embed on restart |
| **LangChain Retriever** | Returns a `Retriever` object that plugs directly into chains and graphs |

### Alternative Methods Considered

| Method | Pros | Cons | Verdict |
|---|---|---|---|
| **Chroma** | Easy setup, persistent, metadata filtering, MMR built in | Adds dependency, separate storage from SQLite | ✅ **Selected** |
| **FAISS** | Fastest ANN search, in-memory | No metadata filtering, no persistence by default, C++ dependency | ❌ For speed-critical |
| **SQLiteVSS** | Stays in SQLite, no new database | Experimental, limited features | ❌ Not mature |
| **pgvector** | Production-grade, SQL-native vector search | Needs PostgreSQL server | ❌ Overkill for now |
| **Qdrant** | Rich filtering, cloud option | External service | ❌ Infrastructure |
| **Brute-force JSON (current)** | Zero dependencies, simple | O(n), no MMR, parses JSON every query, 450-chunk ceiling | ❌ Current pain |

### Hybrid Search (Phase 3b)

Combine vector search with keyword search for the best of both worlds:

```python
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever

# BM25 for exact keyword matches (function names, file names)
bm25 = BM25Retriever.from_documents(docs, k=5)

# Vector for semantic similarity
vector = vectorstore.as_retriever(search_kwargs={"k": 5})

# 60% vector, 40% keyword
hybrid = EnsembleRetriever(
    retrievers=[vector, bm25],
    weights=[0.6, 0.4]
)
```

**Why hybrid:** A user asking "where is the `ingest_repository` function?" needs keyword matching. A user asking "how does the system process new repositories?" needs semantic matching. Hybrid handles both.

### Estimated Effort: 3–4 hours

---

## Phase 4: Structured Output (Replace Regex Citation Parsing)

### What Changes

Replace the 90-line regex citation parser in `ask.py` (`verify_citations`) with structured LLM output using Pydantic models.

### Current Code (ask.py — fragile regex)

```python
citation_pattern = re.compile(
    r'(?:\[\s*`?([a-zA-Z0-9_\-\./]+)`?\s*:\s*(?:L|l)?(\d+)(?:\s*[\-–‑]\s*(?:L|l)?(\d+))?\s*\]|'
    r'(?:`|\b)([a-zA-Z0-9_\-\./]+(?:/[a-zA-Z0-9_\-\.]+)+)(?:`|\b)\s*(?:lines?|L|l)?\s*(\d+)\s*(?:[\-–‑]\s*(?:L|l)?(\d+))?)'
)
```

This regex breaks when the LLM formats citations differently.

### New Code

```python
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

class Citation(BaseModel):
    path: str = Field(description="File path relative to repo root")
    start_line: int = Field(description="First line number")
    end_line: int = Field(description="Last line number")

class RepoAnswer(BaseModel):
    title: str = Field(description="Answer title, max 8 words")
    short_answer: str = Field(description="1-2 sentence summary")
    sections: list[str] = Field(description="Markdown body sections")
    citations: list[Citation] = Field(description="Source file references")

parser = PydanticOutputParser(pydantic_object=RepoAnswer)

# Add format instructions to the system prompt:
system_prompt += f"\n\n{parser.get_format_instructions()}"

# Parse the response:
structured = parser.parse(llm_response.content)
# structured.citations is now a typed list — no regex needed
```

### Why Structured Output

| Reason | Detail |
|---|---|
| **No regex** | The LLM returns JSON that Pydantic validates. No fragile pattern matching |
| **Type safety** | `Citation.path` is always a string. `Citation.start_line` is always an int. No casting, no None checks |
| **Validation** | Pydantic rejects malformed output automatically. The system can retry with a correction prompt |
| **Separation** | Citations are in a structured field, not embedded in prose. No risk of corrupting Mermaid blocks |
| **Testable** | Unit test the Pydantic model, not a 90-line regex |

### Alternative Methods Considered

| Method | Pros | Cons | Verdict |
|---|---|---|---|
| **PydanticOutputParser** | Type-safe, validates, retries | LLM must follow format instructions | ✅ **Selected** |
| **JsonOutputParser** | Simpler, less strict | No type validation | ❌ Weaker |
| **Tool/function calling** | Model returns structured JSON natively | Not all free models support it | ❌ Model-dependent |
| **OutputFixingParser** | Auto-fixes malformed LLM output with a second LLM call | Extra LLM call, cost | 🟡 Use as fallback |
| **Regex (current)** | No LLM format dependency | Fragile, 90 lines, breaks on new formats | ❌ Current pain |

### Recommended Combo

```python
from langchain.output_parsers import OutputFixingParser

# Primary: Pydantic parser
# Fallback: If parsing fails, ask the LLM to fix its own output
robust_parser = OutputFixingParser.from_llm(parser=parser, llm=llm)
```

### Estimated Effort: 2–3 hours

---

## Phase 5: LangGraph Conversation Memory

### What Changes

Add `MemorySaver` checkpointing so follow-up questions see previous context.

### Current Behavior

Each question is independent. Asking "how does routing work?" then "what about error handling in that?" fails — the system does not know what "that" refers to.

### New Code

```python
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()

def build_repoask_graph():
    workflow = StateGraph(RepoAskState)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("synthesize", synthesize_node)
    workflow.add_node("verify", verify_node)
    workflow.add_edge(START, "retrieve")
    workflow.add_edge("retrieve", "synthesize")
    workflow.add_edge("synthesize", "verify")
    workflow.add_edge("verify", END)
    return workflow.compile(checkpointer=checkpointer)  # ← Add this

# Invoke with thread ID for memory:
def run_repoask_graph(repo_id, question, conversation_id=None):
    config = {"configurable": {"thread_id": conversation_id or repo_id}}
    final_state = repoask_graph.invoke(initial_state, config=config)
    return final_state
```

### Why MemorySaver

| Reason | Detail |
|---|---|
| **Follow-up questions** | "What about error handling in that?" works because the graph remembers "that" = routing |
| **Zero storage setup** | `MemorySaver` is in-memory. No database needed. For persistence, swap to `SqliteSaver` |
| **Thread isolation** | Each `thread_id` has its own memory. Different conversations do not leak into each other |
| **State replay** | Inspect any previous state: `graph.get_state(config)` returns the full state at any checkpoint |

### Alternative Methods Considered

| Method | Pros | Cons | Verdict |
|---|---|---|---|
| **MemorySaver (in-memory)** | Zero config, fast, thread-safe | Lost on server restart | ✅ **Selected for dev** |
| **SqliteSaver** | Persistent, uses existing SQLite | Slightly more setup | ✅ **Selected for prod** |
| **PostgresSaver** | Production-grade, concurrent | Needs PostgreSQL | ❌ Overkill |
| **Manual context in prompt** | Append previous Q&A to the prompt | No state management, prompt grows unbounded | ❌ Fragile |
| **No memory (current)** | Simple, stateless | "What about that?" fails | ❌ Current pain |

### Estimated Effort: 30 minutes

---

## Phase 6: Conditional Graph with Multi-Hop Retrieval

### What Changes

Replace the linear `retrieve → synthesize → verify` with a graph that makes decisions.

### New Graph Architecture

```
START
  │
  ▼
retrieve_node
  │
  ▼
evaluate_context ──── enough context? ──── Yes ──→ synthesize_node
  │                                                      │
  No                                                     ▼
  │                                                verify_node
  ▼                                                      │
follow_imports_node ─────────────────────────────→       │
  │                                                      ▼
  └──── (max 2 hops) ────→ synthesize_node        citations_valid?
                                                     │         │
                                                    No        Yes
                                                     │         │
                                                     ▼         ▼
                                              re_synthesize   END
                                                     │
                                                     └──→ verify_node ──→ END
```

### New Code

```python
def evaluate_context(state: RepoAskState) -> str:
    """Decides if retrieved context is sufficient."""
    chunks = state.get("retrieved_chunks", [])
    if not chunks:
        return "insufficient"
    
    top_score = chunks[0].get("score", 0)
    unique_files = len(set(c["path"] for c in chunks))
    
    # Not enough context if top score is low or only 1 file found
    if top_score < 0.35 or unique_files < 2:
        hops = state.get("retrieval_hops", 0)
        if hops < 2:  # Max 2 additional retrieval passes
            return "insufficient"
    
    return "sufficient"


def follow_imports_node(state: RepoAskState) -> dict:
    """Follows import/require statements in top chunks to find related files."""
    chunks = state.get("retrieved_chunks", [])
    hops = state.get("retrieval_hops", 0)
    
    # Extract imported file paths from chunk content
    import_patterns = [
        r'from\s+([\w.]+)\s+import',           # Python
        r'import\s+([\w.]+)',                    # Python/Java
        r"require\(['\"](.+?)['\"]\)",           # JS/Node
        r"from\s+['\"](.+?)['\"]",              # JS/TS ES6
    ]
    
    imported_paths = set()
    for chunk in chunks[:5]:
        for pattern in import_patterns:
            matches = re.findall(pattern, chunk["content"])
            imported_paths.update(matches)
    
    # Search for chunks from imported files
    additional_chunks = search_by_paths(state["repo_id"], imported_paths)
    
    combined = chunks + additional_chunks
    # Deduplicate by chunk ID
    seen = set()
    unique = []
    for c in combined:
        if c["id"] not in seen:
            seen.add(c["id"])
            unique.append(c)
    
    return {
        "retrieved_chunks": unique[:15],
        "retrieval_hops": hops + 1,
    }


# Build the graph with conditional edges:
workflow = StateGraph(RepoAskState)

workflow.add_node("retrieve", retrieve_node)
workflow.add_node("evaluate", evaluate_context)
workflow.add_node("follow_imports", follow_imports_node)
workflow.add_node("synthesize", synthesize_node)
workflow.add_node("verify", verify_node)

workflow.add_edge(START, "retrieve")
workflow.add_edge("retrieve", "evaluate")

workflow.add_conditional_edges("evaluate", evaluate_context, {
    "sufficient": "synthesize",
    "insufficient": "follow_imports",
})
workflow.add_edge("follow_imports", "evaluate")  # Loop back to check again

workflow.add_edge("synthesize", "verify")
workflow.add_edge("verify", END)
```

### Why Conditional Edges + Loops

| Reason | Detail |
|---|---|
| **Deeper understanding** | If the first retrieval only finds README chunks, a second pass follows imports to find actual implementation files |
| **Self-correcting** | The graph evaluates its own context quality before calling the expensive LLM |
| **Bounded loops** | `retrieval_hops < 2` prevents infinite loops. Maximum 3 total retrieval passes |
| **Better answers** | More context = more accurate synthesis. Especially for "how does X work?" questions that span multiple files |

### Alternative Methods Considered

| Method | Pros | Cons | Verdict |
|---|---|---|---|
| **Conditional edges in LangGraph** | Native, typed, debuggable, bounded | More complex graph | ✅ **Selected** |
| **LangChain MultiQueryRetriever** | Generates multiple query variants | Only varies the query, not the retrieval depth | ❌ Shallow |
| **Agentic retrieval (ReAct)** | LLM decides what to retrieve next | Unpredictable, expensive (multiple LLM calls) | ❌ Too expensive on free tier |
| **Fixed multi-query** | Run 3 hardcoded queries per question | Wasteful, not adaptive | ❌ Rigid |
| **Single retrieval (current)** | Simple, fast, predictable | Misses cross-file connections | ❌ Current pain |

### Estimated Effort: 4–5 hours

---

## Phase 7: True SSE Streaming

### What Changes

Replace the fake streaming (split finished answer into words) with true token-by-token streaming from the LLM through LangGraph to the client.

### Current Code (main.py — fake streaming)

```python
# The ENTIRE answer is generated first, then split into words
answer_text = result.get("answer", "")
words = answer_text.split(" ")
for i, word in enumerate(words):
    yield sse("token", {"text": word + " "})
    if i % 4 == 0:
        await asyncio.sleep(0.015)  # Fake delay
```

### New Code

```python
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

async def stream_answer(repo_id, question):
    llm = ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        model=os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free"),
        streaming=True,
        default_headers={
            "HTTP-Referer": "http://localhost:5173",
            "X-Title": "RepoAsk",
        },
    )
    
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    
    async for chunk in llm.astream(messages):
        token = chunk.content
        if token:
            yield sse("token", {"text": token})

# In the FastAPI endpoint:
async def generate():
    # ... status events ...
    async for event in stream_answer(repo_id, question):
        yield event
    # ... citation events after streaming completes ...
```

### Why True Streaming

| Reason | Detail |
|---|---|
| **Time to first token** | User sees the first word in ~500ms instead of waiting 8–15 seconds for the full answer |
| **Perceived speed** | The answer feels instant even though total generation time is the same |
| **Cancelability** | The user can stop generation mid-stream. Currently, the full answer generates before any tokens appear |
| **Memory efficient** | No need to hold the entire answer in memory before streaming |

### Alternative Methods Considered

| Method | Pros | Cons | Verdict |
|---|---|---|---|
| **ChatOpenAI.astream()** | Native async streaming, clean API | Need to verify citations after stream ends | ✅ **Selected** |
| **LangGraph .astream_events()** | Streams events from any node in the graph | More complex, event filtering needed | 🟡 Phase 2 upgrade |
| **OpenRouter streaming via httpx** | No LangChain dependency | Manual chunk parsing, no retry | ❌ Reinventing the wheel |
| **Word splitting (current)** | Simple, no streaming setup | Fake, 8-15 second delay before first word | ❌ Current pain |

### Trade-off: Verification After Streaming

With true streaming, the answer is sent to the client before verification. Options:

1. **Verify after stream** — Stream the raw answer, then send a `corrections` event with removed citations. The frontend patches the displayed text.
2. **Two-pass display** — Stream the answer into a "draft" view, then replace with the verified version.
3. **Pre-verified sources** — Send source files from the retrieval step as early citations, refine after verification.

**Recommended:** Option 1. The user sees the answer immediately. Invalid citations are cleaned up 1–2 seconds later.

### Estimated Effort: 3–4 hours

---

## Phase 8: Observability (LangChain Callbacks)

### What Changes

Add logging and tracing to every step in the pipeline without modifying pipeline code.

### New Code

```python
from langchain_core.callbacks import BaseCallbackHandler
import time

class RepoAskTracer(BaseCallbackHandler):
    def on_llm_start(self, serialized, prompts, **kwargs):
        self.start_time = time.time()
        print(f"[LLM] Starting {serialized.get('name', 'unknown')}")
    
    def on_llm_end(self, response, **kwargs):
        elapsed = time.time() - self.start_time
        tokens = response.llm_output.get("token_usage", {})
        print(f"[LLM] Done in {elapsed:.1f}s | {tokens}")
    
    def on_retriever_start(self, query, **kwargs):
        print(f"[Retriever] Query: {query[:80]}...")
    
    def on_retriever_end(self, documents, **kwargs):
        print(f"[Retriever] Found {len(documents)} chunks")

# Attach globally:
llm = ChatOpenAI(callbacks=[RepoAskTracer()], ...)
```

### Why Callbacks

| Reason | Detail |
|---|---|
| **Zero pipeline changes** | Attach a callback handler and every LLM call, retrieval, and chain step is logged |
| **Cost tracking** | Token counts from every LLM call. Know exactly how much each question costs |
| **Latency profiling** | Time each step to find bottlenecks |
| **LangSmith integration** | Set `LANGCHAIN_TRACING_V2=true` and all traces go to LangSmith for visual debugging |

### Alternative Methods Considered

| Method | Pros | Cons | Verdict |
|---|---|---|---|
| **LangChain Callbacks** | Built in, zero pipeline changes | LangChain-specific | ✅ **Selected** |
| **LangSmith** | Full tracing UI, replay, evaluation | Requires account, sends data externally | 🟡 Optional add-on |
| **OpenTelemetry** | Industry standard, vendor-neutral | More setup, manual instrumentation | ❌ Heavier |
| **Print statements (current)** | Simple | No structure, no metrics, clutters logs | ❌ Current state |

### Estimated Effort: 1 hour

---

## Phase 9: Document Loaders (Replace os.walk)

### What Changes

Replace the manual file tree walk in `ingest.py` (40+ lines of `os.walk`, extension filtering, directory skipping) with LangChain's `GitLoader`.

### Current Code (ingest.py)

```python
for root, dirs, files in os.walk(clone_path):
    dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
    for file_name in files:
        ext = file_path.suffix.lower()
        if ext in IGNORE_EXTENSIONS:
            continue
        # ... 30 more lines of filtering
```

### New Code

```python
from langchain_community.document_loaders import GitLoader

loader = GitLoader(
    clone_url=clean_url,
    repo_path=str(clone_path),
    branch="main",
    file_filter=lambda path: (
        not any(d in path for d in IGNORE_DIRS) and
        not any(path.endswith(ext) for ext in IGNORE_EXTENSIONS) and
        os.path.getsize(path) <= 500_000
    ),
)

documents = loader.load()
# Each document has: page_content, metadata={source, file_path, file_name}
```

### Why GitLoader

| Reason | Detail |
|---|---|
| **Less code** | 5 lines instead of 40+ |
| **Branch support** | Pass `branch="develop"` to index a specific branch |
| **Metadata** | Each document comes with structured metadata (path, name, type) |
| **LangChain Document format** | Returns `Document` objects that feed directly into text splitters and vector stores |

### Alternative Methods Considered

| Method | Pros | Cons | Verdict |
|---|---|---|---|
| **GitLoader** | Clones + loads in one step, branch support, metadata | Slightly less control over clone options | ✅ **Selected** |
| **DirectoryLoader** | Works with any local directory | Need to clone separately | 🟡 If clone is already done |
| **GithubFileLoader** | Uses GitHub API, no clone needed | Rate limited, no full repo support | ❌ Not suitable |
| **os.walk (current)** | Full control, no dependency | 40+ lines, no metadata, no branch support | ❌ Current pain |

### Estimated Effort: 1–2 hours

---

## Implementation Order

| Phase | Feature | Effort | Impact | Priority |
|---|---|---|---|---|
| **1** | ChatOpenAI + fallbacks | 1–2 hours | High — streaming, retries, token counting | 🔴 Do first |
| **5** | Conversation memory | 30 min | High — follow-up questions work | 🔴 Do first |
| **2** | Embeddings interface | 30 min | Medium — enables Phase 3 | 🟡 Do second |
| **3** | Vector store + hybrid search | 3–4 hours | High — better retrieval, MMR diversity | 🟡 Do second |
| **4** | Structured output | 2–3 hours | Medium — eliminates regex, cleaner code | 🟡 Do second |
| **7** | True SSE streaming | 3–4 hours | High — time to first token drops from 15s to 0.5s | 🟠 Do third |
| **6** | Conditional graph + multi-hop | 4–5 hours | High — cross-file understanding | 🟠 Do third |
| **8** | Observability | 1 hour | Medium — debugging, cost tracking | 🔵 Do fourth |
| **9** | Document loaders | 1–2 hours | Low — cleaner code, branch support | 🔵 Do fourth |

### Total Estimated Effort: 17–23 hours

---

## Dependency Changes

### New pip packages

```toml
# Add to pyproject.toml [project.dependencies]
"langchain>=0.3.0",
"langchain-openai>=0.3.0",
"langchain-community>=0.3.0",
"chromadb>=0.5.0",           # Phase 3 only
"rank-bm25>=0.2.0",          # Phase 3b only (hybrid search)
```

### Packages that become optional

```toml
# These are still used internally by LangChain wrappers, but you stop importing them directly:
# "httpx" — replaced by ChatOpenAI internals
# "fastembed" — wrapped by FastEmbedEmbeddings
# "numpy" — replaced by VectorStore internals
```

---

## Files Changed Per Phase

| Phase | Files Modified | Files Created |
|---|---|---|
| 1 | `graph.py` | — |
| 2 | `ingest.py`, `ask.py` | `app/embeddings.py` |
| 3 | `ingest.py`, `ask.py`, `db.py` | — |
| 4 | `graph.py`, `ask.py` | `app/schemas.py` |
| 5 | `graph.py`, `main.py` | — |
| 6 | `graph.py` | — |
| 7 | `graph.py`, `main.py` | — |
| 8 | `graph.py` | `app/tracing.py` |
| 9 | `ingest.py` | — |

