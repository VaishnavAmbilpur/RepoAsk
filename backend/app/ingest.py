import os
import re
import shutil
import uuid
import stat
import tempfile
import git
from pathlib import Path
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter
from app.embeddings import embed_texts
from app.db import get_db, init_db

def parse_github_url(url: str):
    """Extracts owner, repo, and canonical URL from any GitHub link format."""
    match = re.search(r'(?:https?://)?(?:www\.)?github\.com/([^/\s?#]+)/([^/\s?#]+)', url.strip(), re.IGNORECASE)
    if not match:
        return None
    owner = match.group(1)
    name = match.group(2)
    if name.endswith('.git'):
        name = name[:-4]
    canonical = f"https://github.com/{owner}/{name}"
    return owner, name, canonical

def safe_rmtree(path_str):
    """Safely removes a directory tree on Windows by clearing read-only attributes."""
    if not os.path.exists(path_str):
        return
    for root, dirs, files in os.walk(path_str, topdown=False):
        for f in files:
            p = os.path.join(root, f)
            try:
                os.chmod(p, stat.S_IWRITE)
                os.remove(p)
            except Exception:
                pass
        for d in dirs:
            p = os.path.join(root, d)
            try:
                os.chmod(p, stat.S_IWRITE)
                os.rmdir(p)
            except Exception:
                pass
    try:
        os.rmdir(path_str)
    except Exception:
        pass

IGNORE_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", "__pycache__", 
    ".venv", "venv", "env", ".idea", ".vscode", "target", "bin", "obj", 
    ".next", ".nuxt", "coverage", ".turbo", ".cache", "pods"
}

IGNORE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".lock", ".min.js", ".min.css", 
    ".pyc", ".exe", ".dll", ".so", ".dylib", ".bin", ".pt", ".pth", ".safetensors", 
    ".onnx", ".weights", ".h5", ".zip", ".tar", ".gz", ".7z", ".rar", ".mp4", ".mp3", 
    ".wav", ".pdf", ".ttf", ".woff", ".woff2", ".eot", ".map", ".parquet", ".arrow",
    ".db", ".sqlite", ".sqlite3", ".log", ".csv", ".tsv", ".iso", ".dmg"
}

LANGUAGE_MAP = {
    ".py": Language.PYTHON,
    ".js": Language.JS,
    ".jsx": Language.JS,
    ".ts": Language.TS,
    ".tsx": Language.TS,
    ".mjs": Language.JS,
    ".cjs": Language.JS,
    ".html": Language.HTML,
    ".md": Language.MARKDOWN,
    ".go": Language.GO,
    ".rs": Language.RUST,
    ".java": Language.JAVA,
    ".cpp": Language.CPP,
    ".cc": Language.CPP,
    ".cxx": Language.CPP,
    ".c": Language.CPP,
    ".h": Language.CPP,
    ".hpp": Language.CPP,
    ".cs": Language.CSHARP,
    ".rb": Language.RUBY,
    ".php": Language.PHP,
    ".scala": Language.SCALA,
    ".swift": Language.SWIFT,
    ".kt": Language.KOTLIN,
}

TEXT_EXTENSIONS = {
    ".txt", ".rst", ".json", ".yaml", ".yml", ".toml", ".sql", ".sh", ".bash", 
    ".zsh", ".css", ".scss", ".xml", ".graphql", ".gql", ".env.example", ".ini"
}

