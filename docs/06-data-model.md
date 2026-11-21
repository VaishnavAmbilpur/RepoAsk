# Data Model

## Database Schema

RepoAsk uses 3 tables in SQLite (local) or Turso (cloud).

### Entity Relationship

```
repositories  1 ──── * files  1 ──── * chunks
```

---

### `repositories`

Stores metadata for each indexed GitHub repository.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | 8-char UUID prefix (e.g., `a1b2c3d4`) |
| `owner` | TEXT | NOT NULL | GitHub owner (e.g., `pallets`) |
| `name` | TEXT | NOT NULL | Repository name (e.g., `flask`) |
| `url` | TEXT | NOT NULL, UNIQUE | Canonical URL (`https://github.com/owner/repo`) |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | When the repository was indexed |

**Behavior on re-index:** If a repository with the same URL already exists, the existing `id` is reused and all previous `chunks` and `files` are deleted before re-indexing.

---

### `files`

Stores the full content of each indexed file.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | 8-char UUID prefix |
| `repo_id` | TEXT | NOT NULL, FK → repositories.id | Parent repository |
| `path` | TEXT | NOT NULL | Relative path from repo root (e.g., `app/main.py`) |
| `total_lines` | INTEGER | NOT NULL | Line count of the file |
| `content` | TEXT | nullable | Full file content (UTF-8) |

**Usage:** The `content` column enables the file viewer modal and citation verification. The `path` column is used for citation matching.

---

### `chunks`

Stores language-aware code chunks with their vector embeddings.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | 8-char UUID prefix |
| `repo_id` | TEXT | NOT NULL, FK → repositories.id | Parent repository |
| `file_id` | TEXT | nullable | FK → files.id |
| `path` | TEXT | NOT NULL | File path (duplicated for query convenience) |
| `start_line` | INTEGER | NOT NULL | First line number in the original file |
| `end_line` | INTEGER | NOT NULL | Last line number in the original file |
| `content` | TEXT | NOT NULL | The chunk text (up to 900 chars) |
| `embedding` | TEXT | NOT NULL | JSON-encoded float array (384 dimensions) |

**Embedding format:** The `embedding` column stores a Python list serialized with `str(vector.tolist())`. It is parsed back with `json.loads()` at query time.

---

## Indexing Limits

| Limit | Value | Reason |
|---|---|---|
| Max file size | 500 KB | Prevent OOM on minified files |
| Max chunks per repo | 450 | Prevent embedding timeout |
| Chunk size | 900 characters | Fits in embedding model context window |
| Chunk overlap | 120 characters | Preserves context at boundaries |
| Min chunks per file | 2 | Ensures every file has representation |

## Filtered Content

The ingestion pipeline skips:

**Directories:** `.git`, `node_modules`, `vendor`, `dist`, `build`, `__pycache__`, `.venv`, `venv`, `.idea`, `.vscode`, `target`, `bin`, `obj`, `.next`, `.nuxt`, `coverage`, `.turbo`, `.cache`, `pods`

**Extensions:** Images (`.png`, `.jpg`, `.gif`, `.svg`), binaries (`.exe`, `.dll`, `.so`), ML models (`.pt`, `.pth`, `.safetensors`, `.onnx`), archives (`.zip`, `.tar`, `.gz`), media (`.mp4`, `.mp3`), fonts (`.ttf`, `.woff`), data (`.csv`, `.parquet`, `.db`), locks (`.lock`), source maps (`.map`)

