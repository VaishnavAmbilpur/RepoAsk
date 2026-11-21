# AI Model Pipeline

## Overview

RepoAsk uses a **Retrieval-Augmented Generation (RAG)** pipeline built on LangGraph. The pipeline has 3 stages, each implemented as a node in a deterministic state machine.

```
START → retrieve_node → synthesize_node → verify_node → END
```

No loops. No conditional branches. Every question runs through all 3 nodes in order.

---

## Stage 1: Retrieve (`retrieve_node`)

**Purpose:** Find the most relevant code chunks for the user's question.

### Embedding Model

| Property | Value |
|---|---|
| Model | BAAI/bge-small-en-v1.5 |
| Provider | FastEmbed (in-process, CPU) |
| Dimensions | 384 |
| Model size | ~33 MB |
| Batch size | 64 |

### Retrieval Algorithm

1. **Embed the query** — The user's question is converted to a 384-dim vector using the same embedding model used during indexing.
2. **Fetch all chunks** — All chunks for the given `repo_id` are loaded from the database.
3. **Compute similarity** — Cosine similarity is calculated between the query vector and each chunk vector.
4. **Apply scoring boosts and penalties:**

   | Condition | Score Adjustment |
   |---|---|
   | Chunk has fewer than 30 characters | −0.40 |
   | Root README (overview query) | +0.65 |
   | Root README, first 50 lines | +0.35 (additional) |
   | Nested README (overview query) | +0.40 |
   | Architecture/overview docs | +0.35 |
   | Any `.md` file (overview query) | +0.20 |
   | Manifest files (package.json, pyproject.toml) | +0.25 |

5. **Sort and return top 10** — Chunks are sorted by adjusted score, top 10 are returned.

### README Fallback

For overview-type questions (containing words like "what is", "about", "explain"), the system checks if the root README is in the top 10 results. If not, it queries the `files` table directly and injects the first 60 lines of the README at position 0 with a boosted score of 1.5.

### Context Assembly

Retrieved chunks are formatted into a context string:

```
--- File: app/main.py (Lines 1-45) ---
<chunk content>

--- File: app/graph.py (Lines 95-162) ---
<chunk content>
```

This context string is passed to the synthesis stage.

---

## Stage 2: Synthesize (`synthesize_node`)

**Purpose:** Generate a structured, plain-English answer using an LLM.

### LLM Configuration

| Property | Value |
|---|---|
| Gateway | OpenRouter (`https://openrouter.ai/api/v1/chat/completions`) |
| Default model | `nvidia/nemotron-3-ultra-550b-a55b:free` (configurable via env) |
| Temperature | 0.2 |
| Max tokens | 1,600 |
| Timeout | 12 seconds per model attempt |

### Fallback Strategy

The system tries up to 4 models in sequence. If a model returns an error, empty response, or times out, the next model is tried:

```
User-configured model
  ↓ (fail)
nvidia/nemotron-3-ultra-550b-a55b:free
  ↓ (fail)
baidu/ernie-5.5-flash-preview:free
  ↓ (fail)
particle-ai/particle-1:free
  ↓ (fail)
Return hardcoded fallback answer
```

### System Prompt Structure

The system prompt has 7 sections:

1. **Identity** — "You are RepoAsk. You answer questions about one GitHub repository."
2. **Ground Rules** — Use only retrieved context. Never show code blocks.
3. **Writing Style (ASD-STE100)** — 13 rules for Simplified Technical English.
4. **Balance: Text and Visuals** — 80% text, 20% visuals maximum.
5. **When to Use a Visual** — Flowchart for processes, sequence diagram for interactions, ER diagram for data, tables for comparisons.
6. **Diagram Rules** — Maximum 10 nodes, 4 words per label, no citations inside mermaid blocks.
7. **Output Format** — Title, short answer, sections, sources.

### Flowchart Detection

The system detects if the question is about a process or flow by checking for keywords:

```python
["how", "flow", "work", "works", "process", "route", "routing", "request",
 "start", "startup", "init", "handle", "handling", "error",
 "architecture", "connect", "step", "lifecycle", "call", "pipeline", "execution"]
```

If detected, an additional instruction is appended requiring a Mermaid flowchart in the answer.

### Hardcoded Fallback

If all LLM models fail, the system returns a basic answer using data from the first retrieved chunk:

```markdown
# Repository Overview
> **Short answer:** This repository contains code for {repo_name}.
## Structure
The core implementation starts in [{path}:{start}-{end}].
## Sources
- [{path}](https://github.com/{repo}/blob/main/{path}) - Primary source file
```

---

## Stage 3: Verify (`verify_node`)

**Purpose:** Guarantee that every citation in the answer points to a real file with valid line numbers.

### Citation Parsing

The system uses regex to find citation patterns in the answer text:

- `[path/to/file:start-end]`
- `` `path/to/file:start-end` ``
- `path/to/file lines start-end`
- Variations with `L` prefix for line numbers

**Important:** Citations inside ` ```mermaid ``` ` code blocks are skipped to avoid corrupting diagrams.

### Verification Steps

1. **Load valid files** — Query `files` table for all paths in this repository.
2. **Match each citation** — For each parsed citation:
   - Check if the path exists exactly in `valid_files`.
   - If not, try suffix matching (e.g., `main.py` matches `app/main.py`).
   - If matched, clamp `end_line` to `actual_file_length + 20`.
   - If not matched, remove the citation from the answer.
3. **Fallback: file name matching** — If no citations were extracted but the answer mentions file names from retrieved chunks, those are added as citations.
4. **Ultimate fallback** — If still no citations, the top retrieved chunk's file is attached.
5. **Consolidation** — Overlapping or adjacent ranges for the same file are merged (gap tolerance: 15 lines).
6. **Cap** — Maximum 5 unique citations per answer.

### Output

The verify node returns:
- `clean_answer` — The answer with invalid citations removed
- `citations` — A list of `{ path, start_line, end_line }` objects
- `verified_files_count` — Count of unique source files

---

## Embedding Pipeline (Indexing Time)

During repository indexing, embeddings are generated for all code chunks:

```
Raw file content
  ↓
Language-aware splitting (RecursiveCharacterTextSplitter)
  ↓
Chunk text strings (900 chars, 120 overlap)
  ↓
FastEmbed batch embedding (batch_size=64)
  ↓
384-dim float vectors
  ↓
Stored as JSON text in SQLite `chunks.embedding` column
```

### Chunk Budget

Each repository is capped at **450 chunks** to prevent timeout on large repos. When the limit is exceeded:

1. **Priority chunks** are always kept:
   - Root README files
   - Entry points (`main.py`, `app.py`, `index.js`, `server.js`, `package.json`, `go.mod`, `cargo.toml`)
2. **Standard chunks** are balanced across files using round-robin selection (minimum 2 chunks per file).

---

## Similarity Search (Query Time)

The search is brute-force: load all chunk embeddings for the repo, compute cosine similarity with the query vector, sort, and return top K.

```python
def cosine_similarity(v1, v2):
    a, b = np.array(v1), np.array(v2)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
```

**Why brute-force?** With a cap of 450 chunks per repo and 384 dimensions, the search completes in under 50ms. No index structure is needed.

