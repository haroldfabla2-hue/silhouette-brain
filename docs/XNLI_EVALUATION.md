# Full English/Spanish labeled neural evaluation

October 1, 2026. Offline advice evaluation only. No runtime cutover or claim
approval. Builds on draft #8 and uses its pinned local quantized ONNX NLI model.

Sources and class order were verified from the dataset card:
https://huggingface.co/datasets/facebook/xnli
https://huggingface.co/datasets/facebook/xnli/blob/main/README.md
Model provenance: https://huggingface.co/cross-encoder/nli-MiniLM2-L6-H768

Pinned dataset revision b8dd5d7af51114dbda02c0e3f6133f332186418e.
Full validation 2,490 and test 5,010 rows per language, English and Spanish,
15,000 actual neural inferences total. All rows scored, no truncation or rejects.
The data are public translated NLI examples, not private owner memories.
Dataset labels entailment=0, neutral=1, contradiction=2; model order is different
and the provider explicitly maps it. Inputs are read offline from parquet.
No dataset text is bundled into source and no customer/user names are hardcoded.

| Test language | Correct / 5,010 | Accuracy | Raw ECE (10 bins) | Calibrated ECE | Raw NLL | Calibrated NLL |
| --- | --- | --- | --- | --- | --- | --- |
| English | 4,320 | 86.23% | 0.04342 | 0.01460 | 0.36992 | 0.35558 |
| Spanish | 3,285 | 65.57% | 0.14206 | 0.01317 | 0.89726 | 0.78546 |

Temperature is selected per language only on validation NLL over the explicit
fixed grid [0.5,0.75,1,1.25,1.5,2,3,4]: English 1.25, Spanish 2. Test is not used
for selection. Temperature changes confidence, not the winning class or accuracy.
Spanish 65.57% is a serious limit, not production-qualified multilingual NLI.
Calibration does not repair semantic errors or make statements true. Neither
language authorizes automatic acceptance. Lower ECE alone does not justify any
operational claim threshold. Domain shift, negation, instructions embedded in
text, translated annotation artifacts and actual memory corpus remain unknown.
Model trained on MNLI; XNLI derives from MNLI, so this is a public benchmark
rather than an independent deployment-domain qualification. No world-truth proof.

Reproduce with explicit trusted local inputs, `pip install pyarrow` plus prior
ONNX/tokenizer/numpy dependencies:

```
python scripts/evaluate_xnli.py --model-directory /trusted/model \
  --manifest docs/LOCAL_NLI_MANIFEST.json --data-directory /trusted/xnli \
  --dataset-revision b8dd5d7af51114dbda02c0e3f6133f332186418e \
  --output-directory /tmp/xnli-evaluation
```

Run repeatedly: each invocation computes one missing split and returns; final
invocation writes the summary once all four are present. Cached scores are
strictly for this trusted offline run, not untrusted uploaded results. File hashes,
confusion matrices, Brier/NLL/ECE and selected settings are committed in
XNLI_EVALUATION.json. Per-row scores are produced by the script, not source data.
No production model change or confidence gate is installed.
