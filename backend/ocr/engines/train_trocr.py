"""Fine-tune TrOCR on prescription handwriting.

This is the honest path to "a model trained for medical prescriptions": take
TrOCR-handwritten and fine-tune it on (image, text) pairs — e.g. the synthetic
corpus from ``datasets.py synthetic`` and/or a Kaggle prescription dataset.

Requires a GPU for practical training. Run:
  python -m backend.ocr.datasets synthetic -n 2000
  python -m backend.ocr.engines.train_trocr \
      --data prescription-ocr/datasets/synthetic --epochs 5 --out models/trocr-rx

Then point the engine at it:  set OCR_TROCR_MODEL=models/trocr-rx
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="folder with images/ + labels.txt (name\\ttext)")
    ap.add_argument("--base", default="microsoft/trocr-base-handwritten")
    ap.add_argument("--out", default="models/trocr-rx")
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--batch", type=int, default=8)
    args = ap.parse_args()

    import torch
    from PIL import Image
    from torch.utils.data import Dataset
    from transformers import (
        TrOCRProcessor,
        VisionEncoderDecoderModel,
        Seq2SeqTrainer,
        Seq2SeqTrainingArguments,
    )

    data = Path(args.data)
    pairs = [
        (data / "images" / n, t)
        for n, t in (
            line.split("\t", 1)
            for line in (data / "labels.txt").read_text(encoding="utf-8").splitlines()
            if "\t" in line
        )
    ]
    processor = TrOCRProcessor.from_pretrained(args.base)

    class RxDataset(Dataset):
        def __len__(self):
            return len(pairs)

        def __getitem__(self, i):
            path, text = pairs[i]
            img = Image.open(path).convert("RGB")
            pixel_values = processor(img, return_tensors="pt").pixel_values[0]
            labels = processor.tokenizer(
                text, padding="max_length", max_length=64, truncation=True
            ).input_ids
            labels = [l if l != processor.tokenizer.pad_token_id else -100 for l in labels]
            return {"pixel_values": pixel_values, "labels": torch.tensor(labels)}

    model = VisionEncoderDecoderModel.from_pretrained(args.base)
    model.config.decoder_start_token_id = processor.tokenizer.cls_token_id
    model.config.pad_token_id = processor.tokenizer.pad_token_id

    targs = Seq2SeqTrainingArguments(
        output_dir=args.out,
        per_device_train_batch_size=args.batch,
        num_train_epochs=args.epochs,
        fp16=torch.cuda.is_available(),
        save_strategy="epoch",
        logging_steps=50,
    )
    Seq2SeqTrainer(model=model, args=targs, train_dataset=RxDataset()).train()
    model.save_pretrained(args.out)
    processor.save_pretrained(args.out)
    print(f"[train] saved fine-tuned TrOCR -> {args.out}")


if __name__ == "__main__":
    main()
