"""TrOCR engine — Microsoft's transformer OCR, best OSS for handwriting.

TrOCR is a *single-line* recognizer, so we segment the page into horizontal
text bands with a projection profile, then recognize each band. This is the
strongest freely-available handwriting model (trained on IAM); for medical
handwriting specifically, fine-tune it with ``engines/train_trocr.py``.

Heavy (torch + transformers); GPU strongly recommended. Lazily loaded.
"""

from __future__ import annotations

from backend.ocr.engines.base import EngineResult, OCREngine, OCRLine, gpu_available

# Default to the handwritten checkpoint. Override via OCR_TROCR_MODEL env.
import os

_DEFAULT_MODEL = os.getenv("OCR_TROCR_MODEL", "microsoft/trocr-base-handwritten")


class TrOCREngine(OCREngine):
    name = "trocr"

    def _load(self) -> None:
        import torch  # type: ignore
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel  # type: ignore

        self._torch = torch
        self._device = "cuda" if gpu_available() else "cpu"
        self._processor = TrOCRProcessor.from_pretrained(_DEFAULT_MODEL)
        self._model = VisionEncoderDecoderModel.from_pretrained(_DEFAULT_MODEL).to(self._device)
        self._model.eval()

    def _line_bands(self, image_path: str):
        """Split the page into horizontal text bands (numpy crops)."""
        import cv2
        import numpy as np

        img = cv2.imread(image_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        rowsum = thr.sum(axis=1)
        thresh = rowsum.max() * 0.04
        bands, start = [], None
        for y, v in enumerate(rowsum):
            if v > thresh and start is None:
                start = y
            elif v <= thresh and start is not None:
                if y - start > 12:  # ignore tiny specks
                    bands.append((max(0, start - 4), min(len(rowsum), y + 4)))
                start = None
        if start is not None:
            bands.append((start, len(rowsum)))
        if not bands:  # fall back to whole image as one line
            bands = [(0, img.shape[0])]
        return [img[a:b, :] for a, b in bands]

    def _run(self, image_path: str) -> EngineResult:
        from PIL import Image
        import cv2

        lines: list[OCRLine] = []
        for crop in self._line_bands(image_path):
            if crop.size == 0:
                continue
            pil = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
            pixel_values = self._processor(pil, return_tensors="pt").pixel_values.to(self._device)
            with self._torch.no_grad():
                ids = self._model.generate(pixel_values, max_new_tokens=64)
            text = self._processor.batch_decode(ids, skip_special_tokens=True)[0].strip()
            if text:
                # TrOCR doesn't emit confidences; use a neutral prior.
                lines.append(OCRLine(text=text, confidence=0.6))
        return EngineResult(engine=self.name, text="\n".join(l.text for l in lines), lines=lines)
