"""DocTR engine — document text recognition with word confidences."""

from __future__ import annotations

from backend.ocr.engines.base import EngineResult, OCREngine, OCRLine


class DocTREngine(OCREngine):
    name = "doctr"

    def _load(self) -> None:
        from doctr.models import ocr_predictor  # type: ignore

        # pretrained detection + recognition; downloads weights on first use.
        self._predictor = ocr_predictor(pretrained=True)

    def _run(self, image_path: str) -> EngineResult:
        from doctr.io import DocumentFile  # type: ignore

        doc = DocumentFile.from_images(image_path)
        result = self._predictor(doc)
        lines: list[OCRLine] = []
        for page in result.pages:
            for block in page.blocks:
                for line in block.lines:
                    words = [(w.value, w.confidence) for w in line.words if w.value.strip()]
                    if not words:
                        continue
                    text = " ".join(w for w, _ in words)
                    conf = sum(c for _, c in words) / len(words)
                    lines.append(OCRLine(text=text, confidence=float(conf)))
        return EngineResult(engine=self.name, text="\n".join(l.text for l in lines), lines=lines)
