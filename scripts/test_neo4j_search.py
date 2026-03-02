import sys
import os
sys.path.insert(0, "/root/silhouette-brain/src/core")
from memory_core import get_memory_core
import numpy as np

core = get_memory_core()

print("Querying node locally...")
results = core.search_context("codigo hiper secreto alberto", limit=5)
print(f"Found {len(results)} results.")
for r in results:
    print(r)
