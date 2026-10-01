"""Offline, deterministic labeled NLI evaluation. No approval or data downloads."""
import argparse
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

from silhouette.storage.local_nli import LocalOnnxNLI

from silhouette.storage.nli_evaluation import metrics

def main():
    import pyarrow.parquet as pq
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-directory', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--data-directory', required=True)
    parser.add_argument('--dataset-revision', required=True)
    parser.add_argument('--output-directory', required=True)
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text())
    provider = LocalOnnxNLI(args.model_directory, **manifest)
    output = Path(args.output_directory)
    output.mkdir(parents=True, exist_ok=True)
    summary = {'model': manifest, 'dataset': 'facebook/xnli', 'dataset_revision': args.dataset_revision,
               'method': 'All en/es validation/test rows. Temperature selected per language only on validation NLL. Test never selects settings. No automated approval.',
               'results': {}}
    for language in ['en', 'es']:
        parts = {}
        provenance = {}
        for split in ['validation', 'test']:
            path = Path(args.data_directory) / language / f'{split}-00000-of-00001.parquet'
            provenance[split] = hashlib.sha256(path.read_bytes()).hexdigest()
            table = pq.read_table(path)
            expected = [0, 1, 2]
            if set(table['label'].to_pylist()) != set(expected):
                raise ValueError('Unexpected dataset labels')
            cached = output / f'{language}-{split}-scores.json'
            if cached.exists():
                prior = json.loads(cached.read_text())
                if (prior['parquet_sha256'] != provenance[split]
                        or prior.get('model') != manifest
                        or prior.get('dataset_revision') != args.dataset_revision):
                    raise ValueError('Cached dataset differs')
                parts[split] = prior['rows']
                continue
            rows, failures = [], []
            start = time.perf_counter()
            for index, source in enumerate(table.to_pylist()):
                try:
                    scores = asdict(provider.score(source['premise'], source['hypothesis']))
                    rows.append({'index': index, 'label': source['label'], 'scores': scores})
                except ValueError as error:
                    failures.append({'index': index, 'reason': str(error)})
            parts[split] = rows
            raw = {'language': language, 'split': split, 'rows': rows, 'failures': failures,
                   'parquet_sha256': provenance[split], 'model': manifest,
                   'dataset_revision': args.dataset_revision, 'elapsed_seconds': time.perf_counter() - start}
            (output / f'{language}-{split}-scores.json').write_text(json.dumps(raw, separators=(',', ':')) + '\n')
            print(language, split, len(rows), 'scored', len(failures), 'rejected', flush=True)
            # One expensive split per invocation; rerun to resume.
            return
        temperatures = [0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4]
        chosen = min(temperatures, key=lambda t: metrics(parts['validation'], t)['nll'])
        summary['results'][language] = {'parquet_sha256': provenance, 'temperature_grid': temperatures,
            'selected_temperature': chosen, 'validation_raw': metrics(parts['validation']),
            'test_raw': metrics(parts['test']), 'test_calibrated': metrics(parts['test'], chosen)}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
