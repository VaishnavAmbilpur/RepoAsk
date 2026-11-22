import os
import re
import json
import numpy as np
from rank_bm25 import BM25Okapi
from app.embeddings import embed_query
from app.db import get_db
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")

FALLBACK_MODELS = [
    OPENROUTER_MODEL,
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "baidu/ernie-5.5-flash-preview:free",
    "particle-ai/particle-1:free",
]

def cosine_similarity(v1: list, v2: list) -> float:
    """Computes cosine similarity between two float vectors."""
    a = np.array(v1)
    b = np.array(v2)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))

def classify_query_intent(query: str) -> dict:
    """Classifies user query into Track A (local point-lookup) or Track B (global aggregation)."""
    q = query.lower()

    # Schemas, Models, Databases, Data entities
    is_schema = any(w in q for w in [
        "schema", "schemas", "model", "models", "entity", "entities",
        "table", "tables", "collection", "collections", "dto", "types", "interface"
    ])

    # Routes, Endpoints, APIs, Controllers
    is_route = any(w in q for w in [
        "route", "routes", "endpoint", "endpoints", "api", "apis",
        "controller", "controllers", "handler", "handlers", "urls"
    ])

    # Global / Aggregation keywords
    has_agg_word = any(w in q for w in [
        "all", "every", "list", "what are the", "show me all", "what schemas",
        "which schemas", "what models", "what routes", "overview", "catalog", "summary",
        "database structure", "data models"
    ])

    if is_schema and (has_agg_word or len(q.split()) <= 4):
        return {"track": "global", "category": "schema"}

    if is_route and (has_agg_word or len(q.split()) <= 4):
        return {"track": "global", "category": "route"}

    is_arch = any(w in q for w in [
        "architecture", "tech stack", "technologies", "structure", "components",
        "how is this built", "what libraries", "dependencies"
    ])
    if is_arch:
        return {"track": "global", "category": "architecture"}

    return {"track": "local", "category": "general"}


def search_global_catalog(repo_id: str, category: str, top_k: int = 14) -> list:
    """Track B: Collects key definition chunks from matching files across the repository."""
    client = get_db()

    if category == "schema":
        patterns = ["%model%", "%schema%", "%entit%", "%type%", "%dto%", "%table%"]
    elif category == "route":
        patterns = ["%route%", "%controller%", "%api%", "%endpoint%", "%handler%"]
    else:
        patterns = ["%readme%", "%package.json%", "%pyproject.toml%", "%go.mod%", "%cargo.toml%"]

    like_clauses = " OR ".join(["LOWER(path) LIKE ?" for _ in patterns])
    sql = f"SELECT id, path FROM files WHERE repo_id = ? AND ({like_clauses})"
    params = [repo_id] + patterns
    matched_files = client.execute(sql, params).rows

    matched_file_ids = {r[0]: r[1] for r in matched_files}
    chunks = []

    if matched_file_ids:
        placeholders = ",".join(["?" for _ in matched_file_ids])
        chunk_sql = f"""
            SELECT id, path, start_line, end_line, content
            FROM chunks
            WHERE repo_id = ? AND file_id IN ({placeholders})
            ORDER BY start_line ASC
        """
        chunk_rows = client.execute(chunk_sql, [repo_id] + list(matched_file_ids.keys())).rows

        file_chunk_count = {}
        for row in chunk_rows:
            cid, path, sl, el, content = row
            count = file_chunk_count.get(path, 0)
            if count < 2:  # Up to 2 chunks per matching file to ensure diverse catalog
                chunks.append({
                    "id": cid,
                    "path": path,
                    "start_line": int(sl),
                    "end_line": int(el),
                    "content": content,
                    "score": 1.2 - (0.05 * count)
                })
                file_chunk_count[path] = count + 1
                if len(chunks) >= top_k - 2:
                    break

    # Also grab root README for architectural context
    readme_row = client.execute(
        "SELECT path, content FROM files WHERE repo_id = ? AND LOWER(path) IN ('readme.md', 'readme.rst', 'readme.txt')",
        [repo_id]
    ).rows
    client.close()

    if readme_row and readme_row[0][1]:
        readme_lines = readme_row[0][1].splitlines()[:50]
        chunks.insert(0, {
            "id": "root-readme",
            "path": readme_row[0][0],
            "start_line": 1,
            "end_line": min(len(readme_lines), 50),
            "content": "\n".join(readme_lines),
            "score": 1.5
        })

    return chunks[:top_k]


