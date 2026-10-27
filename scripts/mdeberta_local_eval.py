"""One-command, offline-comparable NLI evaluation: current model vs mDeBERTa variants.

Question it answers: on the SAME public Spanish (and optionally English) XNLI test
rows, does an mDeBERTa variant that actually fits the target machine beat the
current model, and is the INT8 export faithful to the original weights?

Datasets (--datasets, default xnli):
  xnli    facebook/xnli test split, es config is the machine-translated XNLI Spanish (CC BY-NC 4.0)
  esxnli  artetxem/esxnli: 2,490 pairs per language ORIGINALLY annotated in Spanish and
          professionally translated (not part of XNLI train/dev/test, so the candidate has
          not seen them; no explicit license file, the repo requests academic citation)

Variants (all scored on identical rows, never tuned, no calibration, no thresholds):
  baseline_minilm_int8     current model (cross-encoder/nli-MiniLM2-L6-H768, quantized ONNX)
  mdeberta_pytorch_fp32    original weights in PyTorch: the reference for "is the export faithful"
  mdeberta_onnx_fp32       official ONNX FP32 export
  mdeberta_onnx_int8       official ONNX INT8 export (previously measured 58.2% on 500 es rows)

Run (needs: pip install -e . torch transformers onnxruntime tokenizers numpy pyarrow huggingface_hub):
  python scripts/mdeberta_local_eval.py --workdir ~/silhouette-nli-eval

Downloads happen only here, once, from pinned revisions, and every file is checked
against a pinned SHA-256 before use. Nothing is downloaded at runtime by the product.
Each variant runs in its own process so peak RSS is that variant's own. Re-running resumes.
The XNLI validation split is NOT used: the candidate was trained on it.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import statistics
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

from silhouette.storage.nli_candidate_eval import (
    paired,
    parse_esxnli,
    percentile,
    verify_artifact,
    wilson_interval,
)
from silhouette.storage.nli_evaluation import LABELS, metrics

DATASET = 'facebook/xnli'
DATASET_REVISION = 'b8dd5d7af51114dbda02c0e3f6133f332186418e'
DATA_HASH = {'es': 'c0159c9a734d7d0683d20a9850adcf3e214a49179b6517fea5868744bfd99886'}
ESXNLI_REVISION = 'b03a5a4d4db700deaa7dd6cf5d4d2d179696905c'
ESXNLI_URL = f'https://raw.githubusercontent.com/artetxem/esxnli/{ESXNLI_REVISION}/esxnli.tsv'
ESXNLI_SHA256 = 'e5a4ac15738511c8d021f66046234482bf57013b861ae536a86d08bef4ac3ffd'
MD = 'MoritzLaurer/mDeBERTa-v3-base-mnli-xnli'
MD_REV = '8adb042d524ecd5c26d3e3ba0e3fbcf7e2d0864c'
MD_FILES = {
    'config.json': '4e4430c95100d613df80fa01276f231931e1b535557cf62fbb3cc50323e50cca',
    'tokenizer.json': '3aca3ce69a0a35aeb144a52c4f1d41c4246b8785f8f398315cc8fb6b24057810',
    'spm.model': '13c8d666d62a7bc4ac8f040aab68e942c861f93303156cc28f5c7e885d86d6e3',
    'tokenizer_config.json': 'df9fd3a4482cc4a866788244824573fab8e74dadd1609d4f0e5997f9e96921dc',
    'special_tokens_map.json': '9463f61e1b109a8eb4688b829260d7c6b1e6dff04c98ff7269bb89e2b92369b9',
    'added_tokens.json': 'fb697283833d25e2c711f1bc37730ecd8b20f4bd5f015db1d84aefe0adc9155a',
    'model.safetensors': '65af59b1ff4450b09ecbf13ca35c840dbf038b26ff8e10e5ea89ca724828ed1e',
    'onnx/model.onnx': '7d39629484bdad052176a0cff26ffe408d8c2b69c7abd242716fee320badd661',
    'onnx/model_quantized.onnx': '27c39e884c14b03cf46cfc5485971b6db70ff330220d93dfe729c63fde43af0e',
}
MINI = 'cross-encoder/nli-MiniLM2-L6-H768'
MINI_REV = 'b95119ce93d3e065de6214e38cd4a97b0f2f2c6d'
MINI_FILES = {
    'config.json': '8b0e41caff7567c0f53e6983f35591c3dec59507c9173ab125c5823394fb57f3',
    'tokenizer.json': '82139106e603ee4e1d5bc99d056ccbed5a92bc24848b1b5a7137c26e00d0dbf6',
    'onnx/model_quint8_avx2.onnx': '44391a5241a62e0083c1a8899a71e69a092b95aea5ba89e14062925468eceac7',
}
VARIANTS = ['baseline_minilm_int8', 'mdeberta_pytorch_fp32', 'mdeberta_onnx_fp32', 'mdeberta_onnx_int8']
MAX_TOKENS = 512
# Published by the model author, NOT measured here. Shown only so a reader can see the gap.
AUTHOR_REPORTED_ES_ACCURACY = 0.845


def fetch(workdir: Path) -> dict:
    from huggingface_hub import hf_hub_download
    paths = {}
    for repo, rev, files, key in [(MD, MD_REV, MD_FILES, 'md'), (MINI, MINI_REV, MINI_FILES, 'mini')]:
        directory = workdir / key
        for name, expected in files.items():
            target = directory / name
            if not target.exists():
                print('downloading', repo, name, flush=True)
                hf_hub_download(repo, name, revision=rev, local_dir=str(directory))
            verify_artifact(target, expected)
        paths[key] = directory
    return paths


def load_rows(workdir: Path, language: str, limit: int | None) -> list[dict]:
    import pyarrow.parquet as pq
    from huggingface_hub import hf_hub_download
    name = f'{language}/test-00000-of-00001.parquet'
    target = workdir / 'xnli' / name
    if not target.exists():
        hf_hub_download(DATASET, name, repo_type='dataset', revision=DATASET_REVISION,
                        local_dir=str(workdir / 'xnli'))
    if language in DATA_HASH:
        verify_artifact(target, DATA_HASH[language])
    rows = pq.read_table(target).to_pylist()
    if {r['label'] for r in rows} != {0, 1, 2}:
        raise ValueError('Unexpected dataset labels (expected entailment=0, neutral=1, contradiction=2)')
    return rows[:limit] if limit else rows


def load_esxnli_rows(workdir: Path, language: str, limit: int | None) -> list[dict]:
    import urllib.request
    target = workdir / 'esxnli' / 'esxnli.tsv'
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        print('downloading', ESXNLI_URL, flush=True)
        with urllib.request.urlopen(ESXNLI_URL, timeout=120) as response:
            target.write_bytes(response.read())
    verify_artifact(target, ESXNLI_SHA256)
    rows = parse_esxnli(target.read_text(), language)
    return rows[:limit] if limit else rows


def load_dataset_rows(workdir: Path, dataset: str, language: str, limit: int | None) -> list[dict]:
    if dataset == 'esxnli':
        return load_esxnli_rows(workdir, language, limit)
    return load_rows(workdir, language, limit)


def make_scorer(variant: str, paths: dict, threads: int, device: str):
    """Return score(premise, hypothesis) -> dict label->probability. Fails on over-budget pairs."""
    if variant.startswith('baseline') or 'onnx' in variant:
        from silhouette.storage.local_nli import LocalOnnxNLI
        if variant == 'baseline_minilm_int8':
            provider = LocalOnnxNLI(str(paths['mini']), model_file='onnx/model_quint8_avx2.onnx',
                                    model_sha256=MINI_FILES['onnx/model_quint8_avx2.onnx'],
                                    tokenizer_sha256=MINI_FILES['tokenizer.json'],
                                    config_sha256=MINI_FILES['config.json'], name=MINI,
                                    revision=MINI_REV, max_tokens=MAX_TOKENS, threads=threads)
        else:
            file = 'onnx/model.onnx' if variant == 'mdeberta_onnx_fp32' else 'onnx/model_quantized.onnx'
            provider = LocalOnnxNLI(str(paths['md']), model_file=file, model_sha256=MD_FILES[file],
                                    tokenizer_sha256=MD_FILES['tokenizer.json'],
                                    config_sha256=MD_FILES['config.json'], name=MD,
                                    revision=MD_REV, max_tokens=MAX_TOKENS, threads=threads)
        return lambda p, h: asdict(provider.score(p, h))
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    torch.set_num_threads(threads)
    directory = str(paths['md'])
    tokenizer = AutoTokenizer.from_pretrained(directory)
    model = AutoModelForSequenceClassification.from_pretrained(directory, torch_dtype=torch.float32)
    if device == 'cuda':
        if not torch.cuda.is_available():
            raise RuntimeError('--device cuda requested but CUDA is not available')
        model = model.to('cuda')
    model.eval()
    labels = [str(model.config.id2label[i]).lower() for i in range(3)]
    if set(labels) != set(LABELS):
        raise ValueError('Explicit three-class label mapping required')

    def score(premise: str, hypothesis: str) -> dict:
        encoded = tokenizer(premise, hypothesis, return_tensors='pt', truncation=False)
        if encoded['input_ids'].shape[1] > MAX_TOKENS:
            raise ValueError('Pair exceeds token budget')
        with torch.no_grad():
            logits = model(**{k: v.to(device) for k, v in encoded.items()}).logits[0].double().cpu()
        if not torch.isfinite(logits).all():
            raise ValueError('Invalid NLI output')
        probs = torch.softmax(logits, dim=0).tolist()
        return dict(zip(labels, probs, strict=True))
    return score


def run_variant(args) -> None:
    workdir = Path(args.workdir).expanduser()
    paths = {'md': workdir / 'md', 'mini': workdir / 'mini'}
    rows = load_dataset_rows(workdir, args.dataset, args.language, args.limit)
    start = time.perf_counter()
    score = make_scorer(args.run_variant, paths, args.threads, args.device)
    load_ms = (time.perf_counter() - start) * 1000
    for _ in range(5):  # warm-up, not counted
        score(rows[0]['premise'], rows[0]['hypothesis'])
    scored, failures = [], []
    for index, source in enumerate(rows):
        t0 = time.perf_counter()
        try:
            scores = score(source['premise'], source['hypothesis'])
            scored.append({'index': index, 'label': source['label'], 'scores': scores,
                           'ms': (time.perf_counter() - t0) * 1000})
        except ValueError as error:
            failures.append({'index': index, 'reason': str(error)})
        if index % 250 == 249:
            print(args.run_variant, args.language, index + 1, '/', len(rows), flush=True)
    times = [r['ms'] for r in scored]
    out = {'variant': args.run_variant, 'language': args.language, 'dataset': args.dataset,
           'dataset_revision': ESXNLI_REVISION if args.dataset == 'esxnli' else DATASET_REVISION,
           'rows_requested': len(rows), 'limit': args.limit, 'threads': args.threads,
           'device': args.device if args.run_variant == 'mdeberta_pytorch_fp32' else 'cpu',
           'load_ms': load_ms, 'p50_ms': statistics.median(times), 'p95_ms': percentile(times, .95),
           'peak_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
           'failures': failures, 'metrics': metrics(scored),
           'python': platform.python_version(), 'rows': scored}
    Path(args.cache_file).write_text(json.dumps(out, separators=(',', ':')) + '\n')
    print(args.run_variant, args.language, 'accuracy', out['metrics']['accuracy'],
          'p50_ms', out['p50_ms'], 'peak_rss_mib', out['peak_rss_mib'], flush=True)


def tokenizer_parity(workdir: Path, rows: list[dict]) -> dict:
    """Do the two tokenizers used (tokenizers/tokenizer.json vs transformers) give identical ids?"""
    from tokenizers import Tokenizer
    from transformers import AutoTokenizer
    fast = Tokenizer.from_file(str(workdir / 'md' / 'tokenizer.json'))
    fast.no_truncation()
    fast.no_padding()
    reference = AutoTokenizer.from_pretrained(str(workdir / 'md'))
    mismatches = [i for i, r in enumerate(rows)
                  if fast.encode(r['premise'], r['hypothesis']).ids
                  != reference(r['premise'], r['hypothesis'], truncation=False)['input_ids']]
    return {'rows': len(rows), 'mismatching_rows': len(mismatches), 'first_mismatches': mismatches[:10]}


def report(workdir: Path, language: str, dataset: str, caches: dict, parity: dict | None) -> None:
    if dataset == 'esxnli':
        heading = f'# NLI candidate comparison, esXNLI {language}'
        provenance = (f'Dataset artetxem/esxnli@{ESXNLI_REVISION} (originally annotated in Spanish, '
                      'professionally translated; NOT part of XNLI train/dev/test). Same rows for every '
                      'variant. No calibration, no tuned thresholds.')
    else:
        heading = f'# NLI candidate comparison, XNLI {language} test'
        provenance = f'Dataset {DATASET}@{DATASET_REVISION}. Same rows for every variant. No calibration, no tuned thresholds.'
    lines = [heading, '', provenance,
             f'Machine: {platform.platform()}, Python {platform.python_version()}.', '',
             '| Variant | Rows scored | Rejected | Accuracy | 95% CI (Wilson) | p50 ms | p95 ms | Peak RSS MiB |',
             '| --- | --- | --- | --- | --- | --- | --- | --- |']
    summary = {'language': language, 'dataset': dataset,
               'dataset_revision': ESXNLI_REVISION if dataset == 'esxnli' else DATASET_REVISION,
               'variants': {}, 'paired_vs': {}}
    for name, c in caches.items():
        m = c['metrics']
        lo, hi = wilson_interval(m['correct'], m['scored'])
        lines.append(f"| {name} | {m['scored']} | {len(c['failures'])} | {m['accuracy']:.4f} | "
                     f"{lo:.4f} to {hi:.4f} | {c['p50_ms']:.1f} | {c['p95_ms']:.1f} | {c['peak_rss_mib']:.0f} |")
        summary['variants'][name] = {k: c[k] for k in ['rows_requested', 'limit', 'threads', 'device', 'load_ms',
                                                        'p50_ms', 'p95_ms', 'peak_rss_mib', 'metrics']}
        summary['variants'][name]['rejected'] = len(c['failures'])
    if dataset == 'xnli' and language == 'es':
        lines += ['', f'Author-reported mDeBERTa es accuracy on this test set: '
                  f'{AUTHOR_REPORTED_ES_ACCURACY} (model card, NOT measured here).']
    for ref_name, others in [('mdeberta_pytorch_fp32', ['mdeberta_onnx_fp32', 'mdeberta_onnx_int8']),
                             ('baseline_minilm_int8', ['mdeberta_pytorch_fp32', 'mdeberta_onnx_fp32',
                                                       'mdeberta_onnx_int8'])]:
        if ref_name not in caches:
            continue
        lines += ['', f'## Paired comparison against {ref_name}', '',
                  '| Variant | Prediction agreement | Only reference correct | Only variant correct | Max abs prob diff |',
                  '| --- | --- | --- | --- | --- |']
        for other in others:
            if other in caches and other != ref_name:
                a, b = caches[ref_name]['rows'], caches[other]['rows']
                common = sorted({r['index'] for r in a} & {r['index'] for r in b})
                a = [r for r in a if r['index'] in set(common)]
                b = [r for r in b if r['index'] in set(common)]
                p = paired(a, b)
                summary['paired_vs'].setdefault(ref_name, {})[other] = p
                lines.append(f"| {other} | {p['prediction_agreement']:.4f} | {p['only_reference_correct']} | "
                             f"{p['only_other_correct']} | {p['max_abs_probability_diff']:.4f} |")
    if parity:
        summary['tokenizer_parity'] = parity
        lines += ['', f"Tokenizer parity (tokenizers vs transformers): {parity['mismatching_rows']} of "
                      f"{parity['rows']} rows differ."]
    lines += ['', 'How to read this (decision inputs, not a decision):',
              '- PyTorch FP32 far below the author-reported figure points at the setup (tokenizer, labels, runtime), not the export.',
              '- PyTorch FP32 near it but INT8 far below: the INT8 export or quantization is the defect. Do not use that file.',
              '- A swap only makes sense if a variant that fits the target machine beats baseline_minilm_int8 with '
              'non-overlapping confidence intervals AND is faithful to PyTorch FP32.',
              '- Public XNLI test is a benchmark, not your memory domain. It does not authorize automatic acceptance.']
    prefix = 'report' if dataset == 'xnli' else f'report-{dataset}'
    (workdir / f'{prefix}-{language}.md').write_text('\n'.join(lines) + '\n')
    (workdir / f'{prefix}-{language}.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('\n'.join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--workdir', default='~/silhouette-nli-eval')
    parser.add_argument('--languages', default='es', help='comma list from: es, en')
    parser.add_argument('--datasets', default='xnli', help='comma list from: xnli, esxnli')
    parser.add_argument('--dataset', default='xnli', help=argparse.SUPPRESS)
    parser.add_argument('--limit', type=int, default=None, help='first N rows only (quick check, labeled as such)')
    parser.add_argument('--threads', type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu',
                        help='PyTorch variant only; ONNX variants always run on CPU')
    parser.add_argument('--variants', default=','.join(VARIANTS))
    parser.add_argument('--run-variant', help=argparse.SUPPRESS)
    parser.add_argument('--language', help=argparse.SUPPRESS)
    parser.add_argument('--cache-file', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.run_variant:
        run_variant(args)
        return
    workdir = Path(args.workdir).expanduser()
    workdir.mkdir(parents=True, exist_ok=True)
    fetch(workdir)
    for dataset in args.datasets.split(','):
        if dataset not in ('xnli', 'esxnli'):
            raise SystemExit('datasets must be xnli and/or esxnli')
        for language in args.languages.split(','):
            if language not in ('es', 'en'):
                raise SystemExit('languages must be es and/or en')
            rows = load_dataset_rows(workdir, dataset, language, args.limit)
            caches = {}
            for variant in args.variants.split(','):
                if variant not in VARIANTS:
                    raise SystemExit(f'unknown variant {variant}')
                stem = f'{variant}-{language}' if dataset == 'xnli' else f'{dataset}-{variant}-{language}'
                cache = workdir / f'{stem}-{args.limit or "full"}-t{args.threads}-{args.device}.json'
                if not cache.exists():
                    code = subprocess.call([sys.executable, __file__, '--workdir', str(workdir), '--run-variant',
                                            variant, '--language', language, '--dataset', dataset,
                                            '--cache-file', str(cache),
                                            '--threads', str(args.threads), '--device', args.device]
                                           + (['--limit', str(args.limit)] if args.limit else []))
                    if code != 0:
                        print(f'VARIANT FAILED: {variant} {dataset}/{language} (exit {code}). Reported as failed, not skipped silently.')
                        continue
                caches[variant] = json.loads(cache.read_text())
            parity = None
            try:
                parity = tokenizer_parity(workdir, rows)
            except ImportError:
                print('transformers not installed: tokenizer parity not measured')
            report(workdir, language, dataset, caches, parity)


if __name__ == '__main__':
    main()
