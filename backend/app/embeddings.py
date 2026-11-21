import os
import gc
import httpx

_embedding_instance = None

OPENROUTER_EMBED_MODELS = [
    "nvidia/nemotron-3.5-embed-1b:free",
    "nvidia/nemotron-3-embed-1b:free",
    "baai/bge-small-en-v1.5",
]

def _openrouter_embed(texts: list[str]) -> list[list[float]] | None:
    """Attempts to generate embeddings via OpenRouter API (0 MB local RAM usage)."""
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return None

    all_embeddings = []
    chunk_batch = 20

    for i in range(0, len(texts), chunk_batch):
        batch = texts[i:i + chunk_batch]
        success = False
        for model in OPENROUTER_EMBED_MODELS:
            try:
                res = httpx.post(
                    "https://openrouter.ai/api/v1/embeddings",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "HTTP-Referer": "https://repoask.app",
                        "X-Title": "RepoAsk",
                        "Content-Type": "application/json",
                    },
                    json={"model": model, "input": batch},
                    timeout=25.0,
                )
                if res.status_code == 200:
                    data = res.json().get("data", [])
                    data.sort(key=lambda x: x.get("index", 0))
                    all_embeddings.extend([item["embedding"] for item in data])
                    success = True
                    break
            except Exception:
                continue

        if not success:
            return None

    return all_embeddings if len(all_embeddings) == len(texts) else None


def get_embedding_model():
    """Returns a shared, single-threaded FastEmbed model (only loaded on demand)."""
    global _embedding_instance
    if _embedding_instance is None:
        from fastembed import TextEmbedding
        _embedding_instance = TextEmbedding(
            model_name="BAAI/bge-small-en-v1.5",
            threads=1
        )
    return _embedding_instance


def embed_texts(texts: list[str], batch_size: int = 8) -> list[list[float]]:
    """Embeds texts. Uses OpenRouter cloud API first (0 MB RAM), falls back to FastEmbed."""
    # 1. Try cloud embeddings (uses zero RAM on Render)
    cloud_result = _openrouter_embed(texts)
    if cloud_result:
        return cloud_result

    # 2. Local fallback using FastEmbed in ultra-small batches
    model = get_embedding_model()
    embeddings = []
    for emb in model.embed(texts, batch_size=batch_size):
        embeddings.append(emb.tolist())

    gc.collect()
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass

    return embeddings


def embed_query(query: str) -> list[float]:
    """Embeds a single search query."""
    return embed_texts([query], batch_size=1)[0]


