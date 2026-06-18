"""Run every available OCR engine and pick the best result.

Engines are instantiated once and cached (models load on first use). Only the
engines whose dependencies are installed participate; on this machine that may
be just EasyOCR (+ Tesseract), and the ensemble still works — it simply has
fewer candidates to choose from.
"""

from __future__ import annotations

from functools import lru_cache

from backend.ocr.confidence import select_best
from backend.ocr.engines.base import EngineResult, OCREngine
from backend.ocr.engines.doctr_engine import DocTREngine
from backend.ocr.engines.easyocr_engine import EasyOCREngine
from backend.ocr.engines.paddle_engine import PaddleOCREngine
from backend.ocr.engines.tesseract_engine import TesseractEngine
from backend.ocr.engines.trocr_engine import TrOCREngine

# Order = preference for tie-breaks / display only.
_ENGINE_CLASSES = [EasyOCREngine, PaddleOCREngine, DocTREngine, TrOCREngine, TesseractEngine]


@lru_cache(maxsize=1)
def get_engines() -> list[OCREngine]:
    """Instantiate engines whose dependencies are installed."""
    engines: list[OCREngine] = []
    for cls in _ENGINE_CLASSES:
        eng = cls()
        if eng.available():
            engines.append(eng)
    return engines


def available_engine_names() -> list[str]:
    return [e.name for e in get_engines()]


def run_ensemble(image_path: str, index) -> tuple[EngineResult, dict]:
    """Run all available engines, return (best_result, score_table)."""
    engines = get_engines()
    if not engines:
        raise RuntimeError(
            "No local OCR engine installed. Install at least one:\n"
            "  pip install easyocr            (recommended)\n"
            "  pip install pytesseract        (+ Tesseract binary)\n"
            "  pip install paddleocr paddlepaddle\n"
            "  pip install python-doctr[torch]\n"
            "  pip install transformers torch (TrOCR)"
        )
    results = [eng.run(image_path) for eng in engines]
    return select_best(results, index)
