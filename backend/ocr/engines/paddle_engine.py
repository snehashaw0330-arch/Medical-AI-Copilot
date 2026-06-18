"""PaddleOCR engine — strong detector + angle classifier, good on photos."""

from __future__ import annotations

from backend.ocr.engines.base import EngineResult, OCREngine, OCRLine, gpu_available


class PaddleOCREngine(OCREngine):
    name = "paddleocr"

    def _load(self) -> None:
        from paddleocr import PaddleOCR  # type: ignore

        self._ocr = PaddleOCR(
            use_angle_cls=True, lang="en", show_log=False, use_gpu=gpu_available()
        )

    def _run(self, image_path: str) -> EngineResult:
        result = self._ocr.ocr(image_path, cls=True)
        lines: list[OCRLine] = []
        # PaddleOCR returns [[ [box, (text, conf)], ... ]]
        page = result[0] if result else []
        for entry in page or []:
            box, (text, conf) = entry[0], entry[1]
            t = (text or "").strip()
            if t:
                lines.append(OCRLine(text=t, confidence=float(conf), box=box))
        return EngineResult(engine=self.name, text="\n".join(l.text for l in lines), lines=lines)
