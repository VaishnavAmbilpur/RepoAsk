"""
Comprehensive API endpoint tests for CodeAtlas.
Covers: healthz, list repos, index repo, ask, file viewer, tour, CORS, error handling.
Requires network (Turso Cloud, GitHub clone, OpenRouter, ONNX model download).
Run with:  .\.venv\Scripts\python.exe -m pytest tests/test_api_endpoints.py -v
"""

import re
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# ---------- known test repo (already indexed in Turso Cloud) ----------
KNOWN_REPO_ID = "4233d148"          # octocat/Hello-World
KNOWN_REPO_FILE = "README"          # only file in Hello-World
TEST_REPO_URL = "https://github.com/octocat/Hello-World"


# ── 1. Health & Root ──────────────────────────────────────────────────

class TestHealth:
    def test_healthz_returns_ok(self):
        res = client.get("/healthz")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["service"] == "codeatlas-api"

    def test_root_returns_info(self):
        res = client.get("/")
        assert res.status_code == 200
        body = res.json()
        assert "CodeAtlas" in body["message"]


# ── 2. List Repositories ─────────────────────────────────────────────

class TestListRepos:
    def test_list_repos_returns_200(self):
        res = client.get("/api/repos")
        assert res.status_code == 200
        body = res.json()
        assert "repositories" in body
        assert isinstance(body["repositories"], list)

    def test_list_repos_shape(self):
        """Each repository record must have id, owner, name, url, created_at."""
        res = client.get("/api/repos")
        repos = res.json()["repositories"]
        if repos:
            first = repos[0]
            for key in ("id", "owner", "name", "url", "created_at"):
                assert key in first, f"Missing key '{key}' in repo record"

    def test_known_repo_appears(self):
        """The Hello-World test repo should already be indexed."""
        res = client.get("/api/repos")
        ids = [r["id"] for r in res.json()["repositories"]]
        assert KNOWN_REPO_ID in ids, "octocat/Hello-World not found in Turso"


# ── 3. Index Repository ──────────────────────────────────────────────

class TestIndexRepo:
    def test_index_invalid_url_returns_400(self):
        res = client.post("/api/repos", json={"url": "https://gitlab.com/foo/bar"})
        assert res.status_code == 400
        assert "github.com" in res.json()["detail"].lower()

    def test_index_empty_url_returns_422(self):
        """Pydantic rejects missing 'url' field."""
        res = client.post("/api/repos", json={})
        assert res.status_code == 422

    def test_index_known_repo_succeeds(self):
        """Re-indexing Hello-World should succeed and return correct shape."""
        res = client.post("/api/repos", json={"url": TEST_REPO_URL})
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "success"
        data = body["data"]
        assert data["repo_name"] == "Hello-World"
        assert data["repo_id"] == KNOWN_REPO_ID   # same ID on re-index
        assert data["files_indexed"] >= 1
        assert data["chunks_indexed"] >= 1


# ── 4. Ask (Grounded Q&A) ────────────────────────────────────────────

class TestAsk:
    def test_ask_returns_answer(self):
        res = client.post("/api/ask", json={
            "repo_id": KNOWN_REPO_ID,
            "question": "What is this repository about?"
        })
        assert res.status_code == 200
        body = res.json()
        assert "answer" in body
        assert isinstance(body["answer"], str)
        assert len(body["answer"]) > 0
        assert "citations" in body

    def test_ask_returns_retrieved_chunks(self):
        res = client.post("/api/ask", json={
            "repo_id": KNOWN_REPO_ID,
            "question": "Summarize the README"
        })
        body = res.json()
        assert "retrieved_chunks" in body
        assert isinstance(body["retrieved_chunks"], list)

    def test_ask_missing_repo_id_returns_422(self):
        res = client.post("/api/ask", json={"question": "hello?"})
        assert res.status_code == 422

    def test_ask_nonexistent_repo(self):
        """Asking about a repo with no chunks should gracefully return a message."""
        res = client.post("/api/ask", json={
            "repo_id": "does_not_exist_12345",
            "question": "What is this?"
        })
        assert res.status_code == 200
        body = res.json()
        assert "no code" in body["answer"].lower() or "answer" in body


