# mDeBERTa candidate: blocked, not activated

The requested model profile is staged explicitly as MDEBERTA_MANIFEST.json.
Existing MiniLM profile, API defaults and advisory owner-review behavior stay
unchanged. No model download in runtime, no production cutover, no replacement
of existing features. Switching artifact manifests is already supported by
LocalOnnxNLI; this profile is experimental, not recommended for deployment yet.

Official source, read October 1, 2026:
https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-mnli-xnli
Revision 8adb042d524ecd5c26d3e3ba0e3fbcf7e2d0864c, MIT. Config explicitly maps
0 entailment, 1 neutral, 2 contradiction, different from the existing model.
Downloaded INT8 SHA-256 matches the publisher LFS hash (338,679,133 bytes).
Downloaded FP32 SHA-256 also matches (1,116,115,065 bytes). Hashes verify bytes,
not correctness of the export. Model binaries are not committed to the repo.

## Actual CPU candidate measurement

First 500 consecutive XNLI test rows per language, exploratory only, no tuned
thresholds, no sampling based on scores, no dropped examples:

| Language | Correct | Accuracy | Inference p50 | p95 | Peak RSS |
| --- | --- | --- | --- | --- | --- |
| English | 317/500 | 63.4% | 50.12ms | 81.84ms | 1,078,408 KiB |
| Spanish | 291/500 | 58.2% | 52.86ms | 80.34ms | 1,079,068 KiB |

Load including artifact hash checks was about 2.2s, with variation recorded.
One further reproducibility run on Spanish rows 500-749: 132/250=52.8%, load
3.10s, p50 50.09ms, p95 82.31ms, peak RSS 1,076,868 KiB. This is worse than the
published original model accuracy and blocks activation. Not a full-corpus or
matched-subset improvement claim; baseline full test has a different sample.
Tokenizer IDs/mask matched the local AutoTokenizer on a probe, but this does
NOT prove complete tokenizer/FP32/quantized parity or locate the defect.

FP32 initialized under 1,700MiB address-space cap failed std::bad_alloc. A bounded
larger attempt was killed in the 2GiB environment. Original PyTorch inference
and FP32/ONNX/INT8 parity remain UNVERIFIED. No claim that the trained model is
bad, nor a conclusion that quantization is definitely the cause. Required next:
measure original/FP32/INT8 on the same fixed inputs in a larger-memory trusted
environment, audit tokenizer/export/runtime, reject bad export instead of
changing labels to fit results. No paid compute or Codespace created.

## Calibration boundary

Author trained on XNLI development/validation. Do not fit temperature on it.
No new calibration is applied here because candidate correctness/parity failed.
A fresh independently labeled domain calibration set and separate untouched
domain test remain required, not substituted by authored smoke cases. Public
XNLI test comparisons are exploratory and cannot authorize auto acceptance.

Reproduce one bounded chunk with optional `pyarrow` and existing ONNX deps:

```
python scripts/benchmark_nli_candidate.py --model-directory /trusted/mdeberta \
 --manifest docs/MDEBERTA_MANIFEST.json --parquet /trusted/xnli/es-test.parquet \
 --language es --dataset-revision b8dd5d7af51114dbda02c0e3f6133f332186418e \
 --start 0 --count 250 --output /tmp/candidate.json
```

Script outputs scores, row indices, hashes, accuracy, p50/p95/load and process
RSS high-water. No network or calibration, no default provider selection.
Failures stay explicit. Resource/accuracy gate intentionally holds the swap.
