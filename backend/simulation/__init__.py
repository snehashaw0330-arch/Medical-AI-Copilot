"""AI Medical Simulation Engine.

A "what-if" engine that lets a clinician simulate treatment and patient changes —
dose changes, medicine replace/remove/add, and patient changes (age, weight,
pregnancy, renal or hepatic impairment, allergies) — and see the projected drug
interactions, disease risk, clinical recommendations, treatment suggestions, side
effects, contraindications and RAG evidence, with a confidence breakdown, BEFORE
making a decision. Multiple scenarios can be compared against the baseline (and
against each other).

It is purely additive: it only *reads* from the existing subsystems (OCR, disease,
drug-interactions, clinical-decision, RAG, report-generator) and changes none.

Public surface:

* :data:`router`         — FastAPI router (mounted at ``/simulation``)
* :func:`run_simulation` — coroutine to run a simulation
* :func:`get_service`    — the process-wide :class:`SimulationService`
"""

from backend.simulation.router import router
from backend.simulation.service import get_service, run_simulation

__all__ = ["router", "run_simulation", "get_service"]
