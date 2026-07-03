"""HTML rendering for medical reports.

Pure, dependency-light rendering (stdlib ``html.escape`` only — no Jinja/template
engine needed) that turns a :class:`ReportContent` into a **self-contained**,
print-friendly HTML document with inline CSS. The same HTML powers the ``.html``
export and can be opened/printed directly by the browser.

Everything is defensive: any missing section simply renders nothing, so a sparse
report (e.g. OCR-only, no clinical data) still produces a clean document.
"""

from __future__ import annotations

from html import escape

from backend.report_generator.schemas import ReportContent

# Risk-level → accent colour (mirrors the frontend badge palette).
_RISK_COLORS = {
    "critical": "#dc2626",
    "high": "#dc2626",
    "moderate": "#d97706",
    "low": "#2563eb",
}


def _pct(value: float) -> int:
    """0..1 → rounded percentage."""
    return round((value or 0.0) * 100)


def _section(title: str, body: str) -> str:
    """Wrap a section body in a titled block, or nothing when the body is empty."""
    if not body.strip():
        return ""
    return f'<section class="sec"><h2>{escape(title)}</h2>{body}</section>'


def _ul(items: list[str], cls: str = "") -> str:
    if not items:
        return ""
    lis = "".join(f"<li>{escape(str(i))}</li>" for i in items)
    return f'<ul class="{cls}">{lis}</ul>'


def _patient_html(c: ReportContent) -> str:
    p = c.patient
    rows = [
        ("Patient", p.name), ("Age", p.age), ("Gender", p.gender),
        ("Doctor", p.doctor), ("Hospital / Clinic", p.hospital),
        ("Date", p.date), ("Diagnosis", p.diagnosis),
    ]
    cells = "".join(
        f'<div class="kv"><span class="k">{escape(label)}</span>'
        f'<span class="v">{escape(str(val))}</span></div>'
        for label, val in rows if val
    )
    return f'<div class="grid">{cells}</div>' if cells else ""


def _medicines_html(c: ReportContent) -> str:
    if not c.medicines:
        return "<p class='muted'>No medicines were detected.</p>"
    blocks = []
    for i, m in enumerate(c.medicines, 1):
        name = escape(m.name or m.raw_text or f"Medicine {i}")
        conf = _pct(m.confidence)
        meta = " · ".join(
            f"{escape(lbl)}: {escape(str(v))}"
            for lbl, v in (("Dosage", m.dosage), ("Frequency", m.frequency),
                           ("Duration", m.duration)) if v
        )
        alts = ", ".join(
            f"{escape(str(cd.get('name', '')))} ({round(cd.get('score', 0))}%)"
            for cd in (m.candidates or [])[1:4] if cd.get("name")
        )
        parts = [
            f'<div class="med"><div class="med-head"><b>{i}. {name}</b>'
            f'<span class="badge">{conf}%</span></div>'
        ]
        if meta:
            parts.append(f'<p class="muted">{meta}</p>')
        if m.needs_review:
            parts.append('<p class="warn">⚠ Low confidence — verify manually.</p>')
        if alts:
            parts.append(f'<p class="muted"><b>Alternative matches:</b> {alts}</p>')
        if m.uses:
            parts.append(f'<p class="muted"><b>Uses:</b> {escape(", ".join(m.uses[:3]))}</p>')
        if m.side_effects:
            parts.append(f'<p class="muted"><b>Side effects:</b> {escape(", ".join(m.side_effects[:5]))}</p>')
        parts.append("</div>")
        blocks.append("".join(parts))
    return "".join(blocks)


def _disease_html(c: ReportContent) -> str:
    if not c.disease_prediction:
        return ""
    rows = []
    for d in c.disease_prediction:
        name = escape(str(d.get("disease", "")))
        conf = d.get("confidence")
        src = escape(str(d.get("source", "")))
        conf_txt = f" — {round(conf)}%" if d.get("source") == "model" and conf else ""
        expl = escape(str(d.get("explanation", "")))
        rows.append(f'<li><b>{name}</b>{conf_txt} <span class="tag">{src}</span>'
                    f'{f"<br><span class=muted>{expl}</span>" if expl else ""}</li>')
    return f'<ul>{"".join(rows)}</ul>'


