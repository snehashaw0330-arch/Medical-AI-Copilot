# 🩺 Medical AI Assistant

An AI-powered healthcare assistant built with **FastAPI**, **React (Vite)**, and **Machine Learning** to help users with disease prediction, handwritten prescription OCR, medicine information lookup, and an intelligent medical chatbot.

## ✨ Features

- 🤖 Multi-Agent AI Medical Copilot — nine specialised agents collaborate over an event-driven pipeline with a live monitor, shared memory & a provider-agnostic LLM layer
- 🧠 Disease Prediction using Machine Learning
- 🩺 Symptom Checker & Triage — categorized symptom picker, four-level urgency, specialist routing & RAG-backed evidence
- 📄 Handwritten Prescription OCR
- 🔎 AI Image Quality Assessment (pre-OCR)
- 🗂️ Prescription OCR History (persistent, searchable)
- ⚠️ Drug Interaction Analysis (auto-run after OCR; severity, warnings & recommendations)
- 🧠 Clinical Decision Support (CDSS) — risk-graded clinical reports fusing OCR, disease prediction, interactions & RAG
- 📑 Medical Report Generator — comprehensive reports auto-generated after OCR, exportable as PDF / JSON / HTML
- 🛡️ Prescription Validation — auto-run after OCR; scores prescription safety (0–100) and flags duplicates, missing dosing info, unsafe abbreviations & prescription errors
- 💊 Medicine Information Search
- ✨ Medicine Alternatives & Recommendations — generic equivalents, substitute brands, similar medicines, drug info & RAG evidence (auto-runs after OCR)
- 🤖 AI Medical Chat Assistant
- 📊 Confidence-based Predictions
- 📑 Downloadable OCR Reports (PDF & JSON)
- 🌙 Modern Responsive UI

---

## 🛠️ Tech Stack

### Frontend
- React
- Vite
- JavaScript
- Axios
- React Router

### Backend
- FastAPI
- Python
- EasyOCR
- OpenCV
- RapidFuzz
- Scikit-learn
- Pandas
- Joblib
- SQLAlchemy 2.0 (async) + aiosqlite — SQLite now, PostgreSQL-ready

---

## 📁 Project Structure

```
medical-ai-assistant/
│
├── backend/
│   ├── agents/         # Multi-Agent Copilot (manager, engine, registry, event bus, memory, 9 agents)
│   ├── llm/            # Provider-agnostic LLM layer (base + factory + OpenAI/Gemini/Claude/Ollama/DeepSeek/offline)
│   ├── ocr/            # OCR pipeline + image quality assessment
│   ├── history/        # OCR History module (models, schemas, service, router)
│   ├── drug_interactions/  # Drug Interaction Analysis (models, schemas, service, router, utils)
│   ├── clinical_decision/  # Clinical Decision Support (rules_engine, risk_analyzer, recommendation_engine, service, ...)
│   ├── report_generator/   # Medical Report Generator (report_builder, templates, pdf_generator, service, ...)
│   ├── prescription_validation/  # Prescription Validation (rules, validator, service, router, models, schemas)
│   ├── symptom_checker/    # Symptom Checker & Triage (symptom_matcher, triage_engine, service, router, models, schemas)
│   ├── medicine_recommendation/  # Medicine Alternatives & Recommendations (alternative_finder, recommendation_engine, service, router, models, schemas)
│   ├── disease/        # Disease prediction
│   ├── rag/            # Retrieval-augmented Q&A
│   └── app.py          # FastAPI app — wires all routers
├── frontend/
├── disease-prediction/
├── datasets/
├── prescription-ocr/
└── README.md
```

---

## 🚀 Installation

### Clone Repository

```bash
git clone https://github.com/snehashaw0330-arch/medical-ai-assistant.git
cd medical-ai-assistant
```

### Backend

```bash
python -m venv venv
```

Windows

```bash
venv\Scripts\activate
```

Install dependencies

```bash
pip install -r backend/requirements.txt
```

Run Backend

```bash
uvicorn backend.app:app --reload
```

---

### Frontend

```bash
cd frontend
npm install
npm run dev
```

---

## 📡 API Documentation

After starting the backend:

```
http://127.0.0.1:8000/docs
```

---

## 📸 Modules

- Multi-Agent AI Medical Copilot
- Disease Prediction
- Symptom Checker & Triage
- Prescription OCR
- Image Quality Assessment
- Prescription OCR History
- Drug Interaction Analysis
- Clinical Decision Support (CDSS)
- Medical Report Generator
- Prescription Validation
- Medicine Search
- Medicine Alternatives & Recommendations
- AI Chat Assistant

---

## 🗂️ Prescription OCR History

Every prescription analysed by the OCR pipeline is **automatically saved** to a
persistent store, so users can revisit, search, re-download and audit past
analyses. The OCR endpoint records each run (success **or** failure) without any
extra user action.

### What is stored

For each analysis: a unique id, timestamp, uploaded image (a retained copy),
raw OCR text, detected medicines (with drug info), overall confidence, OCR
engine used, processing time, and status (`success` / `failed`).

### Backend module — `backend/history/`

| File | Responsibility |
|------|----------------|
| `models.py`  | SQLAlchemy ORM model (`OCRRecord`) + portable column types (works on SQLite **and** PostgreSQL). |
| `schemas.py` | Pydantic response models — the API/frontend contract (list item, detail, page, stats). |
| `service.py` | The only layer that touches the DB: async engine/session setup, CRUD, filtering, pagination, statistics, and image retention. |
| `router.py`  | Async FastAPI routes under `/history`, delegating to the service with logging + exception handling. |

### Storage & database

- **Default:** a local SQLite file (`backend/history/history.db`) via the async
  `aiosqlite` driver. Retained images live in `backend/history/images/`.
- **PostgreSQL (production):** set one environment variable — no code changes:

  ```bash
  export DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/medisense"
  pip install asyncpg
  ```

### API endpoints

| Method & path | Description |
|---------------|-------------|
| `GET /history` | Paginated list. Query params: `q`, `medicine`, `status`, `date_from`, `date_to`, `sort` (`newest`/`oldest`/`confidence`), `page`, `page_size`. |
| `GET /history/stats` | Aggregate stats: total / successful / failed analyses, average confidence, average processing time. |
| `GET /history/medicines` | Distinct medicine names (powers the filter dropdown). |
| `GET /history/{id}` | Full record (image flag, OCR text, medicines, drug info, fields, notes). |
| `GET /history/{id}/image` | Serves the retained prescription image. |
| `DELETE /history/{id}` | Delete one record (and its image). |
| `DELETE /history` | Clear the entire history. |

