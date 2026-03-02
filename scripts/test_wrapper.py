import sys
import os
sys.path.insert(0, "/root/silhouette-brain/src/core")
from embeddings_wrapper import get_memory_core_embeddings

print(get_memory_core_embeddings("codigo hiper secreto", limit=5))