def _clinical_html(c: ReportContent) -> str:
    cl = c.clinical or {}
    if not cl:
        return ""
    risk = str(cl.get("risk_level", "low")).lower()
    color = _RISK_COLORS.get(risk, "#2563eb")
    score = round(cl.get("risk_score", 0))
    conf = round(cl.get("confidence", 0))
    head = (
        f'<div class="risk" style="border-color:{color}">'
        f'<span class="risk-lvl" style="color:{color}">Risk: {escape(risk.upper())}</span>'
        f'<span class="muted">Risk score {score}/100 · Confidence {conf}%</span></div>'
    )
    summary = f'<p>{escape(str(cl.get("clinical_summary", "")))}</p>' if cl.get("clinical_summary") else ""

    red_flags = cl.get("red_flags", []) or []
    rf_html = ""
    if red_flags:
        items = []
        for f in red_flags:
            title = escape(str(f.get("title", "")))
            severity = escape(str(f.get("severity", "")))
            detail = f.get("detail")
            detail_html = f'<br><span class="muted">{escape(str(detail))}</span>' if detail else ""
            items.append(
                f'<li><b>{title}</b> <span class="tag">{severity}</span>{detail_html}</li>'
            )
        rf_html = f'<h3>Red Flag Alerts</h3><ul class="flags">{"".join(items)}</ul>'

    blocks = [
        ("Possible risks", cl.get("possible_risks")),
        ("Contraindications", cl.get("contraindications")),
        ("Recommended next steps", cl.get("recommended_next_steps")),
        ("Recommended lab tests", cl.get("recommended_lab_tests")),
        ("Follow-up suggestions", cl.get("follow_up")),
        ("Missing information", cl.get("missing_information")),
    ]
    extra = "".join(
        f"<h3>{escape(title)}</h3>{_ul(items)}"
        for title, items in blocks if items
    )
    return head + summary + rf_html + extra


def _interactions_html(c: ReportContent) -> str:
    di = c.drug_interactions or {}
    interactions = di.get("interactions", []) or []
    if not di:
        return ""
    overall = str(di.get("overall_risk", "none")).upper()
    head = f'<p><b>Overall interaction risk:</b> {escape(overall)}</p>'
    if di.get("summary"):
        head += f'<p class="muted">{escape(str(di["summary"]))}</p>'
    rows = []
    for it in interactions:
        meds = " + ".join(escape(str(x)) for x in (it.get("medicines") or []))
        sev = escape(str(it.get("severity", "")))
        color = _RISK_COLORS.get(str(it.get("severity", "")).lower(), "#6b7280")
        parts = [f'<div class="med"><div class="med-head"><b>{meds}</b>'
                 f'<span class="badge" style="background:{color}1a;color:{color}">{sev}</span></div>']
        for lbl, key in (("Risk", "clinical_risk"), ("Why", "explanation"),
                         ("Recommendation", "recommendation")):
            if it.get(key):
                parts.append(f'<p class="muted"><b>{lbl}:</b> {escape(str(it[key]))}</p>')
        parts.append("</div>")
        rows.append("".join(parts))
    body = head + "".join(rows)
    return body


def _rag_html(c: ReportContent) -> str:
    parts = []
    for d in c.rag_documents:
        parts.append(f'<div class="med"><p class="muted"><b>Source:</b> {escape(d.source)}</p>'
                     f'<p>{escape(d.text)}</p></div>')
    if c.sources:
        chips = "".join(f'<span class="tag">{escape(s)}</span>' for s in c.sources)
        parts.append(f'<p class="chips">{chips}</p>')
    return "".join(parts)


