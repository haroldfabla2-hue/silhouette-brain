#!/usr/bin/env python3
"""
ZhipuAI Embeddings + Reasoning
================================
- Embeddings: fastembed local (paraphrase-multilingual-MiniLM-L12-v2, 384 dims)
  ONNX optimizado, multilingüe (español + inglés), sin API key, sin rate limits.
  Fallback: TF-IDF numpy si fastembed no está instalado.

- Síntesis/Razonamiento: GLM-4.5-air de z.ai/ZhipuAI (bigmodel.cn)

Modelos disponibles confirmados en la cuenta z.ai:
  glm-4.5, glm-4.5-air, glm-4.6, glm-4.7, glm-5 (NO tienen sufijo -flash)
"""
import os
import re
import math
import json
import hashlib
import requests
import numpy as np

# ============================================================================
# Configuración
# ============================================================================

# Reasoning (síntesis) — z.ai / ZhipuAI
ZHIPU_API_BASE   = os.getenv("ZHIPU_API_BASE", "https://open.bigmodel.cn/api/paas/v4")
ZHIPU_API_KEY    = os.getenv("ZHIPU_API_KEY", "")
REASONING_MODEL  = os.getenv("ZHIPU_REASONING_MODEL", "glm-4.5-air")  # rápido, sin chain-of-thought

# Embeddings — fastembed local (ONNX, sin API)
FASTEMBED_MODEL  = os.getenv("FASTEMBED_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
EMBEDDING_DIMS   = 384    # paraphrase-multilingual-MiniLM-L12-v2 → 384 dims

REQUEST_TIMEOUT  = 20    # segundos para llamadas a z.ai


# ============================================================================
# EMBEDDINGS — fastembed local (ONNX) + fallback TF-IDF numpy
# ============================================================================

# Singleton del modelo fastembed (se carga una vez en memoria)
_fastembed_model = None

def _get_fastembed_model():
    global _fastembed_model
    if _fastembed_model is None:
        from fastembed import TextEmbedding
        _fastembed_model = TextEmbedding(FASTEMBED_MODEL)
    return _fastembed_model


def get_embedding(text: str) -> list:
    """
    Obtiene vector de embedding para un texto.
    Primario: fastembed local ONNX (384 dims, multilingüe, sin API, sin rate limits).
    Fallback:  TF-IDF numpy si fastembed no está disponible.
    """
    text = text.strip()[:1024]
    try:
        model = _get_fastembed_model()
        vectors = list(model.embed([text]))
        return vectors[0].tolist()
    except Exception:
        return _tfidf_embedding(text)


def get_embedding_batch(texts: list) -> list:
    """
    Embedding en batch — mucho más eficiente que llamadas individuales.
    Devuelve lista de vectores (uno por texto).
    """
    texts = [t.strip()[:1024] for t in texts]
    try:
        model = _get_fastembed_model()
        return [v.tolist() for v in model.embed(texts)]
    except Exception:
        return [_tfidf_embedding(t) for t in texts]


# Alias para compatibilidad con código que usa openai_embeddings
get_openai_embedding = get_embedding


# ── TF-IDF numpy (fallback sin dependencias externas) ─────────────────────

def _tokenize(text: str) -> list:
    return re.findall(r'\b\w+\b', text.lower())


_tfidf_vocab: dict = {}
_tfidf_idf:   dict = {}
_tfidf_dims:  int  = EMBEDDING_DIMS


def _build_tfidf_from_db():
    """Construye vocabulario TF-IDF desde la DB de conversaciones."""
    global _tfidf_vocab, _tfidf_idf, _tfidf_dims

    db_path = os.path.join(
        os.getenv("BRAIN_DATA_DIR", "/root/silhouette-brain/data"),
        "memory_core.db",
    )
    if not os.path.exists(db_path):
        return

    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT substr(message,1,200) FROM conversations ORDER BY timestamp DESC LIMIT 5000"
        ).fetchall()
        conn.close()

        docs = [r[0] for r in rows if r[0]]
        if not docs:
            return

        N = len(docs)
        df: dict = {}
        for doc in docs:
            tokens = set(_tokenize(doc))
            for t in tokens:
                df[t] = df.get(t, 0) + 1

        # Filtrar tokens muy raros o muy comunes
        filtered = {t: c for t, c in df.items() if 2 <= c <= N * 0.8}

        # Ordenar por frecuencia desc y tomar los top EMBEDDING_DIMS términos
        top_terms = sorted(filtered.keys(), key=lambda t: -df[t])[:EMBEDDING_DIMS]

        _tfidf_vocab = {t: i for i, t in enumerate(top_terms)}
        _tfidf_idf   = {t: math.log((N + 1) / (df.get(t, 0) + 1)) + 1.0 for t in top_terms}
        _tfidf_dims  = len(top_terms)

    except Exception:
        pass


def _tfidf_embedding(text: str) -> list:
    """TF-IDF embedding usando vocabulario de la DB. Fallback de último recurso."""
    global _tfidf_vocab, _tfidf_idf

    if not _tfidf_vocab:
        _build_tfidf_from_db()

    tokens = _tokenize(text)
    if not tokens or not _tfidf_vocab:
        # Sin vocabulario: fallback mínimo a hash (128 dims)
        return _hash_embedding(text)

    tf: dict = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1

    vec = np.zeros(len(_tfidf_vocab), dtype=np.float32)
    for t, count in tf.items():
        if t in _tfidf_vocab:
            vec[_tfidf_vocab[t]] = (1 + math.log(count)) * _tfidf_idf.get(t, 1.0)

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm

    return vec.tolist()


