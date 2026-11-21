from fastembed import TextEmbedding

def test_fastembed_generates_vector():
    """Verify FastEmbed generates 384-dimension vector embeddings."""
    model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    
    code_snippet = "def calculate_total(price, tax): return price + (price * tax)"
    
    embeddings = list(model.embed([code_snippet]))
    
    assert len(embeddings) == 1
    vector = embeddings[0]
    
    # bge-small produces 384-dimensional float vectors
    assert len(vector) == 384
    assert float(vector[0]) != 0.0