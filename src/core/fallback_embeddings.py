#!/usr/bin/env python3
import os
import sys
# Añadir el directorio raíz al path para encontrar módulos internos
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path: sys.path.append(base_dir)
core_dir = os.path.join(base_dir, "core")
if core_dir not in sys.path: sys.path.append(core_dir)
"""
Fallback Embedding System
Uses local simple embeddings when OpenAI fails
"""
import hashlib
import numpy as np

def simple_embedding(text):
    """Generate simple hash-based embedding as fallback"""
    # Create a simple vector from text
    text = text.lower()
    vector = np.zeros(128)
    
    # Use character frequencies as features
    for i, char in enumerate(text[:128]):
        vector[i % 128] += ord(char)
    
    # Normalize
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector = vector / norm
    
    return vector.tolist()

def cosine_similarity(a, b):
    """Calculate cosine similarity"""
    dot = sum(x*y for x,y in zip(a,b))
    norm1 = sum(x*x for x in a) ** 0.5
    norm2 = sum(x*x for x in b) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0
    return dot / (norm1 * norm2)

if __name__ == "__main__":
    # Test
    e1 = simple_embedding("Alberto es vegetariano")
    e2 = simple_embedding("Beto no come carne")
    e3 = simple_embedding("python code")
    
    print(f"Alberto vs Beto: {cosine_similarity(e1, e2):.3f}")
    print(f"Alberto vs Python: {cosine_similarity(e1, e3):.3f}")
