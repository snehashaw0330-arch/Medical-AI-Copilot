"""Server-side PDF rendering for medical reports.

Uses **reportlab** (pure-Python, no system dependencies) to render a
:class:`ReportContent` into a professional, multi-page PDF. reportlab is imported
lazily so the rest of the module — JSON and HTML export — works even when it is
not installed; in that case :func:`render_pdf` raises a clear, actionable error
that the router turns into a ``503`` (the same graceful-degradation pattern used
by the OCR providers and the RAG LLM layer).
"""

from __future__ import annotations

import logging
from io import BytesIO
from xml.sax.saxutils import escape

from backend.report_generator.schemas import ReportContent

logger = logging.getLogger("report_generator")

# Brand palette (mirrors the frontend).
_PRIMARY = "#2563eb"
_RISK_COLORS = {
    "critical": "#dc2626", "high": "#dc2626",
    "moderate": "#d97706", "low": "#2563eb",
}

_REPORTLAB_HINT = (
    "PDF export requires the 'reportlab' package. Install it with "
    "'pip install reportlab' (it is listed in backend/requirements.txt). "
    "JSON and HTML export work without it."
)


def reportlab_available() -> bool:
    """True when reportlab can be imported (PDF export is possible)."""
    try:
        import reportlab  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _pct(value: float) -> int:
    return round((value or 0.0) * 100)