### Frontend

A new **Prescription History** sidebar page (`/history`):

- Statistics cards (total / successful / failed / avg. confidence / avg. time)
- Search, filter by medicine, filter by date range, sort by newest/oldest/confidence
- Pagination
- Click a record to view the full report (image, OCR text, medicines + drug info, confidence, processing time)
- Per-record actions: **View**, **Download PDF**, **Download JSON**, **Delete**
- The PDF generator is shared with the OCR page via `frontend/src/lib/pdf.js` (no duplicated logic).

### How the workflow operates

1. User analyses a prescription on the **Prescription OCR** page → `POST /ocr/extract-prescription`.
2. The OCR endpoint runs the pipeline, times it, and calls `history.save_ocr_record(...)`
   — a **best-effort** hook that can never break the OCR response. It copies the
   image into the history store and writes one row (success or failure).
3. The **Prescription History** page calls `GET /history` (+ `/stats`, `/medicines`)
   and renders the cards, filters and list.
4. Opening a record fetches `GET /history/{id}`; PDF/JSON exports reuse that detail,
   and the image is loaded from `GET /history/{id}/image`.
5. Deleting a record (or clearing all) removes the row **and** its retained image.

---

## ⚠️ Drug Interaction Analysis

A production-ready module that checks a set of medicines for **drug–drug
interactions** and **per-drug clinical warnings**. It runs **automatically after
OCR** whenever two or more medicines are detected, and can be re-run on demand
against an edited medicine list.

### What it analyses

- **Drug–drug interactions** with a five-level severity scale: `none`, `low`,
  `moderate`, `high`, `critical`
- Per interaction: **medicines involved**, **severity**, **clinical risk**,
  **explanation**, **recommendation**, **clinical notes**
- **Per-drug warnings:** contraindications, food, alcohol, pregnancy,
  breastfeeding, kidney, liver and age restrictions
- **Overall risk**, severity tally, de-duplicated recommendations
- Optional **RAG enrichment** — extra context retrieved from the medical
  knowledge base when available (degrades gracefully when it is not)

### Backend module — `backend/drug_interactions/`

| File | Responsibility |
|------|----------------|
| `schemas.py` | Pydantic contract: `Severity` enum, `DrugDrugInteraction`, `MedicineWarnings`, `InteractionReport`, request + history models. |
| `utils.py`   | Pure helpers — severity ranking, name normalisation (reuses the OCR normaliser), summary/recommendation composition. No I/O. |
| `models.py`  | SQLAlchemy ORM model (`InteractionRecord`) with portable column types (SQLite **and** PostgreSQL). |
| `service.py` | The brain: a **source-agnostic dataset loader** (`InteractionDataSource` → JSON / CSV / SQLite, plus a documented `RemoteAPIDataSource` stub for OpenFDA / RxNorm / DrugBank), fuzzy name resolution, the interaction + warning analysis engine, RAG enrichment, and async persistence. |
| `router.py`  | Async FastAPI routes under `/interactions`, with logging + exception handling. |
| `__init__.py`| Public surface: `router`, `analyze_medicines`, `get_service`. |

### Dataset — `datasets/drug_interactions/interactions.json`

A curated, **educational** knowledge base of common interactions and per-drug
warning profiles (with drug aliases for matching). The loader infers the backend
from the file extension, so the same `INTERACTIONS_DATASET` setting can point at
a `.json`, `.csv` or `.sqlite` file with **no code changes**.

### API endpoints

| Method & path | Description |
|---------------|-------------|
| `POST /interactions/check` | Analyse a list of medicine names. Body: `{ medicines, include_rag, persist }`. Returns the full `InteractionReport`. |
| `GET /interactions/history` | Paginated list of past analyses (`page`, `page_size`). |
| `GET /interactions/{id}` | Full stored report for one analysis. |
| `GET /interactions/health` | Knowledge-base readiness + size (ops/debug). |
| `DELETE /interactions/history` | Clear stored analyses. |

### Frontend

- **Automatic:** when the OCR pipeline detects ≥2 medicines, the backend attaches
  a `drug_interactions` report to the OCR result. The **Prescription OCR** page
  renders a new **Drug Interaction Report** card: interaction summary, overall
  risk level, **color-coded severity badges**, medicines involved, recommendations
  and collapsible per-drug warnings.
- **On demand:** a **Re-check interactions** button re-analyses the edited medicine
  list via `POST /interactions/check`.
- Reusable component: `frontend/src/ui/DrugInteractionReport.jsx`.

### How the workflow operates

1. User analyses a prescription → `POST /ocr/extract-prescription`.
2. After OCR, `_attach_interactions(...)` runs (best-effort, can **never** break
   OCR). If ≥2 medicines are found it calls `drug_interactions.analyze_medicines(...)`
   and attaches the report inline; the OCR history captures it too.
3. The OCR results page renders the **Drug Interaction Report** card.
4. Editing medicines and tapping **Re-check** calls `/interactions/check` again.

### Designed for future API integration

The `InteractionDataSource` abstraction and `RemoteAPIDataSource` stub document
exactly where to plug in **FDA / OpenFDA / RxNorm / DrugBank**: implement `load()`
(bulk-sync into the canonical shape) or override per-query lookups, then register
the source in `service.build_source()` and set `INTERACTIONS_SOURCE`. The analysis
and UI code stay unchanged.

### Configuration (all optional — sensible defaults)

| Env var | Default | Purpose |
|---------|---------|---------|
| `INTERACTIONS_DATASET` | `datasets/drug_interactions/interactions.json` | Knowledge-base file (json/csv/sqlite). |
| `INTERACTIONS_SOURCE` | `auto` | Backend override: `auto`/`json`/`csv`/`sqlite`/`openfda`/`rxnorm`/`drugbank`. |
| `INTERACTIONS_DB_URL` | local SQLite (`…/interactions.db`) | History store (falls back to `DATABASE_URL`; PostgreSQL-ready). |
| `INTERACTION_MATCH_THRESHOLD` | `82` | Fuzzy-match floor (0–100) for resolving OCR'd names to known drugs. |
| `INTERACTIONS_USE_RAG` | `true` | Enrich reports with knowledge-base context when available. |