def search_code(repo_id: str, query: str, top_k: int = 10) -> list:
    """Dual-Track search: routes to Global File-Tree aggregator or Local Hybrid search."""
    intent = classify_query_intent(query)
    
    # If Track B (Global Query), execute file-tree aggregator
    if intent["track"] == "global":
        catalog_chunks = search_global_catalog(repo_id, intent["category"], top_k=max(top_k, 12))
        if len(catalog_chunks) >= 3:
            return catalog_chunks

    # Otherwise execute Track A (Local Hybrid Search)
    client = get_db()
    
    # 1. Embed query
    query_vector = embed_query(query)
    
    # 2. Fetch chunks for this repo
    result = client.execute(
        "SELECT id, path, start_line, end_line, content, embedding FROM chunks WHERE repo_id = ?",
        [repo_id]
    )
    client.close()
    
    if not result.rows:
        return []

    # Prepare BM25 tokenized corpus
    tokenized_corpus = []
    chunk_rows = []
    for row in result.rows:
        chunk_id, path, start_line, end_line, content, emb_str = row
        tokens = re.findall(r'[a-zA-Z0-9_\-\./]+', f"{path} {content}".lower())
        tokenized_corpus.append(tokens)
        chunk_rows.append((chunk_id, path, start_line, end_line, content, json.loads(emb_str)))

    bm25 = BM25Okapi(tokenized_corpus)
    query_tokens = re.findall(r'[a-zA-Z0-9_\-\./]+', query.lower())
    bm25_scores = bm25.get_scores(query_tokens)
    max_bm25 = max(bm25_scores) if len(bm25_scores) > 0 and max(bm25_scores) > 0 else 1.0

    q_low = query.lower()
    is_overview_query = any(w in q_low for w in [
        "what is", "about", "project", "explain", "overview", "describe", 
        "purpose", "summary", "how it works", "architecture", "what does"
    ])

    scored_chunks = []
    for idx, (chunk_id, path, start_line, end_line, content, chunk_vec) in enumerate(chunk_rows):
        vec_score = cosine_similarity(query_vector, chunk_vec)
        norm_bm25 = bm25_scores[idx] / max_bm25

        # 60% semantic similarity + 40% BM25 keyword matching
        score = (0.60 * vec_score) + (0.40 * norm_bm25)
        
        # Penalize ultra-short chunks
        if len(content.strip()) < 30:
            score -= 0.40

        p_lower = path.lower()
        if is_overview_query:
            # Boost for root README
            if p_lower in ["readme.md", "readme.rst", "readme.txt"]:
                score += 0.65
                if start_line <= 50:
                    score += 0.35
            elif "readme" in p_lower:
                score += 0.40
            elif "context" in p_lower or "overview" in p_lower or "architecture" in p_lower:
                score += 0.35
            elif p_lower.endswith(".md"):
                score += 0.20
            elif any(p_lower.endswith(x) for x in ["package.json", "pyproject.toml", "cargo.toml", "go.mod"]):
                score += 0.25

        scored_chunks.append({
            "id": chunk_id,
            "path": path,
            "start_line": int(start_line),
            "end_line": int(end_line),
            "content": content,
            "score": float(score)
        })
        
    scored_chunks.sort(key=lambda x: x["score"], reverse=True)
    return scored_chunks[:top_k]