def ingest_repository(repo_url: str, storage_dir: str | Path | None = None) -> dict:
    """Clones, chunks, embeds, and stores any GitHub repository in Turso."""
    parsed = parse_github_url(repo_url)
    if not parsed:
        raise ValueError("Invalid GitHub URL. Expected format: https://github.com/owner/repository")
    
    owner, repo_name, clean_url = parsed
    init_db()
    client = get_db()
    
    # Check if repository was already indexed; if so, reuse ID and clean previous chunks
    existing_repo = client.execute("SELECT id FROM repositories WHERE url = ?", [clean_url]).rows
    if existing_repo:
        repo_id = existing_repo[0][0]
        client.execute("DELETE FROM chunks WHERE repo_id = ?", [repo_id])
        client.execute("DELETE FROM files WHERE repo_id = ?", [repo_id])
    else:
        repo_id = str(uuid.uuid4())[:8]
        client.execute(
            "INSERT INTO repositories (id, owner, name, url) VALUES (?, ?, ?, ?)",
            [repo_id, owner, repo_name, clean_url]
        )
    
    # Store temporary clone outside the backend directory so uvicorn --reload doesn't restart
    base_dir = Path(storage_dir) if storage_dir else Path(tempfile.gettempdir()) / "codeatlas_repos"
    base_dir.mkdir(parents=True, exist_ok=True)
    clone_path = base_dir / f"{owner}_{repo_name}_{repo_id}"
    safe_rmtree(str(clone_path))
    
    # 1. Shallow clone with terminal prompt disabled (prevents interactive auth hang)
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        git.Repo.clone_from(clean_url, str(clone_path), depth=1, env=env)
    except Exception as ge:
        safe_rmtree(str(clone_path))
        raise ValueError(f"Could not clone repository '{clean_url}'. Please ensure it exists and is public.")
    
    chunks_to_insert = []
    files_to_insert = []
    total_files = 0
    
    # 3. Walk files and chunk by language
    for root, dirs, files in os.walk(clone_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        
        for file_name in files:
            file_path = Path(root) / file_name
            ext = file_path.suffix.lower()
            file_lower = file_name.lower()
            
            if ext in IGNORE_EXTENSIONS:
                continue
                
            # Skip large files (> 500KB) to prevent OOM
            try:
                if file_path.stat().st_size > 500_000:
                    continue
            except Exception:
                continue

            lang = None
            if ext in LANGUAGE_MAP:
                lang = LANGUAGE_MAP[ext]
            elif file_lower.startswith("readme") or ext in TEXT_EXTENSIONS or file_lower in {"dockerfile", "makefile", "procfile", "gemfile"}:
                lang = None
            else:
                continue
            
            relative_path = str(file_path.relative_to(clone_path)).replace("\\", "/")
            
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            
            lines = content.splitlines()
            if not lines:
                continue
                
            file_id = str(uuid.uuid4())[:8]
            files_to_insert.append((
                "INSERT INTO files (id, repo_id, path, total_lines, content) VALUES (?, ?, ?, ?, ?)",
                [file_id, repo_id, relative_path, len(lines), content]
            ))
            total_files += 1
            
            if lang:
                splitter = RecursiveCharacterTextSplitter.from_language(
                    language=lang,
                    chunk_size=900,
                    chunk_overlap=120
                )
            else:
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=900,
                    chunk_overlap=120,
                    separators=["\n## ", "\n### ", "\n\n", "\n", " ", ""]
                )
            
            text_chunks = splitter.split_text(content)
            
            for chunk_text in text_chunks:
                clean_chunk = chunk_text.strip()
                if not clean_chunk:
                    continue

                start_line = content.find(chunk_text[:50])
                if start_line != -1:
                    start_line = content[:start_line].count("\n") + 1
                else:
                    start_line = 1
                
                end_line = start_line + chunk_text.count("\n")
                
                chunks_to_insert.append({
                    "id": str(uuid.uuid4())[:8],
                    "repo_id": repo_id,
                    "file_id": file_id,
                    "path": relative_path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "content": chunk_text
                })

    if total_files == 0:
        safe_rmtree(str(clone_path))
        client.close()
        raise ValueError(f"No readable code or text files found in {clean_url}.")

    # Batch insert files in fast bulk operations (max 40 statements per HTTP call to Turso)
    if files_to_insert:
        batch_size = 40
        for i in range(0, len(files_to_insert), batch_size):
            client.batch(files_to_insert[i:i + batch_size])

    # 4. Generate vectors in-process and save (batch execute for high speed over HTTP)
    if chunks_to_insert:
        # Cap chunks per repo to stay well within 512MB RAM on cloud free tiers
        max_chunks = 120
        if len(chunks_to_insert) > max_chunks:
            # Separate priority chunks (root README, entry points, architecture docs)
            priority_chunks = []
            standard_chunks = []
            for c in chunks_to_insert:
                p_low = c["path"].lower()
                if p_low in ["readme.md", "readme.rst", "readme.txt"] or p_low.endswith("/readme.md"):
                    priority_chunks.append(c)
                elif any(p_low.endswith(x) for x in ["main.py", "app.py", "index.js", "index.ts", "server.js", "package.json", "go.mod", "cargo.toml"]):
                    priority_chunks.append(c)
                else:
                    standard_chunks.append(c)

            # Round-robin select chunks from remaining files
            file_chunk_map = {}
            for c in standard_chunks:
                file_chunk_map.setdefault(c["path"], []).append(c)
            
            balanced_chunks = list(priority_chunks)
            remaining_slots = max(50, max_chunks - len(priority_chunks))
            max_per_file = max(1, remaining_slots // max(1, len(file_chunk_map)))

            for p, chs in file_chunk_map.items():
                balanced_chunks.extend(chs[:max(2, max_per_file)])
            
            chunks_to_insert = balanced_chunks[:max_chunks]

        texts = [c["content"] for c in chunks_to_insert]
        embeddings = embed_texts(texts)
        
        batch_statements = []
        for chunk, emb in zip(chunks_to_insert, embeddings):
            emb_str = str(emb)
            batch_statements.append((
                """INSERT INTO chunks 
                   (id, repo_id, file_id, path, start_line, end_line, content, embedding) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [chunk["id"], chunk["repo_id"], chunk["file_id"], chunk["path"], 
                 chunk["start_line"], chunk["end_line"], chunk["content"], emb_str]
            ))

        # Send in batches of 40 statements per HTTP request to Turso
        batch_chunk_size = 40
        for i in range(0, len(batch_statements), batch_chunk_size):
            slice_stmts = batch_statements[i:i + batch_chunk_size]
            client.batch(slice_stmts)

    client.close()
    safe_rmtree(str(clone_path))
    
    return {
        "repo_id": repo_id,
        "repo_name": repo_name,
        "files_indexed": total_files,
        "chunks_indexed": len(chunks_to_insert)
    }