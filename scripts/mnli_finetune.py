#!/usr/bin/env python3
"""Fine-tune microsoft/mdeberta-v3-base (MIT) on MultiNLI for Spanish NLI via cross-lingual transfer.

Why: the current NLI candidate (MoritzLaurer/mDeBERTa-v3-base-mnli-xnli) was trained on XNLI
(CC BY-NC 4.0, non-commercial). This script trains the same architecture from the MIT base on
MultiNLI only (OANC / CC BY 3.0 / CC BY-SA 3.0 / public domain - commercially usable with
attribution; see docs/NLI_FINETUNE_PLAN.md). An English-only fine-tune transfers zero-shot to
Spanish; the published reference for this exact recipe is mDeBERTaV3-base, XNLI avg 79.8% /
es 84.4% (DeBERTaV3 paper, ICLR 2023, arXiv:2111.09543, Table 6). That is Microsoft's number,
NOT ours: measure ours with scripts/mdeberta_local_eval.py before adopting anything.

Requires: pip install torch transformers datasets
Runs on CPU (slow - use --sample) or GPU. Nothing here runs automatically; it is a manual tool.

Usage (laptop, overnight subsample):
  python scripts/mnli_finetune.py --sample 100000 --output ~/silhouette-nli-eval/finetuned

Then evaluate with REAL numbers (XNLI-es + esXNLI):
  python scripts/mdeberta_local_eval.py --datasets xnli,esxnli --variants mdeberta_finetuned_local
"""

from __future__ import annotations

import argparse
import random
import time

BASE_MODEL = 'microsoft/mdeberta-v3-base'  # MIT license (model card)
DATASET = 'nyu-mll/multi_nli'  # majority OANC (permissive); fiction: CC BY 3.0 / CC BY-SA 3.0 / public domain (US)
# Hyperparameters published by MoritzLaurer for mDeBERTa-v3-base-mnli-xnli (model card).
ID2LABEL = {0: 'entailment', 1: 'neutral', 2: 'contradiction'}
LABEL2ID = {v: k for k, v in ID2LABEL.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample', type=int, default=100_000,
                        help='stratified subsample of MultiNLI train (default 100k; full = 393k, CPU-days)')
    parser.add_argument('--epochs', type=float, default=2)
    parser.add_argument('--lr', type=float, default=2e-5)
    parser.add_argument('--batch', type=int, default=16)
    parser.add_argument('--warmup-ratio', type=float, default=0.1)
    parser.add_argument('--weight-decay', type=float, default=0.06)
    parser.add_argument('--max-len', type=int, default=256)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--output', default='~/silhouette-nli-eval/finetuned')
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    args = parser.parse_args()

    import torch
    from datasets import load_dataset
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
    )

    from pathlib import Path
    output = Path(args.output).expanduser()
    output.mkdir(parents=True, exist_ok=True)
    random.seed(args.seed)
    torch.manual_seed(args.seed)

    print(f'loading {DATASET} train split...', flush=True)
    dataset = load_dataset(DATASET, split='train')  # 392,702 pairs, labels 0/1/2
    if args.sample and args.sample < len(dataset):
        # Stratified subsample: keep the label balance of the full set.
        by_label: dict[int, list[int]] = {0: [], 1: [], 2: []}
        for index, label in enumerate(dataset['label']):
            by_label[label].append(index)
        per_label = args.sample // 3
        indices: list[int] = []
        for label, pool in sorted(by_label.items()):
            indices.extend(random.sample(pool, min(per_label, len(pool))))
        dataset = dataset.select(sorted(indices))
    print(f'training rows: {len(dataset)} (sample={args.sample}, seed={args.seed})', flush=True)

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)

    def tokenize(batch):
        return tokenizer(batch['premise'], batch['hypothesis'], truncation=True, max_length=args.max_len)

    dataset = dataset.map(tokenize, batched=True, remove_columns=['premise', 'hypothesis'])

    model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL, num_labels=3, id2label=ID2LABEL, label2id=LABEL2ID
    )
    if args.device == 'cuda':
        if not torch.cuda.is_available():
            raise RuntimeError('--device cuda requested but CUDA is not available')
        model = model.to('cuda')

    training_args = TrainingArguments(
        output_dir=str(output / 'checkpoints'),
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        per_device_train_batch_size=args.batch,
        warmup_ratio=args.warmup_ratio,
        weight_decay=args.weight_decay,
        seed=args.seed,
        use_cpu=args.device == 'cpu',
        save_strategy='no',  # single final save below; no intermediate checkpoint clutter
        report_to=[],
    )
    trainer = Trainer(model=model, args=training_args, train_dataset=dataset)

    print('starting training - this is the slow part. Config:', flush=True)
    print(f'  base={BASE_MODEL} rows={len(dataset)} epochs={args.epochs} lr={args.lr} '
          f'batch={args.batch} max_len={args.max_len} device={args.device}', flush=True)
    start = time.perf_counter()
    trainer.train()
    hours = (time.perf_counter() - start) / 3600
    model.save_pretrained(str(output))
    tokenizer.save_pretrained(str(output))
    print(f'done in {hours:.2f}h. Model saved to {output}', flush=True)
    print('NEXT: measure real accuracy before adopting:')
    print('  python scripts/mdeberta_local_eval.py --datasets xnli,esxnli --variants mdeberta_finetuned_local',
          flush=True)


if __name__ == '__main__':
    main()
