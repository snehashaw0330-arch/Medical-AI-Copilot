"""AI narrative generation for the Copilot (LLM-backed, offline-safe).

Produces the three free-text deliverables of the workflow — the **AI summary**,
**treatment suggestions** and **follow-up suggestions** — plus the **chat reply**.
It uses the project's provider-agnostic LLM layer (:func:`backend.llm.get_llm`),
which is offline-safe: with no cloud/local provider configured it transparently
falls back to a deterministic offline writer, so this module *always* returns
something useful and never raises.

All generation is grounded strictly in the structured facts the pipeline already
produced (medicines, interactions, disease hypotheses, evidence) — the system
prompt forbids inventing new clinical facts.
"""

from __future__ import annotations

import logging

from backend.config import settings
from backend.copilot.schemas import (
    DiseaseHypothesis,
    FollowUpSuggestion,
    TreatmentSuggestion,
)

logger = logging.getLogger("copilot.summary")

_SYSTEM = (
    "You are a careful clinical writing assistant embedded in a medical decision-"
    "support tool. Summarise ONLY the facts provided. Never invent medicines, "
    "diagnoses, doses or evidence. Be concise, neutral and safety-conscious, and "
    "always defer final judgement to a qualified clinician."
)


def _llm():
    """Return the configured LLM, or None when disabled/unavailable."""
    if not settings.COPILOT_USE_LLM:
        return None
    try:
        from backend.llm import get_llm

        llm = get_llm()
        return llm
    except Exception as exc:  # noqa: BLE001 — offline fallback below
        logger.debug("LLM unavailable, using offline writer: %s", exc)
        return None


def _facts_block(
    *, medicines: list[str], interactions: dict | None,
    diseases: list[DiseaseHypothesis], evidence_titles: list[str],
    patient: str,
) -> str:
    """Compose the grounded fact sheet handed to the model."""
    lines = [patient.strip()]
    if medicines:
        lines.append("Medicines: " + ", ".join(medicines))
    if interactions:
        inters = interactions.get("interactions") or []
        if inters:
            pretty = []
            for it in inters[:6]:
                pair = it.get("pair") or it.get("medicines") or []
                pretty.append(f"{' + '.join(map(str, pair))} ({it.get('severity', 'note')})")
            lines.append("Interactions: " + "; ".join(pretty))
        else:
            lines.append("Interactions: none found.")
    if diseases:
        lines.append("Disease hypotheses: " + "; ".join(
            f"{d.disease} ({d.confidence:.0f}%)" for d in diseases[:4]
        ))
    if evidence_titles:
        lines.append("Evidence: " + "; ".join(evidence_titles[:5]))
    return "\n".join(lines)