def _hash_embedding(text: str, dims: int = 128) -> list:
    """Fallback mínimo: hash de caracteres (sin dependencias)."""
    vec = np.zeros(dims, dtype=np.float32)
    for i, char in enumerate(text.lower()[:dims]):
        vec[i % dims] += ord(char)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.tolist()


# ============================================================================
# COSINE SIMILARITY
# ============================================================================

def cosine_similarity(a: list, b: list) -> float:
    """Similitud coseno entre dos vectores."""
    if not a or not b:
        return 0.0
    # Alinear dimensiones si difieren (puede ocurrir si hay mezcla de modelos)
    min_len = min(len(a), len(b))
    a, b = a[:min_len], b[:min_len]
    dot  = sum(x * y for x, y in zip(a, b))
    na   = sum(x * x for x in a) ** 0.5
    nb   = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ============================================================================
# SÍNTESIS / RAZONAMIENTO — GLM-4.7
# ============================================================================

SYNTHESIS_SYSTEM_PROMPT = (
    "Eres el núcleo cognitivo de Silhouette Brain, sistema de memoria de Alberto. "
    "Analiza los fragmentos de memoria y responde directamente en 2-3 oraciones en español. "
    "Solo usa información que esté explícitamente en los fragmentos. Sin explicaciones adicionales."
)


def _zhipu_headers() -> dict:
    key = ZHIPU_API_KEY
    if not key:
        raise RuntimeError(
            "ZHIPU_API_KEY no configurada. "
            "Ejecuta: export ZHIPU_API_KEY=<tu_token>"
        )
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def synthesize_context(query: str, memory_fragments: list) -> str:
    """
    Usa GLM-4.7 para sintetizar fragmentos de memoria en un resumen cohesionado.

    Args:
        query:            La consulta/pregunta del agente.
        memory_fragments: Lista de strings con fragmentos recuperados.

    Returns:
        String con la síntesis en lenguaje natural.
    """
    if not memory_fragments:
        return ""

    fragments_text = "\n".join(f"- {str(f)[:200]}" for f in memory_fragments[:12])
    user_message = (
        f"Consulta del agente: {query}\n\n"
        f"Fragmentos de memoria:\n{fragments_text}\n\n"
        f"Sintetiza qué es más relevante para esta consulta."
    )

    try:
        resp = requests.post(
            f"{ZHIPU_API_BASE}/chat/completions",
            headers=_zhipu_headers(),
            json={
                "model":       REASONING_MODEL,
                "messages": [
                    {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
                    {"role": "user",   "content": user_message},
                ],
                "temperature": 0.3,
                "max_tokens":  512,
                "stream":      False,
            },
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 200:
            msg = resp.json()["choices"][0]["message"]
            # GLM reasoning models: "content" = respuesta final, "reasoning_content" = chain-of-thought
            # Preferir content (respuesta final). Si está vacío, usar reasoning_content como fallback.
            content = (msg.get("content") or "").strip()
            if not content:
                content = (msg.get("reasoning_content") or "").strip()
                # Extraer solo el último párrafo coherente del chain-of-thought
                if content and "\n\n" in content:
                    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
                    content = paragraphs[-1] if paragraphs else content
            return content
        else:
            return f"[Síntesis no disponible: HTTP {resp.status_code}]"
    except Exception as e:
        return f"[Síntesis error: {e}]"


# ============================================================================
# TEST
# ============================================================================

if __name__ == "__main__":
    import sys

    print("=== Test HuggingFace Embeddings ===")
    try:
        t1 = "Alberto trabaja en Brandistry con automatización y n8n"
        t2 = "Beto es fundador de Brandistry, usa automatización"
        t3 = "El modelo de embeddings usa 384 dimensiones"

        e1 = get_embedding(t1)
        e2 = get_embedding(t2)
        e3 = get_embedding(t3)

        print(f"Modelo: HuggingFace paraphrase-multilingual-MiniLM-L12-v2")
        print(f"Dims:   {len(e1)}")
        print(f"Sim(t1,t2) = {cosine_similarity(e1, e2):.4f}  ← debe ser alto (>0.6)")
        print(f"Sim(t1,t3) = {cosine_similarity(e1, e3):.4f}  ← debe ser bajo (<0.4)")
    except Exception as e:
        print(f"ERROR embedding: {e}", file=sys.stderr)

    print("\n=== Test Síntesis GLM-4.7 ===")
    try:
        synthesis = synthesize_context(
            "¿En qué proyectos trabaja Alberto?",
            [
                "Alberto es el fundador de Brandistry",
                "Brandistry usa n8n para automatización",
                "Proyecto Nexus es el CRM interno",
                "Silhouette Brain es el sistema de memoria cognitiva",
            ]
        )
        print(f"Síntesis: {synthesis}")
    except Exception as e:
        print(f"ERROR síntesis: {e}", file=sys.stderr)