> ⚕️ **Disclaimer:** this analysis is for educational support only and is **not**
> a substitute for a qualified clinician or pharmacist.

---

## 🧠 Clinical Decision Support (CDSS)

A production-ready module that **synthesises every other subsystem** into a single,
risk-graded clinical report. It takes OCR-extracted medicines, patient demographics
(age/gender), symptoms and a diagnosis, then runs disease prediction, drug-interaction
analysis and a deterministic clinical **rules engine**, enriches with the RAG knowledge
base, and grades the overall risk. It runs **automatically after OCR** (completing the
`OCR → Medicine Matching → Drug Interaction → RAG → Clinical Decision Support → Final Report`
pipeline) and is also available as a **dedicated page** for ad-hoc clinician input.

### What it generates (the `ClinicalReport`)

- **Clinical Summary** — a readable synthesis of the case
- **Disease Prediction** — candidate conditions (from the ML model or supplied input)
- **Possible Risks** and **Contraindications**
- **Red Flag Alerts** — urgent findings (chest pain, stroke signs, GI bleed, …)
- **Drug Interaction Alerts** — the full interaction sub-report, reused verbatim
- **Missing Information** — what would sharpen the assessment
- **Recommended Next Steps**, **Recommended Lab Tests**, and **Follow-up Suggestions**
- **Risk Level** — `low` · `moderate` · `high` · `critical` (color-coded badges)
- **Risk Score** (0–100), **Confidence Score** (0–100), and **Sources Used**

### Risk levels & color coding

| Level | Badge tone | Meaning |
|-------|-----------|---------|
| 🟦 Low | primary | Routine care; confirm the medication list. |
| 🟨 Moderate | warning | Clinician confirmation + counselling on cautions. |
| 🟥 High | danger | Prompt review of flagged findings before dispensing. |
| 🟥 Critical | danger | Escalate now — emergency/urgent review. |

The headline level is driven by the **most dangerous single signal** (a critical red
flag or interaction forces a `CRITICAL` report); lesser signals accumulate additively
into the 0–100 score, so two moderate cases can still be ranked.

### Backend module — `backend/clinical_decision/`

| File | Responsibility |
|------|----------------|
| `schemas.py` | Pydantic contract: `RiskLevel` enum, `ClinicalAnalysisRequest`, `RedFlag`, `DiseaseHypothesis`, `ClinicalReport`, history + stats models. |
| `models.py` | SQLAlchemy ORM model (`ClinicalRecord`) with portable column types (SQLite **and** PostgreSQL). |
| `rules_engine.py` | **Pure medical knowledge** (no I/O): red-flag symptoms, age/pediatric/elderly cautions, pregnancy checks, polypharmacy, disease→lab-test and drug→monitoring maps, contraindications and missing-info detection. Data-table driven so a clinician can audit/extend it. |
| `risk_analyzer.py` | Pure scoring: fuses red flags + interaction severity + rule findings into a `RiskLevel` and a 0–100 `risk_score`. |
| `recommendation_engine.py` | Pure composition: prioritised next steps, follow-up advice, the clinical summary, and the confidence score. |
| `service.py` | Async orchestration + persistence: runs disease prediction (in a worker thread) and interactions **concurrently**, adds RAG context, applies the rules, and persists — every external call is best-effort and never breaks the report. |
| `router.py` | Async FastAPI routes under `/clinical`, with logging + exception handling. |
| `__init__.py` | Public surface: `router`, `analyze_clinical`, `get_service`. |

### API endpoints

| Method & path | Description |
|---------------|-------------|
| `POST /clinical/analyze` | Run a full analysis. Body: `{ medicines, symptoms, disease, diagnosis, age, gender, include_rag, run_disease_prediction, persist, source_record_id }`. Returns the full `ClinicalReport`. |
| `GET /clinical/history` | Paginated list of past analyses (`page`, `page_size`). |
| `GET /clinical/stats` | Dashboard aggregates: total reports + critical / high / moderate / low counts + average risk score. |
| `GET /clinical/{id}` | Full stored report for one analysis. |
| `DELETE /clinical/history` | Clear stored analyses. |

### Frontend

- **Dedicated page** — a new **Clinical Decision** sidebar page (`/clinical`): enter
  medicines, symptoms, diagnosis, age and gender → get the full report. Recent reports
  are listed and re-openable.
- **Automatic on OCR** — the OCR result carries a `clinical_report`, rendered inline on
  the **Prescription OCR** page below the interaction card.
- **Dashboard cards** — Total Clinical Reports, High Risk, Moderate Risk and Low Risk
  cases (from `GET /clinical/stats`).
- Reusable component: `frontend/src/ui/ClinicalReport.jsx` (embeds the existing
  `DrugInteractionReport` for the interaction section — no duplicated UI).

### How the workflow operates

1. **After OCR** (`POST /ocr/extract-prescription`): the pipeline extracts and matches
   medicines, `_attach_interactions(...)` runs the drug-interaction analysis, then
   `_attach_clinical(...)` runs the CDSS — **reusing** that interaction report (no
   recompute) and the parsed patient fields (age/gender/diagnosis). Both are best-effort
   and can **never** break the OCR response; both are captured in the OCR history record.
2. The OCR results page renders the **Clinical Decision Report** inline.
3. **On the dedicated page**, `POST /clinical/analyze` runs disease prediction +
   interactions **concurrently**, adds RAG context, applies the rules engine, grades the
   risk, and persists the report.
4. The **Dashboard** reads `GET /clinical/stats` for the risk-overview cards.

### Configuration (all optional — sensible defaults)

| Env var | Default | Purpose |
|---------|---------|---------|
| `CLINICAL_DB_URL` | local SQLite (`…/clinical.db`) | History store (falls back to `DATABASE_URL`; PostgreSQL-ready). |
| `CLINICAL_USE_RAG` | `true` | Enrich reports with knowledge-base context when available. |
| `CLINICAL_PREDICT_DISEASE` | `true` | Run disease prediction from symptoms when no diagnosis is supplied. |
| `CLINICAL_AUTO_ON_OCR` | `true` | Auto-generate a clinical report after OCR. |

> ⚕️ **Disclaimer:** the CDSS is an **educational decision-support aid only** — not a
> medical diagnosis. Every finding must be verified by a qualified clinician.

