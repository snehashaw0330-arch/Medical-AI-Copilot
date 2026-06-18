"""EasyOCR engine — solid general-purpose detector+recognizer (CPU/GPU)."""

from __future__ import annotations

from backend.ocr.engines.base import EngineResult, OCREngine, OCRLine, gpu_available


class EasyOCREngine(OCREngine):
    name = "easyocr"

    def _load(self) -> None:
        import easyocr  # type: ignore

        self._reader = easyocr.Reader(["en"], gpu=gpu_available(), verbose=False)

    def _run(self, image_path: str) -> EngineResult:
        # detail=1 -> [ (bbox, text, confidence), ... ]
        results = self._reader.readtext(image_path)
        lines = [
            OCRLine(text=(t or "").strip(), confidence=float(c), box=box)
            for box, t, c in results
            if (t or "").strip()
        ]
        text = "\n".join(l.text for l in lines)
        return EngineResult(engine=self.name, text=text, lines=lines)
