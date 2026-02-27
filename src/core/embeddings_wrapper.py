import os
#!/usr/bin/env python3
"""
Wrapper for memory_core_embeddings to use with API
"""
import sys
sys.path.insert(0, os.getenv('BRAIN_SRC_DIR', os.path.dirname(os.path.abspath(__file__))))
from memory_noise_filter import is_operational_runtime_noise, is_runtime_diagnostic_query

def get_memory_core_embeddings(query: str, limit: int = 5):
    """
    Búsqueda semántica usando embeddings
    """
    from memory_core_embeddings import get_memory_core
    
    try:
        core = get_memory_core()
        results = core.search_context(query, limit=limit)
        allow_runtime_noise = is_runtime_diagnostic_query(query)
        safe_results = []
        for result in results:
            message = result.get("message", "")
            if not allow_runtime_noise and is_operational_runtime_noise(message):
                continue
            safe_results.append(result)
            if len(safe_results) >= limit:
                break
        
        return {
            "query": query,
            "found": len(safe_results),
            "results": [
                {
                    "message": r.get("message", "")[:300],
                    "speaker": r.get("speaker", ""),
                    "similarity": r.get("similarity", 0)
                }
                for r in safe_results
            ]
        }
    except Exception as e:
        return {"error": str(e), "query": query}

# Test
if __name__ == "__main__":
    result = get_memory_core_embeddings("Alberto Brandistry", 3)
    print(result)
