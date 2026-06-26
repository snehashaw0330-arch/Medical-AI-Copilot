"""OCR History module — persistent storage of every prescription analysis.

Public surface:
* ``router``           — FastAPI APIRouter mounted at ``/history``.
* ``service``          — async persistence + business logic (CRUD, stats).
* ``save_ocr_record``  — convenience hook used by the OCR endpoint.
"""

from backend.history import service
from backend.history.router import router
from backend.history.service import save_ocr_record

__all__ = ["router", "service", "save_ocr_record"]
