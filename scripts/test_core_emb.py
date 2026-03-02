import sys
import os
sys.path.insert(0, "/root/silhouette-brain/src/core")
from memory_core import get_memory_core
import numpy as np

core = get_memory_core()
text = "quien es alberto"
emb = core._get_embedding(text)
if emb:
    vec = np.frombuffer(emb, dtype=np.float32)
    print(f"Dimension: {len(vec)}")
else:
    print("No embedding generated")