---

## 📑 Medical Report Generator

A production-ready module that turns a completed analysis into a **durable,
exportable medical report**. A report is a snapshot of everything the pipeline
produced and can be re-downloaded any time as **PDF, JSON or HTML**. It is
generated **automatically after every OCR analysis** (Requirement 9) and is also
available through a dedicated **Medical Reports** page.

### What each report contains (Requirement 2)

Patient information · uploaded prescription image · OCR extracted text · medicines
detected · confidence scores · alternative medicine matches · disease prediction ·
drug-interaction analysis · clinical-decision summary · AI recommendations ·
warnings · contraindications · follow-up suggestions · retrieved RAG documents ·
sources used · processing time · timestamp.

### Export formats

| Format | Endpoint | Notes |
|--------|----------|-------|
| **PDF** | `GET /reports/{id}/pdf` | Rendered server-side with **reportlab** (pure-Python, no system deps). If reportlab is not installed the endpoint returns an actionable `503` — JSON/HTML still work. |
| **JSON** | `GET /reports/{id}/json` | The full structured `ReportContent`. |
| **HTML** | `GET /reports/{id}/html` | Self-contained, print-friendly document (inline CSS). Add `?download=1` to force a file download instead of inline view. |

### Backend module — `backend/report_generator/`

| File | Responsibility |
|------|----------------|
| `schemas.py` | Pydantic contract: `ReportFormat`, `ReportContent` (+ `PatientInfo`, `ReportMedicine`, `RagDocument`), request, detail, list + stats models. |
| `models.py` | SQLAlchemy ORM model (`ReportRecord`) with portable columns (SQLite **and** PostgreSQL); the full content lives in a JSON column, with denormalised scalars for search/stats. |
| `report_builder.py` | **Pure** mapping: a serialised OCR result (which already carries the interaction + clinical sub-reports) → the structured `ReportContent`. No I/O. |
| `templates.py` | **Pure** HTML rendering (stdlib `html.escape` only — no template engine) into a self-contained, styled document. |
| `pdf_generator.py` | Server-side PDF rendering with reportlab (lazy-imported; degrades gracefully when absent). |
| `service.py` | Async persistence + prescription-image retention + the JSON/HTML/PDF export pipeline (CPU-bound rendering runs in a worker thread). |
| `router.py` | Async FastAPI routes under `/reports`, with logging + exception handling. |
| `__init__.py` | Public surface: `router`, `generate_from_ocr`, `get_service`. |

### API endpoints (Requirement 4)

| Method & path | Description |
|---------------|-------------|
| `POST /reports/generate` | Build + store a report from an OCR result. Body: `{ ocr_result, filename, processing_time, source_record_id, image_data_url, persist }`. |
| `GET /reports` | Filtered, paginated list. Query params: `q`, `patient`, `date_from`, `date_to`, `page`, `page_size`. |
| `GET /reports/stats` | Dashboard aggregates: total, generated today, average OCR confidence, high-risk reports. |
| `GET /reports/{id}` | Full stored report (powers the viewer). |
| `GET /reports/{id}/image` | The retained prescription image. |
| `GET /reports/{id}/pdf` · `/json` · `/html` | Downloadable exports. |
| `DELETE /reports/{id}` | Delete one report (and its image). |
| `DELETE /reports` | Clear all reports. |

### Storage & database

- **Default:** a local SQLite file (`backend/report_generator/reports.db`) via
  `aiosqlite`; retained images live in `backend/report_generator/images/`.
- **PostgreSQL (production):** set `DATABASE_URL` (or `REPORTS_DB_URL`) and install
  `asyncpg` — no code changes.

### Frontend (Requirements 6 & 7)

- **Medical Reports** sidebar page (`/reports`): search, filter by patient, filter by
  date range, paginated list, and per-report **View / PDF / JSON / HTML / Delete**.
- **Report Viewer** (`frontend/src/ui/ReportViewer.jsx`): prescription image, OCR
  text, medicines with confidence scores, patient info, and — by reusing the
  existing `ClinicalReport` + `DrugInteractionReport` components — the clinical
  decision, drug interactions, AI summary, sources and confidence.
- **Dashboard cards:** Total Reports · Generated Today · Average OCR Confidence ·
  High Risk Reports (from `GET /reports/stats`).

### How the report-generation workflow operates

1. **After OCR** (`POST /ocr/extract-prescription`): once interactions and the
   clinical report are attached, `_attach_report(...)` runs. It builds the
   structured `ReportContent`, **retains a copy of the prescription image** (still on
   disk at that point), persists the report, and stamps the new `report_id` back
   onto the OCR result. Best-effort — it can **never** break the OCR response
   (controlled by `REPORTS_AUTO_ON_OCR`).
2. `report_builder.build_content(...)` normalises the OCR result (medicines, fields,
   raw text, disease prediction, interactions, clinical data, RAG notes, sources)
   into one `ReportContent`.
3. The **Medical Reports** page lists reports (`GET /reports` + `/stats`) and opens
   the **Report Viewer** (`GET /reports/{id}`).
4. Exports are rendered **on demand** from the stored content — JSON (stdlib), HTML
   (`templates.py`), PDF (`pdf_generator.py` via reportlab) — so no large binaries
   are stored in the database.
5. A manual **`POST /reports/generate`** is also available for on-demand generation
   from any OCR result payload.

### Configuration (all optional — sensible defaults)

| Env var | Default | Purpose |
|---------|---------|---------|
| `REPORTS_DB_URL` | local SQLite (`…/reports.db`) | Report store (falls back to `DATABASE_URL`; PostgreSQL-ready). |
| `REPORTS_IMAGE_DIR` | `backend/report_generator/images` | Where retained prescription images are stored. |
| `REPORTS_AUTO_ON_OCR` | `true` | Auto-generate a report after every OCR analysis. |

> ⚕️ **Disclaimer:** generated reports are AI-assisted and for educational support
> only — always verify against the original prescription and a qualified clinician.

---

## 🛡️ Prescription Validation

A deterministic, auditable safety layer that runs **automatically after OCR** (and
on demand for an edited medicine list). It inspects the extracted medicines and
text, scores the prescription **0–100**, and grades it **Safe / Needs Review /
High Risk** — with a plain-language reason and a suggested fix for every finding.

### What it checks

