"""Dataset discovery + preprocessing for batch prescription OCR evaluation.

This module is the entry point for turning a *folder of prescription images*
(e.g. ``datasets/prescriptions/illegible_dataset/``) into OCR-ready inputs.

It does two things:

1. **Discovery** — :func:`discover_images` recursively walks a directory and
   returns every supported image, in a stable (natural-sorted) order.

2. **Preprocessing** — :func:`preprocess_image` runs the classic document
   cleanup pipeline requested for this dataset:

       Resize → Grayscale → Deskew → Denoising → CLAHE → Contrast
       enhancement → Sharpening → (optional) Adaptive Threshold

   The individual steps reuse the project's already-tuned OpenCV helpers in
   :mod:`backend.ocr.preprocess` so behaviour stays consistent with the live
   upload flow and there is a single source of truth for the heavy lifting.

   Deep OCR models (EasyOCR) are *hurt* by hard binarisation, so the default
   output is an enhanced **grayscale** image. Adaptive thresholding is exposed
   for the classic/Tesseract path via ``binarize=True``.

Everything here is defensive: if OpenCV is unavailable or a step fails, the
original image path is used so the pipeline degrades gracefully instead of
crashing the whole dataset run.
"""

from __future__ import annotations

import re
from pathlib import Path

try:
    import cv2
    import numpy as np
except Exception:  # pragma: no cover - OpenCV optional at import time
    cv2 = None  # type: ignore
    np = None  # type: ignore

from backend.ocr import preprocess as pp

# Image formats we know OpenCV can decode. The dataset is JPG, but we accept the
# common siblings so the same loader works for any future prescription folder.
IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
)


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------
def _natural_key(path: Path) -> list:
    """Sort key so ``2.jpg`` comes before ``10.jpg`` (human/natural order)."""
    return [
        int(chunk) if chunk.isdigit() else chunk.lower()
        for chunk in re.split(r"(\d+)", path.name)
    ]


def discover_images(root: str | Path) -> list[Path]:
    """Recursively find every supported image under ``root``.

    Returns an empty list (never raises) if the directory does not exist, so
    callers can report "0 images" cleanly instead of erroring.
    """
    root_path = Path(root)
    if not root_path.exists() or not root_path.is_dir():
        return []
    images = [
        p
        for p in root_path.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]
    images.sort(key=_natural_key)
    return images


def count_images(root: str | Path) -> int:
    """Cheap count of discoverable images under ``root``."""
    return len(discover_images(root))


# --------------------------------------------------------------------------
# Preprocessing pipeline (Resize → Grayscale → Deskew → Denoise → CLAHE →
# Contrast → Sharpen → optional Adaptive Threshold)
# --------------------------------------------------------------------------
def preprocess_image(image_path: str | Path, *, binarize: bool = False) -> "np.ndarray | None":
    """Return a cleaned image array ready for OCR, or ``None`` on failure.

    Steps (each delegates to a tested helper in :mod:`backend.ocr.preprocess`):

    * **Resize** — normalise the longest edge into the OCR-friendly band and
      super-resolve tiny scans (``_super_resolve`` + ``_resize_to_band``).
    * **Grayscale** — collapse to a single intensity channel.
    * **Deskew** — straighten rotated/tilted handwriting (``_deskew``), after a
      coarse 90°/180° orientation fix (``_orientation_correct``).
    * **Denoising + CLAHE + Contrast + Sharpening** — ``_enhance`` runs
      Non-Local-Means denoising, background/brightness normalisation, CLAHE
      contrast equalisation and an unsharp mask in one tuned pass.
    * **Adaptive Threshold** — only when ``binarize=True`` (classic/Tesseract
      path). Skipped by default because it degrades deep models.
    """
    if cv2 is None:
        return None
    try:
        img = pp._read(str(image_path))           # decode
        img = pp._perspective_correct(img)        # flatten the page if detected
        img = pp._super_resolve(img)              # Resize (upscale tiny scans)
        img = pp._resize_to_band(img)             # Resize (into OCR band)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  # Grayscale
        gray = pp._orientation_correct(gray)      # coarse rotation fix
        gray = pp._deskew(gray)                   # Deskew
        gray = pp._enhance(gray)                  # Denoise + CLAHE + Contrast + Sharpen
        if binarize:
            gray = cv2.adaptiveThreshold(         # Adaptive Threshold
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 31, 11,
            )
        return gray
    except Exception:  # noqa: BLE001 - any failure -> caller falls back to original
        return None


def preprocess_to_file(
    image_path: str | Path, out_dir: str | Path, *, binarize: bool = False
) -> str:
    """Preprocess ``image_path`` and write the result under ``out_dir``.

    Returns the path of the processed PNG, or the original path if
    preprocessing could not run (so the OCR step always receives a valid file).
    """
    processed = preprocess_image(image_path, binarize=binarize)
    if processed is None:
        return str(image_path)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    dest = out_path / f"{Path(image_path).stem}_processed.png"
    try:
        cv2.imwrite(str(dest), processed)
        return str(dest)
    except Exception:  # noqa: BLE001
        return str(image_path)
