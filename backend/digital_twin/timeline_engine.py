"""Timeline engine — build the patient's chronological health journey.

Pure. Turns the encounter series into UI-ready :class:`TimelineEvent`s: one event
per analysed report, plus derived milestones — the first appearance of a new
medicine and any high/critical-risk visit — so the timeline highlights what
changed, not just that a visit happened. Newest first.
"""

from __future__ import annotations

from backend.digital_twin.schemas import TimelineEvent

_HIGH_RISK = {"high", "critical"}


def build(encounters: list[dict]) -> list[TimelineEvent]:
    """Return timeline events (newest first) derived from the encounters."""
    events: list[TimelineEvent] = []
    seen_medicines: set[str] = set()

    for i, enc in enumerate(encounters):
        ts = enc["created_at"]
        rid = enc.get("id", str(i))
        meds = enc.get("medicine_names", [])
        med_count = len(meds)
        top_disease = enc.get("top_disease")
        risk_level = (enc.get("risk_level") or None)
        confidence = enc.get("overall_confidence")

        # Primary "report" event.
        desc_bits = []
        if med_count:
            desc_bits.append(f"{med_count} medicine(s)")
        if top_disease:
            desc_bits.append(f"condition: {top_disease}")
        if enc.get("interaction_count"):
            desc_bits.append(f"{enc['interaction_count']} interaction(s)")
        events.append(TimelineEvent(
            id=f"{rid}-report", timestamp=ts, type="report",
            title="Prescription analysed",
            description="; ".join(desc_bits) or "Analysis recorded.",
            risk_level=risk_level, confidence=confidence,
            meta={"report_id": rid, "medicine_count": med_count},
        ))

        # New-medicine milestones.
        new_meds = [m for m in meds if m and m not in seen_medicines]
        for m in new_meds:
            events.append(TimelineEvent(
                id=f"{rid}-med-{m}", timestamp=ts, type="new_medicine",
                title=f"Started {m.title()}",
                description="First appearance in the patient's history.",
                meta={"medicine": m},
            ))
        seen_medicines.update(m for m in meds if m)

        # High-risk milestone.
        if risk_level in _HIGH_RISK:
            events.append(TimelineEvent(
                id=f"{rid}-risk", timestamp=ts, type="high_risk",
                title=f"{risk_level.title()} clinical risk flagged",
                description=(enc.get("clinical_summary") or "")[:160]
                or "A high-risk clinical state was recorded.",
                risk_level=risk_level,
                meta={"report_id": rid},
            ))

    # Newest first; stable within the same timestamp by keeping insertion order.
    events.sort(key=lambda e: e.timestamp, reverse=True)
    return events