- **Duplicate medicines** — the same drug prescribed more than once.
- **Duplicate active ingredients** — the same ingredient under different brand
  names (e.g. *Crocin* + *Dolo* are both paracetamol), a therapeutic-duplication /
  overdose risk.
- **Missing dosage / frequency / duration** — incomplete dosing instructions.
- **Unsafe abbreviations** — ISMP error-prone abbreviations (`U`, `IU`, `QD`,
  `MSO4`, trailing/naked decimals like `1.0` or `.5`, `µg`, `cc`, `HS`, …).
- **Suspicious medicine names** — unrecognised, gibberish or weakly-matched names.
- **Low OCR-confidence medicines** — rows read below the confidence threshold.
- **Potential prescription errors** — composite red flags (e.g. an order with no
  dosage, frequency *and* duration is treated as incomplete).

### Scoring & risk levels

Each finding subtracts a severity-weighted penalty from a perfect 100. Any
**high**-severity finding (or a score < 50) forces **High Risk**; any **medium**
finding (or a score < 80) forces at least **Needs Review**; otherwise **Safe**.

| Risk level | Grade | UI tone |
|------------|-------|---------|
| `safe` | Safe | success (green) |
| `needs_review` | Needs Review | warning (amber) |
| `high_risk` | High Risk | danger (red) |

### Backend module — `backend/prescription_validation/`

| File | Responsibility |
|------|----------------|
| `rules.py` | Pure safety knowledge — unsafe-abbreviation table, brand → active-ingredient map, scoring weights & normalisation helpers. |
| `validator.py` | The deterministic checks + scoring/grading (pure, synchronous, unit-testable). |
| `service.py` | Async orchestration + best-effort persistence; convenience `validate_from_ocr()` used by the OCR flow. |
| `models.py` | SQLAlchemy ORM row for the validation-history store (SQLite now, PostgreSQL-ready). |
| `schemas.py` | Pydantic request/report models — the stable frontend contract. |
| `router.py` | Async FastAPI routes under `/validation`, with logging + exception handling. |

### API endpoints

| Method & path | Purpose |
|---------------|---------|
| `POST /validation/check` | Validate a prescription / medicine list. Body: `{ medicines, raw_text, fields, overall_confidence, persist, source_record_id }`. Returns the full `ValidationReport`. |
| `GET /validation/history` | Paginated list of past validations (`page`, `page_size`). |
| `GET /validation/{id}` | Full stored report for one validation. |
| `DELETE /validation/history` | Clear stored validations. |

### Frontend

- A **Prescription Validation** card (`ui/PrescriptionValidationReport.jsx`) renders
  below the OCR results with the validation score, risk level, missing information,
  duplicate medicines, prescription warnings and suggested corrections.
- The card is populated automatically from the OCR result's `validation_report`,
  and a **Re-validate** button re-runs `POST /validation/check` against the edited
  medicine list.

### How the workflow operates

1. OCR extracts the medicines → the pipeline calls `validate_from_ocr()`.
2. The validator runs every check, scores + grades the prescription, and the report
   is shipped **inline** on the OCR result (`validation_report`) and persisted.
3. The workflow is **best-effort and non-fatal** — a validation failure is logged
   and never blocks or breaks the OCR response.

### Configuration (all optional — sensible defaults)

| Env var | Default | Purpose |
|---------|---------|---------|
| `VALIDATION_DB_URL` | local SQLite (`…/validation.db`) | History store (falls back to `DATABASE_URL`; PostgreSQL-ready). |
| `VALIDATION_AUTO_ON_OCR` | `true` | Auto-validate after every OCR analysis. |
| `VALIDATION_LOW_CONFIDENCE` | `0.6` | OCR row confidence below which a medicine is flagged. |

> ⚕️ **Disclaimer:** automated validation is a safety aid only — always verify
> medicines, dosages and instructions against the original prescription and a
> licensed pharmacist/physician before dispensing.

---

## 🩺 Symptom Checker & Triage

An interactive, safety-first symptom triage assistant. A user searches or picks
symptoms from a **categorized catalog**, sets a **severity** (1–10) and
**duration**, and gets a graded assessment that fuses the existing
**disease-prediction model** and the **RAG knowledge base** with a deterministic
triage engine.

### What it generates (the `TriageAssessment`)

- **Possible conditions** with confidence scores + reasoning (from the ML model).
- **Severity level** — mild / moderate / severe.
- **Urgency level** — a four-level triage grade: **Self Care → Visit Clinic →
  Urgent Care → Emergency**.
- **Red-flag symptoms** and a prominent **emergency warning** when warranted.
- **Recommended specialist**, **recommended tests** and **home-care suggestions**.
- **Evidence** — a RAG narrative + related knowledge-base documents and sources.

### Urgency levels & color coding

| Urgency | Grade | UI tone |
|---------|-------|---------|
| `self_care` | Self Care | success (green) |
| `visit_clinic` | Visit Clinic | primary (blue) |
| `urgent_care` | Urgent Care | warning (amber) |
| `emergency` | Emergency | danger (red) |

An **emergency red-flag** symptom (e.g. chest pain, slurred speech, coughing
blood) forces an **Emergency** grade regardless of the numeric triage score.

### Backend module — `backend/symptom_checker/`

Every file created, and what it does:

| File | Responsibility |
|------|----------------|
| `schemas.py` | Pydantic request/response models — the stable frontend contract (`SymptomAnalysisRequest`, `TriageAssessment`, `SymptomCatalog`, history types). |
| `symptom_matcher.py` | The **categorized symptom catalog** (nine body-system groups) + a synonym table + a fuzzy `SymptomMatcher` (exact → synonym → RapidFuzz) that resolves symptoms and reports their category. Pure & unit-testable. |
| `triage_engine.py` | The deterministic **triage policy** (pure): red-flag detection, 0–100 triage score, urgency & severity grading, specialist routing, recommended tests, home-care advice and the emergency warning. |
| `models.py` | SQLAlchemy ORM row for the assessment-history store (SQLite now, PostgreSQL-ready). |
| `service.py` | **Async orchestration** — resolves symptoms, runs disease prediction (`asyncio.to_thread`) and RAG **concurrently** (`asyncio.gather`), invokes the triage engine, and persists the assessment. Best-effort integration + persistence (never raises out of `analyze`). |
| `router.py` | Async FastAPI routes under `/symptoms`, with logging + exception handling. |
| `__init__.py` | Public surface: `router`, `analyze_symptoms`, `get_service`. |

