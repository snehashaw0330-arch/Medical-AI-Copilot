"""Structured logging for the agent layer (Requirement: proper logging).

A thin wrapper so every agent/component logs under a consistent ``agents.*``
namespace with a run-id prefix, without each module re-configuring logging. The
application's root logging config still applies; this only guarantees a handler
exists and offers a small helper for run-scoped logging.
"""

from __future__ import annotations

import logging

_ROOT = "agents"
_configured = False


def _ensure_configured() -> None:
    global _configured
    if _configured:
        return
    logger = logging.getLogger(_ROOT)
    if not logger.handlers and not logging.getLogger().handlers:
        # Only add a handler if nothing upstream configured one, to avoid dupes.
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    _configured = True


def get_logger(name: str = "") -> logging.Logger:
    """Return a logger under the ``agents`` namespace."""
    _ensure_configured()
    return logging.getLogger(f"{_ROOT}.{name}" if name else _ROOT)


class RunLogger:
    """A logging adapter that prefixes every line with the run id."""

    def __init__(self, run_id: str, name: str = "") -> None:
        self._log = get_logger(name)
        self._run_id = run_id

    def _fmt(self, msg: str) -> str:
        return f"[run {self._run_id[:8]}] {msg}"

    def info(self, msg: str, *args) -> None:
        self._log.info(self._fmt(msg), *args)

    def warning(self, msg: str, *args) -> None:
        self._log.warning(self._fmt(msg), *args)

    def error(self, msg: str, *args) -> None:
        self._log.error(self._fmt(msg), *args)

    def exception(self, msg: str, *args) -> None:
        self._log.exception(self._fmt(msg), *args)

    def debug(self, msg: str, *args) -> None:
        self._log.debug(self._fmt(msg), *args)
