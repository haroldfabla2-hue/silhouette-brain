"""Offline candidate benchmark, no downloads, calibration or runtime activation."""
import argparse
import hashlib
import json
import platform
import resource
import statistics
import time
from dataclasses import asdict
from pathlib import Path

from silhouette.storage.local_nli import LocalOnnxNLI
from silhouette.storage.nli_evaluation import metrics


def main():
    import onnxruntime
    import pyarrow.parquet as pq
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-directory', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--parquet', required=True)
    parser.add_argument('--language', required=True)
    parser.add_argument('--dataset-revision', required=True)
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--count', type=int, default=250)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.start < 0 or not 1 <= args.count <= 10000:
        raise ValueError('Invalid row budget')
    manifest = json.loads(Path(args.manifest).read_text())
    start = time.perf_counter()
    provider = LocalOnnxNLI(args.model_directory, **manifest)
    load_ms = (time.perf_counter() - start) * 1000
    path = Path(args.parquet)
    sources = pq.read_table(path).to_pylist()
    if args.start + args.count > len(sources):
        raise ValueError('Requested rows exceed corpus, no duplicated examples')
    rows, failures = [], []
    for index in range(args.start, args.start + args.count):
        source = sources[index]
        start = time.perf_counter()
        try:
            scores = asdict(provider.score(source['premise'], source['hypothesis']))
            rows.append({'index': index, 'label': source['label'], 'scores': scores,
                         'ms': (time.perf_counter() - start) * 1000})
        except ValueError as error:
            failures.append({'index': index, 'reason': str(error)})
    times = sorted(r['ms'] for r in rows)
    result = {'manifest': manifest, 'python': platform.python_version(),
              'onnxruntime': onnxruntime.__version__, 'language': args.language,
              'dataset_revision': args.dataset_revision,
              'parquet_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'start': args.start, 'requested': args.count, 'load_ms': load_ms,
              'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              'p50_ms': statistics.median(times) if times else None,
              'p95_ms': times[max(0, int(len(times) * .95) - 1)] if times else None,
              'metrics': metrics(rows) if rows else None, 'rows': rows,
              'failures': failures, 'calibration': 'NONE',
              'status': 'EXPERIMENTAL_NOT_ACTIVATED',
              'limits': 'Public XNLI test subset, exploratory, not untouched domain holdout. CPU latency includes tokenizer/inference, excludes model load. RSS process high-water on Linux, not deployment estimate.'}
    Path(args.output).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ['rows', 'manifest']}, indent=2))


if __name__ == '__main__':
    main()
