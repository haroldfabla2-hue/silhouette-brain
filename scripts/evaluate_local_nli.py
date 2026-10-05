"""Reproducible offline smoke evaluation; not an independent quality benchmark."""
import argparse
import hashlib
import json
import platform
import statistics
import time
from dataclasses import asdict
from pathlib import Path

from silhouette.storage.local_nli import LocalOnnxNLI

parser = argparse.ArgumentParser()
parser.add_argument('--directory', required=True)
parser.add_argument('--manifest', required=True)
parser.add_argument('--cases', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
manifest = json.loads(Path(args.manifest).read_text())
start = time.perf_counter()
provider = LocalOnnxNLI(args.directory, **manifest)
load_ms = (time.perf_counter() - start) * 1000
cases_path = Path(args.cases)
cases = json.loads(cases_path.read_text())
rows = []
for case in cases:
    start = time.perf_counter()
    scores = asdict(provider.score(case['premise'], case['hypothesis']))
    rows.append({**case, 'scores': scores, 'prediction': max(scores, key=scores.get),
                 'ms': (time.perf_counter() - start) * 1000})
result = {'provider': manifest, 'python': platform.python_version(), 'cases_sha256':
          hashlib.sha256(cases_path.read_bytes()).hexdigest(), 'load_ms': load_ms,
          'count': len(rows), 'correct': sum(r['prediction'] == r['label'] for r in rows),
          'median_ms': statistics.median(r['ms'] for r in rows), 'rows': rows,
          'limits': 'Hand-authored smoke cases, not held-out labeled quality; no automatic approvals.'}
Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))