### Symptom categories (Requirement 3)

General · Respiratory · Cardiovascular · Neurological · Gastrointestinal ·
Musculoskeletal · Skin · Urinary · Mental Health. Canonical symptom names are
aligned with the disease-prediction vocabulary so both subsystems agree.

### API endpoints

| Method & path | Purpose |
|---------------|---------|
| `POST /symptoms/analyze` | Run a full assessment. Body: `{ symptoms, severity, duration, age, gender, include_rag, top_k, persist }`. Returns the full `TriageAssessment`. |
| `GET /symptoms/catalog` | Categorized symptom list + duration options (powers the picker). |
| `GET /symptoms/suggest` | Autocomplete for the symptom search box (`q`, `limit`). |
| `GET /symptoms/history` | Paginated list of past assessments (`page`, `page_size`). |
| `GET /symptoms/{id}` | Full stored report for one assessment. |
| `DELETE /symptoms/history` | Clear stored assessments. |

The three required endpoints — `/analyze`, `/history`, `/{id}` — are present;
`/catalog` and `/suggest` support the frontend picker & search.

### Frontend

- A new **Symptom Checker** sidebar page (`/symptoms`,
  `pages/SymptomChecker.jsx`) with symptom search + multi-select, a categorized
  chip picker, a **severity slider**, a **duration selector**, and a
  **Generate Assessment** action.
- Results render the urgency grade, severity, triage score, recommended
  specialist, red flags + emergency banner, possible conditions (with confidence
  bars), recommended tests & home care, and the retrieved RAG documents/sources —
  plus a persistent medical disclaimer.
- New API helpers in `lib/api.js`: `getSymptomCatalog`, `suggestSymptomTerms`,
  `analyzeSymptoms`, `getSymptomHistory`, `getSymptomAssessment`.

### How the workflow operates

1. The page loads the catalog (`GET /symptoms/catalog`) and recent history.
2. On **Generate Assessment**, `POST /symptoms/analyze` resolves the symptoms,
   runs disease prediction + RAG **concurrently**, applies the triage engine, and
   **persists** the assessment (Requirement 9).
3. Every external call is best-effort — a disease-model or RAG failure degrades
   gracefully into `warnings` and never breaks the assessment.

### Configuration (all optional — sensible defaults)

| Env var | Default | Purpose |
|---------|---------|---------|
| `SYMPTOM_DB_URL` | local SQLite (`…/symptoms.db`) | History store (falls back to `DATABASE_URL`; PostgreSQL-ready). |
| `SYMPTOM_USE_RAG` | `true` | Enrich assessments with RAG knowledge-base evidence. |

> ⚕️ **Disclaimer:** the symptom checker is an educational triage aid only — it is
> not a diagnosis. In an emergency, call your local emergency number immediately.

---

## ✨ Medicine Alternatives & Recommendations

After OCR detects the medicines on a prescription (or when a user types names on
the dedicated page), this module retrieves full drug information and suggests
**generic equivalents, substitute brands and similar medicines** — each with a
plain-language reason — and enriches the harder fields from the **RAG knowledge
base**. It **runs automatically after OCR** (Requirement 7) and is also available
as a standalone page.

### What it retrieves per medicine (Requirement 2)

Generic name · Brand name · Drug class · Therapeutic category · Available
strengths · Alternative medicines · Equivalent generic drugs · Similar medicines
· Prescription-required (Yes/No) · Common uses · Common side effects ·
Contraindications · Pregnancy safety · Food interactions · Storage instructions.

Structured drug data (uses, side effects, substitutes, classes) comes from the
project's existing **~248k-row medicine dataset** via the shared `MedicineIndex`;
the evidence fields (contraindications, pregnancy, food, storage) and a grounded
summary come from **RAG** (`amedicine_info`). Fields the dataset does not carry
fall back to clearly-labelled, cautionary defaults — never fabricated detail.

### Backend module — `backend/medicine_recommendation/`

Every file created, and what it does:

| File | Responsibility |
|------|----------------|
| `schemas.py` | Pydantic request/response models — the stable frontend contract (`MedicineRecommendRequest`, `RecommendationReport`, `DrugInfo`, `AlternativeMedicine`, history types). |
| `alternative_finder.py` | Bridge to the shared `MedicineIndex`: resolves a name (fuzzy match → canonical + confidence), extracts substitutes/strengths, finds **same-class similar medicines** (via a lazily-built, cached class index), and applies best-effort heuristics for prescription-required / storage. Pure & synchronous (pandas/CPU). |
| `recommendation_engine.py` | Assembles the `DrugInfo` card, the three alternative lists **with reasons**, per-medicine summary + confidence, and the overall **AI recommendation report** (Requirement 3). Pure. |
| `models.py` | SQLAlchemy ORM row for the recommendation-history store (SQLite now, PostgreSQL-ready). |
| `service.py` | **Async orchestration** — resolves medicines in worker threads (`asyncio.to_thread`), enriches via RAG (best-effort), builds the report and persists it. Convenience `recommend_from_ocr()` used by the OCR flow. |
| `router.py` | Async FastAPI routes under `/medicine`, with logging + exception handling. |
| `__init__.py` | Public surface: `router`, `recommend_medicines`, `recommend_from_ocr`, `get_service`. |

### API endpoints (Requirement 5)

| Method & path | Purpose |
|---------------|---------|
| `POST /medicine/recommend` | Build a report. Body: `{ medicines, include_rag, max_alternatives, persist, source_record_id }`. Returns the full `RecommendationReport`. |
| `GET /medicine/recommendations` | Paginated list of past reports (`page`, `page_size`). |
| `GET /medicine/recommendations/{id}` | Full stored report for one recommendation. |
| `DELETE /medicine/recommendations` | Clear stored reports. |

> These live under the `/medicine` prefix and do **not** collide with the existing
> `GET /medicine-info/{name}` Medicine-Search endpoint.

### Frontend

- A new **Medicine Recommendations** sidebar page (`/recommendations`,
  `pages/MedicineRecommendations.jsx`): type medicines → get, per medicine, the
  **detected medicine, generic equivalent, brand alternatives, similar medicines,
  drug information, side effects, warnings, AI summary, sources and a confidence
  score**, plus the overall AI report. Recent reports are re-openable from history.