# CSS kept inline so the exported .html file is fully self-contained.
_CSS = """
* { box-sizing: border-box; }
body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
  color: #1f2937; margin: 0; padding: 0 0 48px; background: #f8fafc; }
.wrap { max-width: 820px; margin: 0 auto; background: #fff; }
.head { background: linear-gradient(135deg,#2563eb,#7c3aed); color:#fff; padding: 28px 32px; }
.head h1 { margin: 0; font-size: 24px; }
.head .sub { opacity: .9; font-size: 13px; margin-top: 4px; }
.head .ts { opacity: .85; font-size: 12px; margin-top: 8px; }
.body { padding: 24px 32px; }
.sec { margin: 22px 0; }
.sec h2 { font-size: 16px; color:#2563eb; border-bottom: 2px solid #eef2ff;
  padding-bottom: 6px; margin: 0 0 12px; }
.sec h3 { font-size: 13px; margin: 14px 0 6px; color:#374151; }
.grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px 20px; }
.kv { display: flex; justify-content: space-between; gap: 12px; font-size: 13px;
  border-bottom: 1px dashed #e5e7eb; padding: 5px 0; }
.kv .k { color:#6b7280; } .kv .v { font-weight: 600; text-align: right; }
.med { border: 1px solid #e5e7eb; border-radius: 10px; padding: 12px 14px; margin: 8px 0;
  background: #fafafa; }
.med-head { display:flex; justify-content: space-between; align-items:center; gap: 10px; }
.badge { background:#2563eb1a; color:#2563eb; border-radius: 999px; padding: 2px 10px;
  font-size: 12px; font-weight: 700; white-space: nowrap; }
.muted { color:#6b7280; font-size: 13px; margin: 5px 0; }
.warn { color:#d97706; font-size: 13px; margin: 5px 0; }
ul { margin: 4px 0; padding-left: 20px; } li { font-size: 13px; margin: 3px 0; }
.tag { background:#eef2ff; color:#4338ca; border-radius: 6px; padding: 1px 7px;
  font-size: 11px; margin-left: 4px; }
.risk { display:flex; justify-content: space-between; align-items:center;
  border:1px solid; border-radius: 10px; padding: 10px 14px; margin-bottom: 10px; }
.risk-lvl { font-weight: 800; font-size: 15px; }
.chips { margin-top: 8px; } .flags li { margin: 6px 0; }
pre { white-space: pre-wrap; background:#f1f5f9; border-radius: 10px; padding: 12px;
  font-size: 12px; color:#475569; overflow:auto; }
img.presc { max-width: 100%; border: 1px solid #e5e7eb; border-radius: 10px; }
.foot { border-top: 1px solid #e5e7eb; margin-top: 24px; padding-top: 12px;
  font-size: 11px; color:#9ca3af; }
"""


def render_html(content: ReportContent, *, image_data_uri: str | None = None) -> str:
    """Render a full, self-contained HTML document for one report."""
    c = content
    meta_bits = [b for b in (
        f"Provider: {escape(c.provider)}" if c.provider else "",
        f"Processing time: {c.processing_time}s" if c.processing_time else "",
        f"Overall confidence: {_pct(c.overall_confidence)}%",
    ) if b]

    image_html = ""
    if image_data_uri:
        image_html = f'<img class="presc" src="{image_data_uri}" alt="Prescription image" />'

    sections = [
        _section("Patient Information", _patient_html(c)),
        _section("Uploaded Prescription", image_html),
        _section("OCR Extracted Text",
                 f"<pre>{escape(c.raw_text)}</pre>" if c.raw_text else ""),
        _section("Medicines Detected", _medicines_html(c)),
        _section("Disease Prediction", _disease_html(c)),
        _section("Clinical Decision Summary", _clinical_html(c)),
        _section("Drug Interaction Analysis", _interactions_html(c)),
        _section("AI Recommendations", _ul(c.recommendations)),
        _section("Warnings", _ul(c.warnings)),
        _section("Contraindications", _ul(c.contraindications)),
        _section("Follow-up Suggestions", _ul(c.follow_up)),
        _section("Retrieved Knowledge & Sources", _rag_html(c)),
    ]

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{escape(c.title)}{f' — {escape(c.filename)}' if c.filename else ''}</title>
<style>{_CSS}</style></head>
<body><div class="wrap">
  <div class="head">
    <h1>MediSense · {escape(c.title)}</h1>
    <div class="sub">{escape(c.filename or 'Prescription analysis')}</div>
    <div class="ts">{escape(c.timestamp)} &nbsp;|&nbsp; {' · '.join(escape(m) for m in meta_bits)}</div>
  </div>
  <div class="body">
    {''.join(sections)}
    <div class="foot">{escape(c.disclaimer)}</div>
  </div>
</div></body></html>"""
