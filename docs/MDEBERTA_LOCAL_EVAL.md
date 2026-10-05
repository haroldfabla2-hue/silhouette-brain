# mDeBERTa local evaluation (one command)

Offline measurement only. No runtime change, no model download by the product,
no claim approval, no calibration, no thresholds tuned on the result.

## Why this exists

The earlier mDeBERTa INT8 run scored 58.2% on 500 Spanish XNLI rows, below the
current model, while the model author reports 84.5% for Spanish on the same test
set (model card, not measured here). FP32 would not load in a 2 GB environment, so
nothing separated "the export is broken" from "the setup is wrong". This script
scores four variants on the SAME rows so that question gets a measured answer:

| Variant | What it tells you |
| --- | --- |
| `baseline_minilm_int8` | the current model, the number to beat |
| `mdeberta_pytorch_fp32` | original weights in PyTorch, the reference |
| `mdeberta_onnx_fp32` | official ONNX FP32 export, is the export faithful |
| `mdeberta_onnx_int8` | official INT8 export, is quantization the defect |

It also reports paired agreement against the PyTorch reference, accuracy with a 95%
Wilson interval, p50/p95 latency, per-variant peak RSS (each variant runs in its own
process), and tokenizer parity between the two tokenizers in use.

## Run it

```
pip install -e ".[nli-eval]"
python scripts/mdeberta_local_eval.py --workdir ~/silhouette-nli-eval
```

Downloads about 2.5 GB once, from pinned revisions, and checks every file against a
pinned SHA-256 before use. A mismatch stops the run. Re-running resumes from cached
variants. Expect roughly 20 to 40 minutes on a laptop CPU for Spanish (5,010 rows x 4
variants). Options: `--languages es,en`, `--limit 500` for a quick check (labeled as a
subset in the output), `--threads N`, and `--device cuda` for the PyTorch variant
only. The PyTorch variant runs FP32 (the model does not support FP16). Send back
`report-es.md` and `report-es.json` from the work directory. They contain scores and
hashes only, no secrets and no private data (public XNLI text).

The XNLI validation split is deliberately not used: the candidate was trained on it.

## What was verified before handing this over (real runs, 2 GB Linux box)

- `baseline_minilm_int8`, full Spanish test, 5,010 rows: 3,285 correct = 65.57%
  (95% interval 64.24% to 66.87%), 0 rejected. This reproduces the number already
  committed in `XNLI_EVALUATION.json`, so the harness matches the earlier pipeline.
- `mdeberta_onnx_int8`, first 500 Spanish rows: 291 correct = 58.2%, the same figure
  as the earlier run. On those rows the baseline scored 68.6% (343/500).
- Tokenizer parity on those 500 rows: 9 rows differ between `tokenizers` (used by the
  ONNX path) and `transformers`. They come from 3 sentences: two contain the ellipsis
  character (one tokenizer gives the piece "...", the other the unknown token) and one
  contains the ordinal "º" (piece "o" versus unknown token). That is a real difference
  in 1.8% of these rows, far too small to explain a gap of about 26 points, but the full
  run will quantify it.
- NOT verified here: the PyTorch FP32 and ONNX FP32 variants. Both exceed this 2 GB
  machine (the PyTorch process was killed by the OS while loading, which the script
  reports as a failed variant instead of skipping it). Their code paths are untested
  against real weights until you run it. If one fails on your machine the report says
  so explicitly.

## How to read the result (inputs to a decision, not a decision)

- PyTorch FP32 far below 84.5%: suspect the setup (tokenizer, label order, runtime), not the export.
- PyTorch FP32 near 84.5% but INT8 far below: the INT8 export is the defect. Do not use that file.
- ONNX FP32 matching PyTorch FP32 but INT8 not: quantization is the cause.
- A swap is only worth considering if a variant that fits the target machine beats
  `baseline_minilm_int8` with non-overlapping intervals and is faithful to PyTorch FP32.
- Public XNLI is a benchmark, not your memory domain. A good score here still does not
  authorize automatic acceptance; owner review stays in the loop.
