"""Tesseract engine via pytesseract. Best on clean/printed text.

Uses ``image_to_data`` to recover per-word confidences, grouped into lines.
Needs the Tesseract binary installed in addition to the pytesseract package.
"""

from __future__ import annotations

from backend.ocr.engines.base import EngineResult, OCREngine, OCRLine


class TesseractEngine(OCREngine):
    name = "tesseract"

    def _load(self) -> None:
        import pytesseract  # type: ignore

        self._pt = pytesseract
        # Will raise if the binary is missing -> engine marked unavailable.
        pytesseract.get_tesseract_version()

    def _run(self, image_path: str) -> EngineResult:
        from PIL import Image

        data = self._pt.image_to_data(
            Image.open(image_path), output_type=self._pt.Output.DICT
        )
        # Group words by (block, par, line).
        groups: dict[tuple, list[tuple[str, float]]] = {}
        for i, word in enumerate(data["text"]):
            w = (word or "").strip()
            if not w:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            conf = float(data["conf"][i])
            groups.setdefault(key, []).append((w, conf if conf >= 0 else 0.0))

        lines: list[OCRLine] = []
        for key in sorted(groups):
            words = groups[key]
            text = " ".join(w for w, _ in words)
            confs = [c for _, c in words]
            lines.append(OCRLine(text=text, confidence=(sum(confs) / len(confs)) / 100.0))

        return EngineResult(engine=self.name, text="\n".join(l.text for l in lines), lines=lines)
