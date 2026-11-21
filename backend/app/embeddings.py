import os
import gc
from fastembed import TextEmbedding

_embedding_instance = None

def get_embedding_model() -> TextEmbedding:
    """Returns a shared, single-threaded FastEmbed model optimized for low memory."""
    global _embedding_instance
    if _embedding_instance is None:
        # threads=1 keeps ONNX Runtime memory footprint under 150MB
        _embedding_instance = TextEmbedding(
            model_name="BAAI/bge-small-en-v1.5",
            threads=1
        )
    return _embedding_instance

def embed_texts(texts: list[str], batch_size: int = 16) -> list[list[float]]:
    """Embeds a batch of texts with low memory streaming."""
    model = get_embedding_model()
    embeddings = []
    
    # Stream embeddings in small batches of 16 to avoid RAM spikes
    for emb in model.embed(texts, batch_size=batch_size):
        embeddings.append(emb.tolist())
    
    # Free memory back to Linux OS
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

