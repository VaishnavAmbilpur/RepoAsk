import os
from fastembed import TextEmbedding

_embedding_instance = None

def get_embedding_model() -> TextEmbedding:
    """Returns a shared, cached instance of the FastEmbed model."""
    global _embedding_instance
    if _embedding_instance is None:
        _embedding_instance = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    return _embedding_instance

def embed_texts(texts: list[str], batch_size: int = 64) -> list[list[float]]:
    """Embeds a batch of texts into 384-dimensional float vectors."""
    model = get_embedding_model()
    embeddings = list(model.embed(texts, batch_size=batch_size))
    return [e.tolist() for e in embeddings]

def embed_query(query: str) -> list[float]:
    """Embeds a single search query."""
    return embed_texts([query])[0]