class SummaryEngine:
    """Generates the Copilot's AI narratives and chat replies."""

    async def summary(
        self, *, medicines, interactions, diseases, evidence_titles, patient,
    ) -> tuple[str, str]:
        """Return ``(summary_text, provider)`` for the AI summary section."""
        facts = _facts_block(
            medicines=medicines, interactions=interactions, diseases=diseases,
            evidence_titles=evidence_titles, patient=patient,
        )
        llm = _llm()
        if llm and llm.available():
            try:
                resp = await llm.acomplete(
                    system=_SYSTEM,
                    prompt=(
                        "Write a 3-5 sentence clinical summary of this case for the "
                        "treating clinician, grounded strictly in the facts:\n\n" + facts
                    ),
                    temperature=0.2, max_tokens=350,
                )
                return resp.text.strip(), resp.provider
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM summary failed, using offline writer: %s", exc)
        return self._offline_summary(medicines, interactions, diseases), "offline"

    async def treatment(
        self, *, medicines, interactions, diseases, patient,
    ) -> list[TreatmentSuggestion]:
        """Treatment suggestions (grounded, conservative, always non-empty)."""
        llm = _llm()
        facts = _facts_block(
            medicines=medicines, interactions=interactions, diseases=diseases,
            evidence_titles=[], patient=patient,
        )
        if llm and llm.available():
            try:
                resp = await llm.acomplete(
                    system=_SYSTEM,
                    prompt=(
                        "List 2-4 conservative, general treatment considerations for "
                        "this case as short bullet lines (no numbering). Each line: a "
                        "suggestion, then ' — ' then a brief rationale. Ground strictly "
                        "in the facts; do not prescribe specific new drugs/doses:\n\n" + facts
                    ),
                    temperature=0.3, max_tokens=350,
                )
                parsed = self._parse_bullets(resp.text)
                if parsed:
                    return [TreatmentSuggestion(suggestion=s, rationale=r) for s, r in parsed]
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM treatment failed, using offline writer: %s", exc)
        return self._offline_treatment(medicines, interactions, diseases)

    async def follow_up(
        self, *, diseases, interactions, risk_level,
    ) -> list[FollowUpSuggestion]:
        """Follow-up / safety-net suggestions (deterministic, always non-empty)."""
        out: list[FollowUpSuggestion] = []
        if risk_level in ("critical", "high"):
            out.append(FollowUpSuggestion(
                action="Arrange prompt clinical review",
                timeframe="within 24-48 hours" if risk_level == "high" else "immediately",
                reason=f"Overall risk was assessed as {risk_level}.",
            ))
        else:
            out.append(FollowUpSuggestion(
                action="Routine review",
                timeframe="within 1-2 weeks",
                reason="Reassess response to treatment and any new symptoms.",
            ))
        if diseases:
            out.append(FollowUpSuggestion(
                action=f"Reassess the working diagnosis of {diseases[0].disease}",
                timeframe="at the next visit",
                reason="Confirm the diagnosis holds and treatment is effective.",
            ))
        if interactions and (interactions.get("interactions") or []):
            out.append(FollowUpSuggestion(
                action="Monitor for adverse effects of the interacting medicines",
                timeframe="ongoing",
                reason="A drug-drug interaction was flagged for this medication list.",
            ))
        out.append(FollowUpSuggestion(
            action="Return sooner if symptoms worsen or new red-flags appear",
            timeframe="safety-net",
            reason="Standard safety-netting advice.",
        ))
        return out

    async def chat(self, *, system_context: str, transcript: str, question: str) -> tuple[str, str]:
        """Answer a clinician question grounded in the session context."""
        llm = _llm()
        prompt = (
            f"Patient context:\n{system_context}\n\n"
            f"Recent conversation:\n{transcript}\n\n"
            f"Clinician question: {question}\n\n"
            "Answer helpfully and concisely, grounded in the context above. If the "
            "answer is not supported by the context, say so and suggest what to check."
        )
        if llm and llm.available():
            try:
                resp = await llm.acomplete(system=_SYSTEM, prompt=prompt,
                                           temperature=0.3, max_tokens=500)
                return resp.text.strip(), resp.provider
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM chat failed, using offline reply: %s", exc)
        return self._offline_chat(system_context, question), "offline"

    # -- offline deterministic writers ------------------------------------
    def _offline_summary(self, medicines, interactions, diseases) -> str:
        bits: list[str] = []
        if diseases:
            top = diseases[0]
            bits.append(
                f"The leading consideration is {top.disease} "
                f"(~{top.confidence:.0f}% from the symptom pattern)."
            )
        if medicines:
            bits.append(f"The regimen under review includes {', '.join(medicines[:8])}.")
        if interactions and (interactions.get("interactions") or []):
            n = len(interactions["interactions"])
            bits.append(f"{n} potential drug interaction(s) were flagged and should be reconciled.")
        elif medicines:
            bits.append("No drug-drug interactions were detected in the current list.")
        bits.append("All findings require confirmation by a qualified clinician.")
        return " ".join(bits) if bits else (
            "Insufficient information was supplied to summarise this case."
        )

    def _offline_treatment(self, medicines, interactions, diseases) -> list[TreatmentSuggestion]:
        out: list[TreatmentSuggestion] = []
        if interactions and (interactions.get("interactions") or []):
            out.append(TreatmentSuggestion(
                suggestion="Reconcile the medication list and address flagged interactions",
                rationale="One or more drug-drug interactions were detected.",
                caution="Do not stop or change therapy without clinician review.",
            ))
        if diseases:
            out.append(TreatmentSuggestion(
                suggestion=f"Direct management toward the leading hypothesis ({diseases[0].disease})",
                rationale="It best fits the reported symptoms.",
                caution="Confirm the diagnosis before committing to a plan.",
            ))
        if medicines and not out:
            out.append(TreatmentSuggestion(
                suggestion="Review current medicines for appropriateness and dosing",
                rationale="A regimen was provided without a specific active problem.",
            ))
        out.append(TreatmentSuggestion(
            suggestion="Verify every suggestion with a qualified clinician",
            rationale="This is an educational decision-support aid only.",
        ))
        return out

    def _offline_chat(self, context: str, question: str) -> str:
        return (
            "Based on the current session context:\n\n"
            f"{context}\n\n"
            f"Regarding your question — \"{question}\" — I can only reason over the "
            "information gathered so far in this session. Please review the analysis "
            "panels for specifics, and confirm any decision with a qualified clinician."
        )

    @staticmethod
    def _parse_bullets(text: str) -> list[tuple[str, str]]:
        """Parse ' - suggestion — rationale' style lines into pairs."""
        pairs: list[tuple[str, str]] = []
        for raw in text.splitlines():
            line = raw.strip().lstrip("-*•0123456789. ").strip()
            if not line:
                continue
            for sep in (" — ", " - ", ": "):
                if sep in line:
                    s, r = line.split(sep, 1)
                    pairs.append((s.strip(), r.strip()))
                    break
            else:
                pairs.append((line, ""))
        return pairs[:4]


_ENGINE: SummaryEngine | None = None


def get_engine() -> SummaryEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = SummaryEngine()
    return _ENGINE
