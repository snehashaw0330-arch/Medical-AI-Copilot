"""Acquire training/eval data for prescription OCR.

Run:  python -m backend.ocr.datasets <command>

Commands:
  synthetic   Generate labeled synthetic prescription lines (NO credentials).
  iam         Download the IAM handwriting DB via HuggingFace datasets.
  kaggle      Download a Kaggle prescription dataset (needs Kaggle API token).
  hf          Download a HuggingFace dataset by repo id.
  roboflow    Download a Roboflow dataset (needs ROBOFLOW_API_KEY).

Honesty note:
  * Synthetic generation is fully local and always works.
  * IAM/HF pull public data once `datasets`/`huggingface_hub` are installed.
  * Kaggle/Roboflow need YOUR credentials (env vars / ~/.kaggle/kaggle.json) —
    they cannot be embedded. MIMIC is intentionally omitted: it requires
    credentialed PhysioNet access + a data-use agreement and contains no
    prescription-handwriting images.
"""

from __future__ import annotations

import argparse
import os
import random
from pathlib import Path

from backend.config import ROOT_DIR

DATA_DIR = Path(ROOT_DIR) / "prescription-ocr" / "datasets"


# --------------------------------------------------------------------------
# Synthetic prescription-line generator (no credentials required)
# --------------------------------------------------------------------------
_MEDS = [
    "Paracetamol 650mg", "Amoxicillin 500mg", "Azithromycin 250mg",
    "Metformin 500mg", "Pantoprazole 40mg", "Cetirizine 10mg",
    "Augmentin 625", "Dolo 650", "Telmisartan 40mg", "Atorvastatin 10mg",
    "Omeprazole 20mg", "Ibuprofen 400mg", "Amlodipine 5mg", "Losartan 50mg",
]
_SIGS = ["1-0-1 x 5 days", "OD for 7 days", "BD x 3 days", "TDS after food",
         "HS x 10 days", "1 tab SOS", "0-0-1 x 1 week"]


def generate_synthetic(n: int = 500, out: Path | None = None) -> Path:
    """Render synthetic prescription lines with light augmentation + labels.txt.

    Produces an OCR fine-tuning corpus (image,text pairs) that needs no
    external data. Uses PIL; augments with rotation + noise to mimic photos.
    """
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    import numpy as np

    out = out or (DATA_DIR / "synthetic")
    img_dir = out / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    labels = []

    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except Exception:  # noqa: BLE001
        font = ImageFont.load_default()

    for i in range(n):
        text = f"{random.choice(_MEDS)}  {random.choice(_SIGS)}"
        img = Image.new("RGB", (640, 64), "white")
        draw = ImageDraw.Draw(img)
        draw.text((10, 16), text, fill=(20, 20, 60), font=font)
        # Augment: slight rotation + gaussian noise + blur (mimic camera).
        img = img.rotate(random.uniform(-4, 4), expand=False, fillcolor="white")
        arr = np.array(img).astype(np.int16)
        arr += np.random.normal(0, random.uniform(3, 14), arr.shape).astype(np.int16)
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        if random.random() < 0.4:
            img = img.filter(ImageFilter.GaussianBlur(random.uniform(0.4, 1.2)))
        name = f"rx_{i:05d}.png"
        img.save(img_dir / name)
        labels.append(f"{name}\t{text}")

    (out / "labels.txt").write_text("\n".join(labels), encoding="utf-8")
    print(f"[synthetic] wrote {n} samples -> {out}")
    return out


# --------------------------------------------------------------------------
# Public dataset downloaders
# --------------------------------------------------------------------------
def download_iam() -> None:
    try:
        from datasets import load_dataset  # type: ignore
    except Exception as e:  # noqa: BLE001
        raise SystemExit("pip install datasets") from e
    ds = load_dataset("Teklia/IAM-line", cache_dir=str(DATA_DIR / "iam"))
    print(f"[iam] downloaded: {ds}")


def download_hf(repo: str) -> None:
    try:
        from datasets import load_dataset  # type: ignore
    except Exception as e:  # noqa: BLE001
        raise SystemExit("pip install datasets") from e
    ds = load_dataset(repo, cache_dir=str(DATA_DIR / "hf"))
    print(f"[hf] {repo} downloaded: {ds}")


def download_kaggle(slug: str = "mehaksingal/illegible-medical-prescription-images-dataset") -> None:
    """Needs a Kaggle API token at ~/.kaggle/kaggle.json (or KAGGLE_* env)."""
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi  # type: ignore
    except Exception as e:  # noqa: BLE001
        raise SystemExit("pip install kaggle  and add ~/.kaggle/kaggle.json") from e
    api = KaggleApi()
    api.authenticate()
    dest = DATA_DIR / "kaggle"
    dest.mkdir(parents=True, exist_ok=True)
    api.dataset_download_files(slug, path=str(dest), unzip=True)
    print(f"[kaggle] {slug} -> {dest}")


def download_roboflow(workspace: str, project: str, version: int = 1) -> None:
    key = os.getenv("ROBOFLOW_API_KEY")
    if not key:
        raise SystemExit("Set ROBOFLOW_API_KEY")
    try:
        from roboflow import Roboflow  # type: ignore
    except Exception as e:  # noqa: BLE001
        raise SystemExit("pip install roboflow") from e
    rf = Roboflow(api_key=key)
    rf.workspace(workspace).project(project).version(version).download(
        "folder", location=str(DATA_DIR / "roboflow")
    )
    print("[roboflow] downloaded")


def main() -> None:
    p = argparse.ArgumentParser(description="Prescription OCR dataset tools")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("synthetic"); s.add_argument("-n", type=int, default=500)
    sub.add_parser("iam")
    k = sub.add_parser("kaggle"); k.add_argument("--slug", default="mehaksingal/illegible-medical-prescription-images-dataset")
    h = sub.add_parser("hf"); h.add_argument("repo")
    r = sub.add_parser("roboflow"); r.add_argument("workspace"); r.add_argument("project"); r.add_argument("--version", type=int, default=1)

    args = p.parse_args()
    if args.cmd == "synthetic":
        generate_synthetic(args.n)
    elif args.cmd == "iam":
        download_iam()
    elif args.cmd == "kaggle":
        download_kaggle(args.slug)
    elif args.cmd == "hf":
        download_hf(args.repo)
    elif args.cmd == "roboflow":
        download_roboflow(args.workspace, args.project, args.version)


if __name__ == "__main__":
    main()
