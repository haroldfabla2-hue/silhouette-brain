import os
import sys
# Añadir el directorio raíz al path para encontrar módulos internos
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path: sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path: sys.path.append(core_dir)
import os
#!/usr/bin/env python3
"""
OpenAI Embeddings Integration
Uses text-embedding-3-small for semantic search
"""
import requests
import json

# OpenAI API
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = 1536

def get_openai_embedding(text: str) -> list:
    """Get embedding from OpenAI API"""
    API_KEY = os.getenv("OPENAI_API_KEY")
    
    response = requests.post(
        "https://api.openai.com/v1/embeddings",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "input": text,
            "model": EMBEDDING_MODEL,
            "dimensions": EMBEDDING_DIMENSIONS
        }
    )
    
    if response.status_code == 200:
        return response.json()["data"][0]["embedding"]
    else:
        raise Exception(f"OpenAI error: {response.status_code} - {response.text}")

def cosine_similarity(a: list, b: list) -> float:
    """Calculate cosine similarity between two embeddings"""
    dot_product = sum(x * y for x, y in zip(a, b))
    magnitude_a = sum(x * x for x in a) ** 0.5
    magnitude_b = sum(x * x for x in b) ** 0.5
    
    if magnitude_a == 0 or magnitude_b == 0:
        return 0
    
    return dot_product / (magnitude_a * magnitude_b)

# Test
if __name__ == "__main__":
    print("Testing OpenAI embeddings...")
    
    # Test embedding
    text = "Alberto trabaja en Brandistry usando n8n"
    embedding = get_openai_embedding(text)
    
    print(f"Generated embedding with {len(embedding)} dimensions")
    print(f"First 5 values: {embedding[:5]}")
    
    # Test similarity
    text2 = "Beto es el fundador de Brandistry"
    embedding2 = get_openai_embedding(text2)
    
    similarity = cosine_similarity(embedding, embedding2)
    print(f"\nSimilarity: {similarity:.4f}")
    
    # Cost estimate
    chars = len(text) + len(text2)
    tokens = chars // 4
    cost = tokens * 0.00002 / 1000
    print(f"Estimated cost for 2 embeddings: ${cost:.6f}")
