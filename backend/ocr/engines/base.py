"""Common interface for every OCR engine in the ensemble.

Each engine returns a uniform ``EngineResult`` so the ensemble can compare them
on equal footing. Engines lazily import their heavy dependencies and report
``available=False`` (instead of crashing) when those deps aren't installed, so
the pipeline runs with whatever subset of engines exists on the machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OCRLine:
    text: str
    confidence: float | None = None  # 0..1
    box: list | None = None          # optional polygon/bbox


@dataclass
class EngineResult:
    engine: str
    text: str = ""
    lines: list[OCRLine] = field(default_factory=list)
    mean_confidence: float = 0.0     # 0..1
    available: bool = True
    error: str | None = None

    @property
    def is_empty(self) -> bool:
        return not any(c.isalpha() for c in self.text)


class OCREngine:
    """Base class. Subclasses set ``name`` and implement ``_run``."""

    name: str = "base"

    def __init__(self) -> None:
        self._ready: bool | None = None

    # -- lifecycle ---------------------------------------------------------
    def _load(self) -> None:
        """Import deps / build models. Raise to mark engine unavailable."""

    def available(self) -> bool:
        if self._ready is None:
            try:
                self._load()
                self._ready = True
            except Exception:  # noqa: BLE001
                self._ready = False
        return self._ready

    # -- inference ---------------------------------------------------------
    def _run(self, image_path: str) -> EngineResult:  # pragma: no cover
        raise NotImplementedError

    def run(self, image_path: str) -> EngineResult:
        if not self.available():
            return EngineResult(engine=self.name, available=False, error="not installed")
        try:
            res = self._run(image_path)
            res.engine = self.name
            if res.lines and not res.mean_confidence:
                confs = [l.confidence for l in res.lines if l.confidence is not None]
                res.mean_confidence = sum(confs) / len(confs) if confs else 0.0
            return res
        except Exception as exc:  # noqa: BLE001
            return EngineResult(engine=self.name, available=True, error=str(exc))


def gpu_available() -> bool:
    """True if a CUDA GPU is usable (for engines that can accelerate)."""
    try:
        import torch  # type: ignore

        return bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001
        return False