- New API helpers in `lib/api.js`: `recommendMedicines`,
  `getMedicineRecommendations`, `getMedicineRecommendation`.

### Automatic OCR integration (Requirement 7)

`ocr/router.py` calls `_attach_recommendations()` after the medicines are
extracted; the report is shipped **inline** on the OCR result as
`recommendation_report` and persisted. It is **best-effort and non-fatal** — a
failure is logged and never blocks or breaks the OCR response
(`MEDICINE_REC_AUTO_ON_OCR` toggles it).

### Configuration (all optional — sensible defaults)

| Env var | Default | Purpose |
|---------|---------|---------|
| `MEDICINE_REC_DB_URL` | local SQLite (`…/recommendations.db`) | History store (falls back to `DATABASE_URL`; PostgreSQL-ready). |
| `MEDICINE_REC_USE_RAG` | `true` | Enrich reports with RAG knowledge-base evidence. |
| `MEDICINE_REC_AUTO_ON_OCR` | `true` | Auto-generate a report after every OCR analysis. |

> ⚕️ **Disclaimer:** suggested alternatives and generic equivalents are educational
> only and must be substituted **only on a doctor's or pharmacist's advice**.

---

## 🤖 Multi-Agent AI Medical Copilot

The assistant is also a **true Agentic AI system**: instead of one monolith doing
everything, nine **specialised agents** collaborate over an **event-driven
pipeline**, sharing a **blackboard memory**, coordinated by a workflow engine and
observed live from the **AI Agent Monitor** page. Crucially, the agents
**orchestrate the existing services** (OCR, disease prediction, drug interactions,
RAG, clinical decision support, reports) — nothing was removed or rewritten, and
every existing API still works exactly as before.

### Architecture

```
                          ┌─────────────────────────────────────────────┐
   POST /agents/run  ───► │                AgentManager                 │  (composition root / DI)
                          │  TaskRouter → WorkflowEngine → ContextManager│
                          └───────────────┬─────────────────────────────┘
                                          │ builds per-run AgentContext
             ┌────────────────────────────┼─────────────────────────────┐
             ▼                            ▼                              ▼
      Shared Memory                  Event Bus                     LLM Factory
      (blackboard)              (pub/sub, async)            (provider-agnostic, offline-safe)
             ▲                            │                              ▲
             │ read/write                 │ events                       │ inject
             │                            ▼                              │
   ┌─────────┴──────────────────────  Agents  ──────────────────────────┴────────┐
   │ OCR → Medicine → (Disease ‖ Drug-Interaction) → Knowledge → Clinical →       │
   │ Explainability → Report → Audit    (each delegates to an existing service)   │
   └──────────────────────────────────┬───────────────────────────────────────────┘
                                       │ lifecycle events
                                       ▼
                                   Run Store  ───►  GET /agents/runs/{id}  ───► AI Agent Monitor (live)
```

### Agent workflow (event-driven, with concurrency)

```
Prescription / symptoms / medicines
        │
        ▼
   OCR Agent            → ocr_result          (image quality + OCR JSON)
        ▼
 Medicine Agent         → medicines           (fuzzy match, dosage, alternatives)
        ▼
 ┌──────────────┬────────────────────┐        ← concurrent stage (asyncio.gather)
 Disease Agent   Drug-Interaction Agent
 → disease       → interactions
 └──────────────┴────────────────────┘
        ▼
 Knowledge Agent        → knowledge           (SOLE RAG gateway, injection-sanitised, cached)
        ▼
 Clinical Agent         → clinical            (recommendations, risk)
        ▼
 Explainability Agent   → explanation         (WHY each conclusion, with evidence)
        ▼
 Report Agent           → report              (PDF / JSON / HTML)
        ▼
 Audit Agent            → audit               (every step, timing, confidence, errors)
```

### Sequence diagram

```
Client        Router      Manager     Engine      Agent(i)     Memory     EventBus    RunStore
  │  POST /run  │           │           │            │           │           │           │
  │────────────►│  start_run│           │            │           │           │           │
  │             │──────────►│  route+seed│           │           │           │  create   │
  │             │           │───────────────────────────────────────────────────────────►│
  │   run_id    │◄──────────│  create_task(_execute) │           │           │           │
  │◄────────────│           │──────────►│ run(ctx,plan)          │           │           │
  │             │           │           │  WORKFLOW_STARTED ─────────────────►│──apply───►│
  │             │           │           │──execute──►│ process()  │           │           │
  │             │           │           │            │──set(key)─►│           │           │
  │             │           │           │            │  AGENT_COMPLETED ─────►│──apply───►│
  │             │           │           │  (repeat per stage; independent agents gather)  │
  │             │           │           │  WORKFLOW_COMPLETED ───────────────►│──apply───►│
  │             │           │  finalize(records,result) ────────────────────────────────►│
  │ GET /runs/{id} (poll)   │           │            │           │           │  snapshot │
  │◄───────────────────────────────────────────────────────────────────────────────────│
```

### Folder structure & every new file

**`backend/agents/`** — the agent runtime:

| File | Responsibility |
|------|----------------|
| `agent_manager.py` | Composition root / façade. Wires all collaborators (DI), exposes `start_run` (background) + `run_and_wait`, builds the sanitised result summary. |
| `base_agent.py` | Abstract `BaseAgent` + lifecycle wrapper: timing, event emission, timeout, error isolation, `AgentRecord`. Agents implement one `process()` method (SRP). |
| `context_manager.py` | `AgentContext` (per-run DI bundle: memory, bus, logger, LLM, config) + `MemoryKeys` (the shared blackboard vocabulary). |
| `memory.py` | `SharedMemory` — the async-safe blackboard agents collaborate through. |
| `event_bus.py` | `AsyncEventBus` — pub/sub backbone; sync+async handlers, failure-isolated. |
| `task_router.py` | Classifies the request and returns the `RoutePlan` (stages) to run. |
| `workflow_engine.py` | Executes stages sequentially, agents **within a stage concurrently**; emits lifecycle events; computes overall confidence. |
| `agent_registry.py` | Lazy discovery/construction of agents from specs; honours enable/disable; exposes metadata without heavy imports. |
| `run_store.py` | In-memory live run state, updated from the event bus; powers the monitor. |
| `logger.py` | Run-scoped structured logging. |
| `schemas.py` | Pydantic contracts (run state, records, timeline, registry) — the frontend boundary. |
| `security.py` | Input validation, output sanitisation, **RAG prompt-injection defence**. |
| `router.py` | FastAPI routes under `/agents`. |
| `config/agent_config.py` | Per-agent enable/disable + timeouts (`AGENTS_DISABLED`, `AGENT_TIMEOUT`). |
| `config/llm_config.py` | LLM provider selection + credentials from env (`AGENT_LLM_PROVIDER`). |
| `config/workflow_config.py` | The declarative pipeline (stages) — reshape the flow without engine changes. |
| `implementations/*.py` | The nine agents (`ocr`, `medicine`, `disease`, `drug_interaction`, `knowledge`, `clinical`, `explainability`, `report`, `audit`) — each delegates to an existing service. |
| `tests/test_agents.py` | Unit + integration + workflow tests (run with `python -m backend.agents.tests.test_agents`). |