def verify_citations(repo_id: str, answer: str, fallback_chunks: list = None) -> tuple[str, list]:
    """Verifies that cited references exist in the database. Extracts citations and cleans answer."""
    client = get_db()
    file_rows = client.execute("SELECT path, total_lines FROM files WHERE repo_id = ?", [repo_id]).rows
    client.close()
    
    valid_files = {row[0]: row[1] for row in file_rows}
    
    # Matches patterns: [path:start-end], `path:start-end`, etc.
    citation_pattern = re.compile(
        r'(?:\[\s*`?([a-zA-Z0-9_\-\./]+)`?\s*:\s*(?:L|l)?(\d+)(?:\s*[\-–‑]\s*(?:L|l)?(\d+))?\s*\]|'
        r'(?:`|\b)([a-zA-Z0-9_\-\./]+(?:/[a-zA-Z0-9_\-\.]+)+)(?:`|\b)\s*(?:lines?|L|l)?\s*(\d+)\s*(?:[\-–‑]\s*(?:L|l)?(\d+))?)'
    )
    
    verified_citations = []
    
    def check_citation(match):
        raw_path = match.group(1) or match.group(4)
        if not raw_path:
            return match.group(0)
        path = raw_path.strip().replace("\\", "/")
        
        start_str = match.group(2) or match.group(5)
        end_str = match.group(3) or match.group(6) or start_str
        start = int(start_str) if start_str else 1
        end = int(end_str) if end_str else start
        
        # Check if file exists in valid_files or ends with path
        matched_real_path = None
        if path in valid_files:
            matched_real_path = path
        else:
            for vf in valid_files:
                if vf.endswith(path) or path.endswith(vf):
                    matched_real_path = vf
                    break

        if matched_real_path:
            tot = valid_files[matched_real_path]
            actual_end = min(max(start, end), tot + 20)
            cit = {"path": matched_real_path, "start_line": start, "end_line": actual_end}
            if cit not in verified_citations:
                verified_citations.append(cit)
            return f"[{matched_real_path}:{start}-{actual_end}]"
        else:
            return ""
            
    def replace_citations_outside_code(text: str) -> str:
        parts = re.split(r'(```[\s\S]*?```)', text)
        res = []
        for i, part in enumerate(parts):
            if i % 2 == 1:
                # Code blocks (including ```mermaid) remain completely intact
                res.append(part)
            else:
                subbed = citation_pattern.sub(check_citation, part)
                subbed = re.sub(r'([^\n])\n{1,2}\s*(\[[a-zA-Z0-9_\-\./]+:\d+(?:[\-–‑]\d+)?\])', r'\1 \2', subbed)
                res.append(subbed)
        return "".join(res)

    clean_answer = replace_citations_outside_code(answer)

    # Fallback: If no citations extracted but answer discusses files from retrieved chunks
    if not verified_citations and fallback_chunks:
        for c in fallback_chunks[:4]:
            fn = c["path"].split("/")[-1]
            if fn.lower() in clean_answer.lower() or c["path"].lower() in clean_answer.lower():
                cit = {"path": c["path"], "start_line": c["start_line"], "end_line": c["end_line"]}
                if cit not in verified_citations:
                    verified_citations.append(cit)

    # Ultimate fallback: attach top retrieved chunk
    if not verified_citations and fallback_chunks:
        c0 = fallback_chunks[0]
        verified_citations.append({"path": c0["path"], "start_line": c0["start_line"], "end_line": c0["end_line"]})

    # Consolidate overlapping / adjacent ranges for the same file
    by_file = {}
    for cit in verified_citations:
        by_file.setdefault(cit["path"], []).append((cit["start_line"], cit["end_line"]))

    consolidated = []
    for path, ranges in by_file.items():
        ranges.sort(key=lambda r: r[0])
        merged = []
        for s, e in ranges:
            if not merged:
                merged.append([s, e])
            else:
                last_s, last_e = merged[-1]
                if s <= last_e + 15:
                    merged[-1][1] = max(last_e, e)
                else:
                    merged.append([s, e])
        for s, e in merged:
            consolidated.append({"path": path, "start_line": s, "end_line": e})

    return clean_answer, consolidated[:5]

def ask_repo(repo_id: str, question: str, conversation_id: str | None = None) -> dict:
    """Invokes the LangGraph workflow to retrieve, synthesize, and verify repository answers."""
    from app.graph import run_repoask_graph
    return run_repoask_graph(repo_id, question, conversation_id)

def get_file_content(repo_id: str, file_path: str, start: int = 1, end: int = 0) -> dict:
    """Returns lines of an indexed file for the code viewer modal.
    Returns {path, start_line, end_line, lines: [{n, text}]}."""
    client = get_db()

    file_row = client.execute(
        "SELECT id, total_lines, content FROM files WHERE repo_id = ? AND path = ?",
        [repo_id, file_path]
    ).rows

    if not file_row:
        client.close()
        raise Exception(f"File '{file_path}' not found in this repository.")

    total_lines = file_row[0][1]
    direct_content = file_row[0][2]

    if direct_content:
        client.close()
        all_lines = [(i + 1, line) for i, line in enumerate(direct_content.splitlines())]
    else:
        chunk_rows = client.execute(
            "SELECT start_line, end_line, content FROM chunks WHERE repo_id = ? AND path = ? ORDER BY start_line ASC",
            [repo_id, file_path]
        ).rows
        client.close()

        all_lines = []
        for chunk_start, _, content in chunk_rows:
            for i, text in enumerate(content.splitlines()):
                ln = chunk_start + i
                all_lines.append((ln, text))

    seen = {}
    for ln, text in all_lines:
        if ln not in seen:
            seen[ln] = text

    actual_end = end if end > 0 else total_lines
    window = {ln: text for ln, text in seen.items() if start <= ln <= actual_end}
    if not window:
        window = seen

    lines = [{"n": ln, "text": text} for ln, text in sorted(window.items())]

    return {
        "path": file_path,
        "start_line": min(window.keys()) if window else start,
        "end_line": max(window.keys()) if window else actual_end,
        "lines": lines,
    }
