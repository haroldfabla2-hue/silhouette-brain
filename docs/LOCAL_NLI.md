# Local neural advice, explicit opt-in

Builds on owner-review PR #8. `LocalOnnxNLI` implements the real provider
protocol using ONNX Runtime CPU and the tokenizers package. It never downloads,
executes remote Python, modifies claims, or approves anything. Existing exact
extract and default no-provider behavior remain unchanged.

Install optional evaluation dependencies explicitly:
`pip install onnxruntime tokenizers numpy`.
Download model artifacts through your trusted deployment process, copy (not
symlink) them into one dedicated directory, and pin SHA-256 of model, tokenizer,
and config. The config must explicitly label entailment/contradiction/neutral;
no guessed label ordering. Model revision and name are required. Only CPU is
selected, thread count defaults to one. Long pairs fail, not truncate evidence.
Model binaries are trusted-local deployment inputs, not uploads from users.
This adapter is not a hostile model-file sandbox. No network provider involved.

Reproduce the actual integration smoke run:

```
python scripts/evaluate_local_nli.py --directory /trusted/model-directory \
  --manifest docs/LOCAL_NLI_MANIFEST.json --cases docs/LOCAL_NLI_SMOKE_CASES.json \
  --output /tmp/local-nli-result.json
```

The checked manifest pins cross-encoder/nli-MiniLM2-L6-H768 revision
b95119ce93d3e065de6214e38cd4a97b0f2f2c6d, quantized AVX2 ONNX export.
These are artifact identities, not client or owner data. Its model card labels
classes explicitly and says training used SNLI/MultiNLI:
https://huggingface.co/cross-encoder/nli-MiniLM2-L6-H768
https://www.sbert.net/docs/cross_encoder/pretrained_models.html

Actual October 1 CPU run on Python 3.10: 12 hand-authored English/Spanish smoke
cases, 11 correct, median 9.39ms inference, 493.91ms load. Six English cases:
6 correct. Six Spanish: 5 correct. The Spanish neutral music statement was
misclassified as contradiction. Full scores and input hashes are committed in
LOCAL_NLI_SMOKE_RESULT.json. These simple authored cases are not a held-out
quality set, not multilingual qualification, not calibrated confidence, not a
production relevance gate. Do not enable automated acceptance based on them.

142 local tests pass, no skips, lint and mypy pass. Six new tests validate
artifact/label/path/budget gates with invalid non-model files, not fake inference.
Actual neural inference is exercised separately by the reproducible script.
Real human UI/identity lifecycle, multilingual corpus, adversarial calibration,
provider timeout isolation and service-wide auth remain pending. Exact matching
and source revalidation in `review_statement` still apply and scores remain
NEEDS_OWNER_REVIEW, never ACCEPTED. Model revision needs deployment audit.