> **Note on `config/`:** the project already has a `backend/config.py` module, so
> the agent config package lives at **`backend/agents/config/`** (creating a
> top-level `backend/config/` package would shadow and break the existing
> settings module). Same intent, non-breaking placement.

**`backend/llm/`** — provider-agnostic LLM abstraction:

| File | Responsibility |
|------|----------------|
| `base_llm.py` | Abstract `BaseLLM` (the contract every provider implements) + `LLMResponse`. |
| `factory.py` | Config → concrete provider; `auto` picks the first available, else **offline**. |
| `providers/offline.py` | Always-available deterministic fallback — the app runs with **no** cloud/local LLM. |
| `providers/openai.py` | OpenAI (and base for OpenAI-compatible endpoints). |
| `providers/deepseek.py` | DeepSeek (OpenAI-compatible — extends OpenAI, no duplicated logic). |
| `providers/gemini.py` · `claude.py` · `ollama.py` | Google Gemini, Anthropic Claude, local Ollama (Llama/Mistral). |
| `providers/future.py` | Documented extension template (OpenRouter, Mistral, **MCP**, on-prem). |

### Agent responsibilities

| Agent | Delegates to | Reads → Writes |
|-------|--------------|----------------|
| **OCR** | `ocr.pipeline` + image quality | `inputs` → `ocr_result` |
| **Medicine** | `medicine_recommendation` (fuzzy match, dosage, alternatives) | `ocr_result`/`inputs` → `medicines` |
| **Disease Prediction** | `disease.service` (scikit-learn) | `inputs` → `disease` |
| **Drug Interaction** | `drug_interactions` | `medicines` → `interactions` |
| **Medical Knowledge** | `rag.rag_service` — **the only RAG caller** | `medicines`,`disease` → `knowledge` |
| **Clinical Decision** | `clinical_decision` | everything → `clinical` |
| **Explainability** | grounded reasoning + injected LLM | all outputs → `explanation` |
| **Report** | `report_generator` (PDF/JSON/HTML) | `ocr_result`,`clinical`,`interactions` → `report` |
| **Audit** | the execution trail | records → `audit` |

### API endpoints

| Method & path | Purpose |
|---------------|---------|
| `POST /agents/run` | Start a run from an image and/or symptoms/medicines/text (multipart). Returns `{ run_id }` (or the final state with `?wait=true`). |
| `GET /agents/runs/{run_id}` | Live/final run state — pipeline, timeline, logs, confidence (polled by the monitor). |
| `GET /agents/runs` | Recent runs. |
| `GET /agents/registry` | Agents, workflow stages and available LLM providers. |
| `GET /agents/health` | Subsystem health. |

### Frontend — AI Agent Monitor (`/agents`)

An animated pipeline of the nine agent nodes (pending → running → completed /
skipped / failed with per-agent latency + confidence), an overall progress bar,
current-agent indicator, a **timeline** of milestones, a **result summary** and
live **execution logs** — polled from `GET /agents/runs/{id}`.

### Design principles & guarantees

- **SOLID / DI** — agents depend on abstractions (`BaseAgent`, `BaseLLM`); the
  manager injects all collaborators; adding an agent or LLM provider touches only
  a spec/registry entry (Open-Closed).
- **Single responsibility** — each agent knows only its own slot; they never call
  each other, only the shared memory.
- **Offline-first** — no cloud/local LLM required; the offline provider guarantees
  the system runs anywhere. Configure a provider with `AGENT_LLM_PROVIDER`.
- **Resilient** — agent failures/timeouts are isolated into the run record; the
  pipeline always completes and degrades gracefully.
- **Performant** — async throughout; independent agents run concurrently; RAG
  queries are cached.
- **Secure** — inputs validated, outputs sanitised, RAG queries defended against
  prompt injection (the Knowledge Agent is the sole RAG gateway).
- **Future-ready** — OpenAI · Gemini · Claude · DeepSeek · Ollama · Llama ·
  Mistral · OpenRouter · **MCP** plug in behind `BaseLLM`; FHIR/HL7/DrugBank/
  RxNorm/OpenFDA/WHO connectors slot in as new agents or data sources without
  changing the engine.

### Configuration (all optional — sensible defaults)

| Env var | Default | Purpose |
|---------|---------|---------|
| `AGENT_LLM_PROVIDER` | `auto` | `auto` \| `offline` \| `openai` \| `gemini` \| `claude` \| `deepseek` \| `ollama`. |
| `AGENTS_DISABLED` | *(none)* | Comma-separated agent names to disable. |
| `AGENT_TIMEOUT` | `240` | Per-agent hard timeout (seconds); generous for first-run ML cold-start. |
| `ANTHROPIC_API_KEY` / `DEEPSEEK_API_KEY` / `OLLAMA_BASE_URL` | — | Provider credentials/endpoints (OpenAI/Gemini reuse existing keys). |

> ⚕️ **Disclaimer:** the copilot is educational decision *support*, not a diagnosis;
> all outputs must be verified by a qualified clinician.

---

## 📈 Future Improvements

- PaddleOCR Integration
- TrOCR Handwriting Recognition
- Better Medicine Matching
- Medical Report Generation
- Multi-language Support
- Voice Assistant

---

## 👨‍💻 Author

**Sneha Shaw**

GitHub:
https://github.com/snehashaw0330-arch

---

## ⭐ Support

If you like this project, consider giving it a ⭐ on GitHub.