def render_pdf(content: ReportContent, *, image_path: str | None = None) -> bytes:
    """Render one report to PDF bytes.

    Raises
    ------
    RuntimeError
        If reportlab is not installed (caller surfaces an actionable 503).
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            HRFlowable,
            Image,
            ListFlowable,
            ListItem,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(_REPORTLAB_HINT) from exc

    c = content
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm,
        leftMargin=16 * mm, rightMargin=16 * mm,
        title=c.title, author="MediSense",
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1x", parent=styles["Heading1"], fontSize=15,
                        textColor=colors.HexColor(_PRIMARY), spaceBefore=10, spaceAfter=6)
    h2 = ParagraphStyle("h2x", parent=styles["Heading2"], fontSize=11,
                        textColor=colors.HexColor("#374151"), spaceBefore=8, spaceAfter=3)
    body = ParagraphStyle("bodyx", parent=styles["BodyText"], fontSize=9.5, leading=13)
    muted = ParagraphStyle("mutedx", parent=body, textColor=colors.HexColor("#6b7280"))
    small = ParagraphStyle("smallx", parent=body, fontSize=8.5,
                           textColor=colors.HexColor("#9ca3af"))

    story: list = []

    def para(text: str, style=body) -> None:
        story.append(Paragraph(escape(str(text)), style))

    def heading(text: str) -> None:
        story.append(Paragraph(escape(text), h1))
        story.append(HRFlowable(width="100%", thickness=0.8,
                                color=colors.HexColor("#e5e7eb"), spaceAfter=5))

    def bullets(items: list[str]) -> None:
        if not items:
            return
        story.append(ListFlowable(
            [ListItem(Paragraph(escape(str(i)), body), leftIndent=8) for i in items],
            bulletType="bullet", start="•", leftIndent=10,
        ))

    # ---- Title banner ----
    banner = Table(
        [[Paragraph(f'<font color="white"><b>MediSense</b> · {escape(c.title)}</font>',
                    ParagraphStyle("bn", parent=body, fontSize=15, textColor=colors.white)),
          Paragraph(f'<font color="white">{escape(c.timestamp)}</font>',
                    ParagraphStyle("bnr", parent=small, textColor=colors.white, alignment=2))]],
        colWidths=[doc.width * 0.62, doc.width * 0.38],
    )
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(_PRIMARY)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(banner)
    story.append(Spacer(1, 6))
    meta = " · ".join(b for b in (
        f"File: {c.filename}" if c.filename else "",
        f"Provider: {c.provider}" if c.provider else "",
        f"Overall confidence: {_pct(c.overall_confidence)}%",
        f"Processing time: {c.processing_time}s" if c.processing_time else "",
    ) if b)
    para(meta, small)
    story.append(Spacer(1, 6))

    # ---- Patient information ----
    p = c.patient
    prows = [(lbl, val) for lbl, val in (
        ("Patient", p.name), ("Age", p.age), ("Gender", p.gender),
        ("Doctor", p.doctor), ("Hospital", p.hospital), ("Date", p.date),
        ("Diagnosis", p.diagnosis)) if val]
    if prows:
        heading("Patient Information")
        data = [[Paragraph(f"<b>{escape(k)}</b>", muted), Paragraph(escape(str(v)), body)]
                for k, v in prows]
        t = Table(data, colWidths=[doc.width * 0.28, doc.width * 0.72])
        t.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#eef2f7")),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)

    # ---- Prescription image ----
    if image_path:
        try:
            from reportlab.lib.utils import ImageReader

            ir = ImageReader(image_path)
            iw, ih = ir.getSize()
            max_w = doc.width * 0.55
            w = min(max_w, iw)
            h = (ih / iw) * w
            max_h = 90 * mm
            if h > max_h:
                h = max_h
                w = (iw / ih) * h
            heading("Uploaded Prescription")
            story.append(Image(image_path, width=w, height=h))
        except Exception as exc:  # noqa: BLE001 — image is best-effort
            logger.debug("Skipped embedding image in PDF: %s", exc)

    # ---- OCR text ----
    if c.raw_text:
        heading("OCR Extracted Text")
        para(c.raw_text, muted)

    # ---- Medicines ----
    heading("Medicines Detected")
    if not c.medicines:
        para("No medicines were detected.", muted)
    for i, m in enumerate(c.medicines, 1):
        name = m.name or m.raw_text or f"Medicine {i}"
        para(f"<b>{escape(name)}</b> — {_pct(m.confidence)}% confidence", body)
        meta_line = " · ".join(
            f"{lbl}: {v}" for lbl, v in
            (("Dosage", m.dosage), ("Frequency", m.frequency), ("Duration", m.duration)) if v)
        if meta_line:
            para(meta_line, muted)
        alts = ", ".join(
            f"{cd.get('name', '')} ({round(cd.get('score', 0))}%)"
            for cd in (m.candidates or [])[1:4] if cd.get("name"))
        if alts:
            para(f"Alternative matches: {alts}", muted)
        if m.uses:
            para(f"Uses: {', '.join(m.uses[:3])}", muted)
        if m.side_effects:
            para(f"Side effects: {', '.join(m.side_effects[:5])}", muted)
        story.append(Spacer(1, 3))

    # ---- Disease prediction ----
    if c.disease_prediction:
        heading("Disease Prediction")
        for d in c.disease_prediction:
            conf = d.get("confidence")
            tail = f" — {round(conf)}%" if d.get("source") == "model" and conf else ""
            para(f"<b>{escape(str(d.get('disease', '')))}</b>{tail} "
                 f"[{escape(str(d.get('source', '')))}]", body)
            if d.get("explanation"):
                para(str(d["explanation"]), muted)

    # ---- Clinical decision summary ----
    cl = c.clinical or {}
    if cl:
        heading("Clinical Decision Summary")
        risk = str(cl.get("risk_level", "low")).lower()
        color = _RISK_COLORS.get(risk, _PRIMARY)
        para(f'<font color="{color}"><b>Risk level: {escape(risk.upper())}</b></font> · '
             f'score {round(cl.get("risk_score", 0))}/100 · '
             f'confidence {round(cl.get("confidence", 0))}%', body)
        if cl.get("clinical_summary"):
            para(cl["clinical_summary"], body)
        red_flags = cl.get("red_flags", []) or []
        if red_flags:
            story.append(Paragraph("Red Flag Alerts", h2))
            bullets([f"{f.get('title', '')} ({f.get('severity', '')})"
                     + (f" — {f.get('detail', '')}" if f.get("detail") else "")
                     for f in red_flags])
        for title, key in (("Possible Risks", "possible_risks"),
                           ("Contraindications", "contraindications"),
                           ("Recommended Next Steps", "recommended_next_steps"),
                           ("Recommended Lab Tests", "recommended_lab_tests"),
                           ("Follow-up Suggestions", "follow_up"),
                           ("Missing Information", "missing_information")):
            if cl.get(key):
                story.append(Paragraph(title, h2))
                bullets(cl[key])

    # ---- Drug interactions ----
    di = c.drug_interactions or {}
    if di:
        heading("Drug Interaction Analysis")
        para(f"Overall risk: <b>{escape(str(di.get('overall_risk', 'none')).upper())}</b>", body)
        if di.get("summary"):
            para(di["summary"], muted)
        for it in di.get("interactions", []) or []:
            meds = " + ".join(str(x) for x in (it.get("medicines") or []))
            para(f"<b>{escape(meds)}</b> — {escape(str(it.get('severity', '')))}", body)
            for lbl, key in (("Risk", "clinical_risk"), ("Why", "explanation"),
                             ("Recommendation", "recommendation")):
                if it.get(key):
                    para(f"{lbl}: {it[key]}", muted)

    # ---- AI recommendations / warnings / follow-up ----
    for title, items in (("AI Recommendations", c.recommendations),
                         ("Warnings", c.warnings),
                         ("Contraindications", c.contraindications),
                         ("Follow-up Suggestions", c.follow_up)):
        if items:
            heading(title)
            bullets(items)

    # ---- RAG + sources ----
    if c.rag_documents or c.sources:
        heading("Retrieved Knowledge & Sources")
        for d in c.rag_documents:
            if d.source:
                para(f"<b>Source:</b> {escape(d.source)}", muted)
            if d.text:
                para(d.text, muted)
        if c.sources:
            para("Sources used: " + ", ".join(c.sources), muted)

    # ---- Disclaimer ----
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e5e7eb")))
    story.append(Spacer(1, 4))
    para(c.disclaimer, small)

    doc.build(story)
    return buf.getvalue()