# ── 5. File Viewer ────────────────────────────────────────────────────

class TestFileViewer:
    def test_get_file_content(self):
        res = client.get(f"/api/repos/{KNOWN_REPO_ID}/file", params={"path": KNOWN_REPO_FILE})
        assert res.status_code == 200
        body = res.json()
        assert body["path"] == KNOWN_REPO_FILE
        assert "content" in body
        assert len(body["content"]) > 0

    def test_get_file_not_found(self):
        res = client.get(f"/api/repos/{KNOWN_REPO_ID}/file", params={"path": "nonexistent.py"})
        assert res.status_code == 200  # returns error in body, not 404
        body = res.json()
        assert "error" in body

    def test_get_file_missing_path_returns_422(self):
        res = client.get(f"/api/repos/{KNOWN_REPO_ID}/file")
        assert res.status_code == 422


# ── 6. AI Guided Tour ────────────────────────────────────────────────

class TestTour:
    def test_tour_returns_markdown(self):
        res = client.get(f"/api/repos/{KNOWN_REPO_ID}/tour")
        assert res.status_code == 200
        body = res.json()
        assert "tour" in body
        assert isinstance(body["tour"], str)
        assert len(body["tour"]) > 10
        assert body["repo_id"] == KNOWN_REPO_ID

    def test_tour_includes_metadata(self):
        res = client.get(f"/api/repos/{KNOWN_REPO_ID}/tour")
        body = res.json()
        assert "repo_name" in body
        assert "files_count" in body
        assert body["files_count"] >= 1

    def test_tour_nonexistent_repo(self):
        res = client.get("/api/repos/no_such_repo_999/tour")
        assert res.status_code == 200
        body = res.json()
        assert "error" in body


# ── 7. CORS Headers ──────────────────────────────────────────────────

class TestCORS:
    def test_cors_allows_localhost_5173(self):
        res = client.options(
            "/api/repos",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert res.status_code == 200
        assert "access-control-allow-origin" in res.headers

    def test_cors_allows_127_0_0_1_5173(self):
        res = client.options(
            "/api/repos",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert res.status_code == 200
        assert "access-control-allow-origin" in res.headers

    def test_cors_allows_post(self):
        res = client.options(
            "/api/repos",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert res.status_code == 200
        allow = res.headers.get("access-control-allow-methods", "")
        assert "POST" in allow.upper() or "*" in allow


# ── 8. Internal: Citation Verification ───────────────────────────────

class TestCitationVerification:
    def test_verify_strips_bad_citation(self):
        from app.ask import verify_citations
        answer_with_bad = "Check [fake_file.py:L1-L99] for details."
        clean, cites = verify_citations(KNOWN_REPO_ID, answer_with_bad)
        assert "fake_file.py" not in clean
        # fake citation should be stripped
        assert len([c for c in cites if c["path"] == "fake_file.py"]) == 0

    def test_verify_keeps_valid_citation(self):
        from app.ask import verify_citations
        answer_with_good = f"See [{KNOWN_REPO_FILE}:L1-L1] for the intro."
        clean, cites = verify_citations(KNOWN_REPO_ID, answer_with_good)
        assert KNOWN_REPO_FILE in clean
        assert any(c["path"] == KNOWN_REPO_FILE for c in cites)


# ── 9. Internal: Cosine Similarity ───────────────────────────────────

class TestCosineSimilarity:
    def test_identical_vectors_return_1(self):
        from app.ask import cosine_similarity
        v = [0.1, 0.2, 0.3, 0.4]
        assert abs(cosine_similarity(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors_return_0(self):
        from app.ask import cosine_similarity
        assert abs(cosine_similarity([1, 0], [0, 1])) < 1e-6

    def test_zero_vector_returns_0(self):
        from app.ask import cosine_similarity
        assert cosine_similarity([0, 0], [1, 2]) == 0.0

