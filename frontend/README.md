# 🩺 Medical AI Copilot

An enterprise-grade AI-powered Clinical Decision Support System (CDSS) that combines Prescription OCR, Retrieval-Augmented Generation (RAG), Large Language Models (LLMs), Disease Prediction, Drug Interaction Analysis, Clinical Reasoning, Explainable AI, Multi-Agent AI, and Medical Knowledge Retrieval to provide evidence-based clinical decision support.

The platform integrates Computer Vision, Machine Learning, Natural Language Processing (NLP), Vector Search, and Generative AI to assist healthcare professionals with prescription analysis, clinical reasoning, risk assessment, treatment recommendations, and patient-centric decision support.

Built using FastAPI, React.js, EasyOCR, Scikit-learn, Sentence Transformers, ChromaDB, SQLAlchemy, and modern AI engineering practices.



## 🏗️ System Architecture
                        ┌─────────────────────────────┐
                        │      React.js Frontend      │
                        └──────────────┬──────────────┘
                                       │
                                       ▼
                           FastAPI REST API Backend
                                       │
         ┌───────────────┬─────────────┬───────────────┐
         ▼               ▼             ▼               ▼
   Prescription OCR     RAG        Disease ML      AI Copilot
         │               │             │               │
         ▼               ▼             ▼               ▼
 Medicine Matching   ChromaDB     Scikit-learn     LLM Layer
         │               │             │               │
         └───────────────┴─────────────┴───────────────┘
                         │
                         ▼
            Clinical Decision Support Engine
                         │
                         ▼
             Reports • Explainability • Audit

## ✨ Features

- 📚 **Evidence-Based Medical Response Engine** — every AI-generated medical response is grounded in evidence retrieved from the RAG knowledge base **before** it is written: retrieve → rerank (semantic + lexical) → cite → generate. Returns the AI response, numbered **citations** with highlighted matching terms, **expandable retrieved chunks**, a **confidence score** derived from evidence strength, and full source attribution — available as a single query or a session-aware chat
- 🛡️ **AI Hallucination Detection & Evidence Verification** — every AI-generated response can be verified against the retrieved medical knowledge base before it is trusted: the engine breaks the answer into atomic **claims**, scores each against the evidence (semantic + lexical), and reports **evidence coverage**, **citation strength**, a **hallucination-risk** category (very low → critical), a **confidence** score, plus **unsupported claims**, **contradictions** and **missing references** — with unsupported statements highlighted in red
- 🧪 **AI Medical Simulation Engine** — a "what-if" engine that lets a clinician simulate treatment changes (dose change, replace / remove / add) and patient changes (age, weight, pregnancy, renal or hepatic impairment, allergies) across **multiple scenarios**, and see the projected drug interactions, disease risk, clinical recommendations, treatment suggestions, side effects, contraindications and RAG evidence — with a confidence breakdown — **before deciding**. Compares every scenario (and A vs B) against the baseline.
- 🧑‍⚕️ **AI Medical Copilot Workspace** — a session-scoped orchestrator that, on every upload, automatically runs the **full clinical pipeline** (OCR → medicine extraction → drug interactions → disease prediction → RAG evidence → clinical decision → AI summary → treatment → follow-up → medical report), **remembers the current patient for the session**, and presents everything in a three-panel workspace with a conversation, an AI reasoning view and a live AI Activity Timeline
- 🛡️ Clinical AI Audit, Explainability & Governance — every AI decision is explainable, traceable, auditable, reproducible & versioned: decision traces, an explainability engine, confidence/reliability analysis, a visual pipeline view, immutable audit logs, model & dataset registries, version tracking and CSV/JSON/PDF export
- 🫀 Medical Digital Twin — a continuously-evolving virtual health profile per patient: health score, trend analysis, future-risk prediction, timeline & charts, aggregated from every prior analysis
- 🤖 Multi-Agent AI Medical Copilot — nine specialised agents collaborate over an event-driven pipeline with a live monitor, shared memory & a provider-agnostic LLM layer
- 🧠 Disease Prediction using Machine Learning
- 🩺 Symptom Checker & Triage — categorized symptom picker, four-level urgency, specialist routing & RAG-backed evidence
- 📄 Handwritten Prescription OCR
- 🔎 AI Image Quality Assessment (pre-OCR)
- 🗂️ Prescription OCR History (persistent, searchable)
- ⚠️ Drug Interaction Analysis (auto-run after OCR; severity, warnings & recommendations)
- 🧠 Clinical Decision Support (CDSS) — risk-graded clinical reports fusing OCR, disease prediction, interactions & RAG
- 🧩 AI Clinical Reasoning Platform — instead of answering directly, the AI reasons **step by step** and shows all of its work: an animated reasoning pipeline, a weighted confidence breakdown, a differential with explicit rejection reasons, evidence cards and a full Clinical Reasoning Report
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
│   ├── evidence_engine/ # Evidence-Based Medical Response Engine (retriever, reranker, citation_builder, response_builder, service, router, schemas)
│   ├── evidence_verification/  # Hallucination Detection & Evidence Verification (verification_engine, hallucination_detector, evidence_ranker, citation_builder, confidence_calculator, service, router, schemas)
│   ├── simulation/     # AI Medical Simulation Engine (simulation_engine, treatment_engine, risk_engine, recommendation_engine, patient_model, service, router, schemas)
│   ├── copilot/        # AI Medical Copilot Workspace (workflow, planner, reasoning, context, memory, summary, service, router, schemas)
│   ├── ai_governance/  # Clinical AI Audit, Explainability & Governance (decision_tracker, explanation_engine, confidence_analyzer, pipeline_tracker, audit_logger, model_registry, dataset_registry, version_manager, service, router, models, schemas)
│   ├── digital_twin/   # Medical Digital Twin (health_score, trend/risk/prediction/timeline engines, service, router, models, schemas)
│   ├── agents/         # Multi-Agent Copilot (manager, engine, registry, event bus, memory, 9 agents)
│   ├── llm/            # Provider-agnostic LLM layer (base + factory + OpenAI/Gemini/Claude/Ollama/DeepSeek/offline)
│   ├── ocr/            # OCR pipeline + image quality assessment
│   ├── history/        # OCR History module (models, schemas, service, router)
│   ├── drug_interactions/  # Drug Interaction Analysis (models, schemas, service, router, utils)
│   ├── clinical_decision/  # Clinical Decision Support (rules_engine, risk_analyzer, recommendation_engine, service, ...)
│   ├── clinical_reasoning/ # AI Clinical Reasoning Platform (reasoning_engine, evidence_engine, confidence_engine, recommendation_engine, medical_rules, explanation_engine, service, router, schemas)
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

- Evidence-Based Medical Response Engine
- Clinical AI Audit, Explainability & Governance
- Medical Digital Twin
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

## 🧩 AI Clinical Reasoning Platform

Where the CDSS returns a graded *answer*, the **Clinical Reasoning Platform**
returns the **reasoning**. Instead of jumping straight to a recommendation, it
walks a fixed, transparent pipeline and records **every step** — with a status, a
human summary and a structured payload — so a clinician can audit exactly how the
platform arrived at its conclusion. It is **purely additive**: it only *reads*
from the existing subsystems (OCR, disease prediction, drug interactions, RAG) and
changes none of their behaviour.

### The reasoning pipeline

```
            ┌─────────────────────────── ReasoningRequest ───────────────────────────┐
            │  medicines · symptoms · disease/diagnosis · ocr_text · age · gender     │
            └────────────────────────────────────┬───────────────────────────────────┘
                                                 ▼
   1  OCR ─────────────────────► echo raw text + detected medicines
                                                 ▼
   2  Medicine Detection ───────► normalise the medicine list
                                                 ▼
   3  Medicine Validation ──────► resolve against the medicine dataset  ┐  (drug_interactions
   4  Drug Interaction Analysis ► drug–drug interactions + warnings     ┘   module — reused)
                                                 ▼
   5  Disease Prediction ───────► ranked hypotheses            (disease model — reused, in a thread)
                                                 ▼
   6  Retrieve Medical Evidence ► RAG knowledge base → EvidenceCards     (rag module — reused)
                                                 ▼
   7  Clinical Rules Evaluation ► deterministic MatchedRules   (medical_rules.py)
                                                 ▼
   8  Differential Diagnosis ───► leading / considered / rejected + rejection reasons
                                                 ▼
   9  Confidence Calculation ───► weighted, auditable ConfidenceBreakdown
                                                 ▼
  10  Final Recommendation ─────► graded, individually-justified recommendations
                                                 ▼
                             ClinicalReasoningReport  (cached + persisted)
```

Every stage is a `ReasoningStep` in the report's `reasoning_chain`, so the UI can
**animate the flow** live and replay it in the timeline afterwards. Each step
carries `status` (`complete`/`running`/`skipped`/`failed`), a headline `title`, a
`summary` and its `duration_ms`.

### Full explainability (for the leading diagnosis)

The report's `explanation` object answers, in one place, every "why" the product
requires:

| Question | Field |
|----------|-------|
| Why was this disease predicted? | `why_disease` |
| Which symptoms contributed? | `contributing_symptoms` (weighted) |
| Which medicines influenced it? | `influencing_medicines` |
| Which RAG documents were used? | `rag_documents_used` |
| Which clinical rules matched? | `matched_rules` |
| Which alternatives were considered? | `alternatives_considered` |
| Why were they rejected? | `rejected_alternatives[].rejection_reason` |
| How confident, and why? | `confidence_breakdown` (weighted components) |
| What would improve confidence? | `missing_information` |

### The Clinical Reasoning Report (12 sections)

`Patient Summary` · `OCR Findings` · `Medicine Analysis` · `Disease Prediction` ·
`Clinical Evidence` · `Reasoning Chain` · `Drug Interaction Analysis` ·
`Confidence Analysis` · `Alternative Diagnoses` · `Clinical Recommendations` ·
`Follow-up Suggestions` · `Medical References`.

### Confidence — weighted & auditable

Rather than an opaque number, confidence is a weighted sum of five named
components, each shown with its sub-score and the points it contributed:

| Component | Weight | Measures |
|-----------|:------:|----------|
| Input completeness | 20% | How much useful input was provided |
| Model certainty | 30% | Leading diagnosis probability |
| Evidence grounding | 20% | Quality/quantity of retrieved evidence |
| Rule agreement | 15% | Corroborating rules (critical alerts lower it) |
| Differential separation | 15% | How clearly the leader beats the runner-up |

### Backend module — `backend/clinical_reasoning/` (clean architecture)

| File | Responsibility |
|------|----------------|
| `router.py` | Async FastAPI routes (`/reasoning/*`) — logging + exception handling per route |
| `service.py` | Orchestration, **TTL+LRU caching**, best-effort persistence, history & stats |
| `reasoning_engine.py` | The step-by-step pipeline orchestrator (async, best-effort, timed steps) |
| `evidence_engine.py` | RAG retrieval → normalised `EvidenceCard`s (async, best-effort) |
| `confidence_engine.py` | Weighted, deterministic `ConfidenceBreakdown` |
| `recommendation_engine.py` | Final recommendations, follow-ups, references, risk roll-up |
| `medical_rules.py` | Pure, declarative clinical-rules engine → `MatchedRule`s |
| `explanation_engine.py` | Differential + the nine-part `ReasoningExplanation` |
| `schemas.py` | Pydantic frontend contract (report, steps, breakdown, differential…) |

Design contract (identical to every other module): **async everywhere** (the
CPU-bound disease model runs in a worker thread via `asyncio.to_thread`),
**best-effort integration** (any subsystem failure marks that *step* `failed` and
degrades gracefully — it never aborts the run), and **best-effort persistence**
(a DB error never breaks a reasoning run).

### Caching

Identical re-runs (e.g. a page refresh) are served from an in-memory **TTL + LRU
cache** keyed by a stable hash of the request, so the platform never re-runs the
slow disease-model + RAG fan-out unnecessarily. Cache metrics are exposed on
`/reasoning/stats`.

### API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/reasoning/analyze` | Run the full step-by-step reasoning pipeline |
| `GET` | `/reasoning/pipeline` | Static pipeline definition (UI renders it before a run) |
| `GET` | `/reasoning/history` | Paginated past reports (newest first) |
| `GET` | `/reasoning/stats` | Dashboard aggregates incl. cache metrics |
| `GET` | `/reasoning/{id}` | Full stored report for one run |
| `DELETE` | `/reasoning/history` | Clear stored reports |

### Frontend — Clinical Reasoning page (`/reasoning`)

A dedicated page (`src/pages/ClinicalReasoning.jsx`) with three reusable UI
components:

- **`ReasoningPipeline.jsx`** — the animated reasoning flow: nodes light up and a
  connector "flows" while a step runs; completed links turn green.
- **`ConfidenceMeter.jsx`** — a radial confidence gauge plus the weighted
  component breakdown and "would improve confidence" chips.
- **`ClinicalReasoningReport.jsx`** — renders all 12 sections, including evidence
  cards, the differential with rejection reasons, and the reasoning timeline.

While a run is in flight the page shows a **live animated pipeline** that advances
through the ten stages; on completion it swaps in the real, per-step statuses.

### How the workflow operates

```
User (medicines + symptoms + patient) ─► POST /reasoning/analyze
        │
        ├─ cache hit? ─► return cached report (flagged `cached: true`)
        │
        └─ ReasoningEngine.run():
             OCR → detection → validation → interactions → disease prediction
             → RAG evidence → clinical rules → differential → confidence
             → recommendation      (each step timed & recorded)
                   │
                   ├─ ConfidenceEngine → weighted breakdown
                   ├─ ExplanationEngine → differential + nine-part explanation
                   └─ RecommendationEngine → graded recommendations + follow-ups
        ▼
   ClinicalReasoningReport  ──►  cached (TTL+LRU)  &  persisted (best-effort)
        ▼
   Frontend animates the reasoning_chain, renders the confidence meter,
   evidence cards, alternative diagnoses and recommendations.
```

### Configuration (all optional — sensible defaults)

| Env var | Default | Purpose |
|---------|---------|---------|
| `CLINICAL_REASONING_DB_URL` | local SQLite (`…/reasoning.db`) | History store (falls back to `DATABASE_URL`; PostgreSQL-ready). |
| `CLINICAL_REASONING_USE_RAG` | `true` | Retrieve knowledge-base evidence during reasoning. |
| `CLINICAL_REASONING_PREDICT_DISEASE` | `true` | Run disease prediction from symptoms when no diagnosis is supplied. |
| `CLINICAL_REASONING_TOP_K` | `5` | Number of differential candidates to consider. |
| `CLINICAL_REASONING_CACHE_TTL` | `600` | Cache lifetime (seconds); `0` disables caching. |
| `CLINICAL_REASONING_CACHE_SIZE` | `128` | Max cached reports (LRU eviction). |

> ⚕️ **Disclaimer:** the Clinical Reasoning Platform is an **educational
> decision-support aid only** — not a medical diagnosis. Every step, score and
> recommendation must be verified by a qualified clinician.

---

## 🧑‍⚕️ AI Medical Copilot Workspace

The **Copilot Workspace** is the assistant's command centre. It doesn't add a new
clinical capability — it **orchestrates every existing one** into a single,
session-aware workflow. Drop in a prescription (or type medicines/symptoms) and the
Copilot automatically runs the whole pipeline, **remembers the patient for the
session**, keeps a running conversation, and shows a live **AI Activity Timeline**
of everything it did.

It is **purely additive**: it only *reads* from the existing modules (OCR, disease,
drug-interactions, RAG, clinical-decision, report-generator, the LLM layer) and
changes none of them. Every existing API keeps working unchanged.

### The automatic workflow (11 stages)

```
        ┌──────────────── upload / medicines / symptoms (one session) ───────────────┐
        ▼                                                                             │
  1  Receive Prescription                                                             │
        ▼                                                                             │
  2  Run OCR ................................ backend/ocr (run_pipeline, in a thread)  │
        ▼                                                                             │
  3  Extract Medicines ...................... OCR medicines ∪ typed ∪ parsed-from-text │
        ▼                                                                             │
  4  Check Drug Interactions ................ backend/drug_interactions (reused)       │
        ▼                                                                             │
  5  Predict Disease ........................ backend/disease (reused, in a thread)    │
        ▼                                                                             │
  6  Retrieve Medical Evidence (RAG) ........ backend/rag via the evidence engine      │
        ▼                                                                             │
  7  Generate Clinical Decision ............. backend/clinical_decision (reused)       │
        ▼                                                                             │
  8  Generate AI Summary ...................┐                                          │
  9  Generate Treatment Suggestions ........┤ backend/llm (offline-safe fallback)      │
 10  Generate Follow-up Suggestions ........┘                                          │
        ▼                                                                             │
 11  Generate Final Medical Report .......... backend/report_generator (reused)        │
        ▼                                                                             │
   CopilotAnalysis  ──►  folded into the session PatientContext  ──►  timeline + chat ─┘
```

Each stage is recorded as a `ReasoningStep` (status, headline, timing) **and** as
one or more `ActivityEvent`s (`09:42 OCR Completed`), so the workspace can render
both the **AI Reasoning** view and the **AI Activity Timeline**.

### Session memory — "remember the current patient"

The Copilot keeps one evolving `PatientContext` per session (in memory, TTL + LRU
evicted). **Every new upload updates it automatically**: medicines accumulate,
patient identity/conditions are backfilled from OCR, a `ReportRef` is prepended to
*Previous Reports*, and the activity timeline grows. A `session_id` is issued on
the first analyze call and returned on every response; the frontend persists it in
`localStorage` so a page reload keeps the same patient.

### The workspace layout

| Left panel | Center | Right panel |
|------------|--------|-------------|
| Patient Context | Conversation (grounded chat) | Drug Interactions |
| Current Medicines | AI Reasoning (animated pipeline) | Disease Prediction |
| Previous Reports | Evidence (RAG cards) | Confidence + Risk |
| AI Activity Timeline | Current Analysis (summary / treatment / follow-up) | Recommendations · Medical References |

### Backend module — `backend/copilot/` (clean architecture)

| File | Responsibility |
|------|----------------|
| `router.py` | Async FastAPI routes (`/copilot/*`) — per-route logging + exception handling; multipart upload; image never retained on disk |
| `service.py` | Top-level orchestration, **TTL + LRU result cache** (keyed by a hash of inputs incl. the file bytes), session wiring, chat/context/history |
| `workflow.py` | The 11-stage pipeline orchestrator (async, best-effort, every stage timed) |
| `planner.py` | Decides which stages to run from the supplied inputs + feature flags (records skip reasons) |
| `reasoning.py` | `WorkflowTrace` — records the reasoning steps + activity events for one run |
| `context.py` | Session-scoped `PatientContext` store (TTL + LRU), folds each analysis into memory |
| `memory.py` | Conversation + activity helpers; builds the grounded prompt snapshot |
| `summary.py` | AI summary / treatment / follow-up / chat via the provider-agnostic LLM layer (offline-safe) |
| `schemas.py` | Pydantic frontend contract (analysis, context, chat, history, steps, activity) |

Design contract (identical to every other module): **async everywhere** (CPU-bound
OCR + disease model run in worker threads via `asyncio.to_thread`), **best-effort
integration** (any subsystem failure marks *that stage* failed and the workflow
continues — it never aborts), and **exception-safe** routes.

### Caching

Identical re-runs are served from an in-memory **TTL + LRU cache** keyed by a
stable hash of the inputs (including the uploaded file's bytes), so the expensive
OCR + model + RAG fan-out isn't repeated. A cache hit is re-stamped with a fresh
`analysis_id` and flagged `cached: true`.

### API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/copilot/analyze` | Run the full 11-stage workflow (multipart: optional image + patient/medicine/symptom fields). Updates the session context. |
| `POST` | `/copilot/chat` | Ask the Copilot a question grounded in the current patient session. |
| `GET` | `/copilot/context` | The remembered patient context + conversation for a session. |
| `GET` | `/copilot/history` | The analyses run in a session (newest first). |
| `GET` | `/copilot/pipeline` | Static 11-stage pipeline definition (drives the UI animation). |

### Frontend — Copilot Workspace page (`/copilot`)

`src/pages/CopilotWorkspace.jsx` implements the three-panel workspace: an upload +
tag-input bar, a tabbed center (Conversation / AI Reasoning / Evidence / Current
Analysis), and live left/right context panels. While the workflow runs, the AI
Reasoning tab shows an **animated pipeline** (reusing `ui/ReasoningPipeline.jsx`);
on completion it swaps in the real per-stage statuses. The session id is persisted
in `localStorage` so the patient survives a reload.

### How the workflow operates

```
Upload / inputs ─► POST /copilot/analyze (multipart)
        │
        ├─ resolve session (create or reuse)  ── remembers the patient
        ├─ cache hit? ─► return re-stamped cached analysis (cached: true)
        └─ CopilotWorkflow.run() under the session lock:
             receive → OCR → extract → interactions → disease → evidence
             → clinical decision → summary → treatment → follow-up → report
                   │  (each stage recorded: ReasoningStep + ActivityEvent)
                   ▼
             CopilotAnalysis
                   │
                   ├─ fold into PatientContext (medicines, conditions, reports, timeline)
                   └─ append assistant message to the conversation
        ▼
   Frontend updates all three panels + the AI Activity Timeline; the clinician can
   then chat with the Copilot, grounded in the accumulated session context.
```

### Configuration (all optional — sensible defaults)

| Env var | Default | Purpose |
|---------|---------|---------|
| `COPILOT_USE_RAG` | `true` | Retrieve knowledge-base evidence during the workflow. |
| `COPILOT_USE_LLM` | `true` | Use the LLM layer for narratives + chat (offline-safe fallback). |
| `COPILOT_SESSION_TTL` | `86400` | Idle patient-session lifetime (seconds). |
| `COPILOT_MAX_SESSIONS` | `500` | Max concurrent sessions (LRU eviction). |
| `COPILOT_CACHE_TTL` | `600` | Workflow result cache lifetime (seconds); `0` disables. |
| `COPILOT_CACHE_SIZE` | `128` | Max cached workflow results (LRU eviction). |
| `COPILOT_MAX_MESSAGES` / `COPILOT_MAX_TIMELINE` / `COPILOT_MAX_ANALYSES` | `200` / `300` / `50` | Per-session bounds so memory stays bounded. |

> ⚕️ **Disclaimer:** the Copilot Workspace is an **educational decision-support aid
> only** — not a medical diagnosis. Every summary, suggestion and report must be
> verified by a qualified clinician. In an emergency, seek urgent care.

---

## 🧪 AI Medical Simulation Engine

The Simulation Engine answers the question a clinician asks *before* changing a
prescription: **"what happens if I do this?"** Given a baseline prescription + a
patient, the doctor describes one or more **scenarios** — dose changes, medicine
replace / remove / add, and patient changes (age, weight, pregnancy, renal or
hepatic impairment, allergies) — and the engine projects the resulting picture for
each, then compares every scenario against the baseline (and A vs B).

It is **purely additive**: it only *reads* from the existing subsystems (OCR,
disease prediction, drug interactions, clinical decision, RAG, report generator)
and mutates none. Every existing API keeps working unchanged.

### What every simulation produces (per scenario)

Updated **drug interactions** · updated **disease risk** · **clinical
recommendations** · **treatment suggestions** · possible **side effects** ·
**contraindications** · **RAG evidence** · a weighted **confidence** breakdown — plus
a single 0-100 **composite risk score** (lower is safer) that the comparison is
built on.

### Supported changes

| Treatment changes | Patient changes |
|-------------------|-----------------|
| Medicine **dosage** change | **Age** change |
| Medicine **replacement** | **Weight** change |
| Medicine **removal** | **Pregnancy** status |
| Medicine **addition** | **Kidney** disease (none→severe) |
| | **Liver** disease (none→severe) |
| | **Allergy** changes |

### Example

```
Current Prescription            Doctor's change (Scenario A)
  Paracetamol 500mg    ──►         Paracetamol 650mg
  Amoxicillin 500mg
        │
        ▼  simulate
  ┌───────────────────────────────────────────────────────────┐
  │ apply edits ─► re-run interactions + disease + evidence    │
  │            ─► contraindications · side effects · risk      │
  │            ─► recommendations · treatment · confidence     │
  └───────────────────────────────────────────────────────────┘
        │
        ▼  compare vs Baseline (and A vs B)
   Interaction Risk → Clinical Recommendation → Evidence → Final Report
```

### How it flows

```
POST /simulation/run  { baseline_medicines, patient, scenarios[] }
        │
        ├─ cache hit? ─► return cached report (cached: true)
        │
        └─ for the BASELINE and EACH scenario (run concurrently):
             treatment_engine.apply_changes()   → resulting medicines + edit log
             patient_model.apply_patient_change()→ effective patient + derived flags
                   │
                   ├─ drug_interactions.analyze_medicines()   (reused)
                   ├─ disease.predict() (in a thread)          (reused)
                   ├─ clinical_reasoning.evidence_engine       (RAG, reused)
                   ├─ recommendation_engine → contraindications, side effects,
                   │                          treatment suggestions, recommendations
                   └─ risk_engine → disease risk + composite risk score + confidence
        ▼
   simulation_engine.compare(baseline, variant)  → ComparisonDelta (risk Δ, new/resolved
        │                                            interactions, new contraindications, verdict)
        ▼
   pick safest scenario → SimulationReport (cached + persisted)
```

### Backend module — `backend/simulation/` (clean architecture)

| File | Responsibility |
|------|----------------|
| `router.py` | Async FastAPI routes (`/simulation/*`) — per-route logging + exception handling |
| `service.py` | Orchestration (baseline + N scenarios, concurrent), comparisons, safest-scenario pick, **TTL+LRU cache**, best-effort persistence + history |
| `simulation_engine.py` | Evaluates one scenario end-to-end (async, best-effort) and builds the variant-vs-baseline / A-vs-B comparisons |
| `treatment_engine.py` | Parses medicine strings and applies the treatment edits (dosage / replace / remove / add) with a human-readable change log |
| `patient_model.py` | Applies patient overrides → effective patient; derives clinical flags (paediatric / geriatric / pregnancy / renal / hepatic / low-weight) |
| `risk_engine.py` | Disease risk (patient-amplified) + the composite 0-100 risk score |
| `recommendation_engine.py` | Contraindications, side effects, treatment suggestions, clinical recommendations + weighted confidence breakdown (curated safety net over the live datasets) |
| `schemas.py` | Pydantic frontend contract (request, scenario, result, comparison, report, history) |

Design contract (identical to every other module): **async everywhere** (CPU-bound
disease model runs in a worker thread via `asyncio.to_thread`; baseline + scenarios
run concurrently with `asyncio.gather`), **best-effort integration** (any subsystem
failure degrades that stage only and is recorded in `warnings` — it never aborts a
simulation), and **best-effort persistence** (a DB error never breaks a run).

### Caching

Identical re-runs are served from an in-memory **TTL + LRU cache** keyed by a stable
hash of the request, so the interaction + disease + RAG fan-out isn't repeated. A
cache hit is flagged `cached: true`.

### Multiple scenarios & A-vs-B comparison

Every request may carry several scenarios (capped by `SIMULATION_MAX_SCENARIOS`).
The engine always simulates an implicit **baseline** (current prescription, no
changes) and compares each variant to it; when exactly two variants are supplied it
also emits a direct **A vs B** comparison. Each `ComparisonDelta` carries the risk-
score delta, new/resolved interactions, new contraindications and a plain-language
verdict, and the report names the safest **recommended scenario**.

### API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/simulation/run` | Run a simulation (baseline + variant scenarios); returns per-scenario results + comparisons |
| `GET` | `/simulation/history` | Paginated list of past simulations (newest first) |
| `GET` | `/simulation/{id}` | Full stored report for one simulation |
| `DELETE` | `/simulation/history` | Clear stored simulations |

### Frontend — Treatment Simulator page (`/simulator`)

`src/pages/TreatmentSimulator.jsx` renders the required workspace: **Current
Treatment** + **Editable Medicines** (name / dose / unit rows), a patient editor,
and a **scenario builder** (add multiple scenarios; each with medicine changes +
patient overrides). Results show a **Risk Meter** per scenario, a **Clinical
Summary** with the recommended scenario, the **Scenario Comparison** (A vs Baseline,
A vs B), **Alternative Treatments** (treatment suggestions), **Evidence Cards** and a
**Confidence Meter** (reusing `ui/ConfidenceMeter.jsx`).

### Integrations (reused, never modified)

OCR · Disease Prediction · Drug Interaction Analysis · Clinical Decision Support ·
RAG Knowledge Base · Medical Reports (the recommended scenario can be persisted as a
durable report via `generate_report: true`).

### Configuration (all optional — sensible defaults)

| Env var | Default | Purpose |
|---------|---------|---------|
| `SIMULATION_DB_URL` | local SQLite (`…/simulation.db`) | History store (falls back to `DATABASE_URL`; PostgreSQL-ready). |
| `SIMULATION_USE_RAG` | `true` | Retrieve knowledge-base evidence per scenario. |
| `SIMULATION_PREDICT_DISEASE` | `true` | Run disease prediction from symptoms inside a simulation. |
| `SIMULATION_MAX_SCENARIOS` | `6` | Max variant scenarios per request (bounds fan-out). |
| `SIMULATION_CACHE_TTL` | `600` | Result cache lifetime (seconds); `0` disables. |
| `SIMULATION_CACHE_SIZE` | `128` | Max cached reports (LRU eviction). |

> ⚕️ **Disclaimer:** the Simulation Engine is an **educational decision-support aid
> only** — not a medical order. Projected interactions, risks and suggestions must
> be verified by a qualified clinician before any treatment change.

---

## 🛡️ AI Hallucination Detection & Evidence Verification

Large language models can produce fluent, confident text that is not actually
supported by any source — a serious risk in a medical setting. This engine is the
project's safeguard: it takes an AI-generated response and **checks it, claim by
claim, against the medical evidence retrieved from the RAG knowledge base**, then
estimates whether the response is well-grounded or potentially hallucinated.

It is purely additive: it only *reads* from the RAG knowledge base and changes no
existing feature. Any module can also call `verify_response()` to verify its own
generated text before showing it to the user.

### Verification architecture

```
   User question
        │
        ▼
   Retrieve context (RAG knowledge base) ──► evidence chunks + retrieval score
        │
        ▼
   Generate AI response  (RAG answer, or the caller's own text is supplied)
        │
        ▼
   ┌──────────────────────── verification_engine ────────────────────────┐
   │  hallucination_detector : split response → atomic claims            │
   │                           build claim↔evidence similarity           │
   │                           classify: supported / weak / unsupported /│
   │                                     contradicted                    │
   │  evidence_ranker        : rank docs by response-relevance           │
   │  citation_builder       : link supported claims → evidence (+strength)│
   │  confidence_calculator  : coverage · citation strength · risk · conf│
   └─────────────────────────────────────────────────────────────────────┘
        │
        ▼
   Verified response  +  metrics  +  per-claim highlighting  (cached + persisted)
```

### Hallucination detection workflow

1. **Claim extraction** — the response is split into atomic, verifiable claims
   (sentences); questions, greetings and disclaimers are dropped.
2. **Similarity** — each claim is compared to every evidence sentence. When the
   RAG embedding model (MiniLM) is available the score is **semantic cosine
   blended with lexical content-containment**; otherwise a deterministic lexical
   fallback is used. The blend is deliberate: same-topic sentences score a high
   baseline cosine even when the specific assertion is absent, so a claim whose
   distinctive terms don't appear in the evidence is penalised down — this is what
   stops an on-topic hallucination from being marked "supported".
3. **Classification** — each claim becomes **supported** (strong match), **weak**
   (partial/indirect), **unsupported** (no match) or **contradicted** (high overlap
   but opposite negation polarity — a heuristic contradiction flag).
4. **Roll-up** — coverage, citation strength, hallucination risk and confidence.

### Evidence scoring

| Metric | How it's computed |
|--------|-------------------|
| **Evidence coverage %** | `(supported + 0.5 × weak) / total_claims` |
| **Citation strength** | avg of each citation's strength (`0.85 × similarity + 0.15 × retrieval_score`) |
| **Document relevance** | `0.7 × best-claim-match + 0.3 × original retrieval score` (used to rank retrieved docs) |
| **Missing references** | weak/unsupported claims that read as assertions but have no solid citation |

### Hallucination-risk categories

The risk score (0-100, higher = riskier) is
`0.60 × unsupported% + 0.20 × weak% + contradiction_penalty + evidence_penalty`,
bucketed into five levels:

| Score | Category |
|:-----:|----------|
| < 10 | **Very Low** |
| 10–24 | **Low** |
| 25–49 | **Medium** |
| 50–74 | **High** |
| ≥ 75 | **Critical** |

### Confidence calculation

Confidence (0-100) is a weighted, explainable blend — the panel shows every
component and the points it contributed:

| Component | Weight | Score source |
|-----------|:------:|--------------|
| Evidence coverage | 35% | % of claims supported |
| Citation strength | 25% | avg citation strength |
| Retrieval quality | 20% | RAG retrieval confidence × 100 |
| Low hallucination | 20% | `100 − hallucination_risk_score` |

### Backend module — `backend/evidence_verification/` (clean architecture)

| File | Responsibility |
|------|----------------|
| `router.py` | Async FastAPI routes (`/verification/*`) — per-route logging + exception handling |
| `service.py` | RAG retrieval + optional generation, **TTL+LRU cache**, best-effort persistence + history; `verify_response()` for reuse by other modules |
| `verification_engine.py` | Orchestrates the claim-level pipeline over one response |
| `hallucination_detector.py` | Claim extraction, semantic+lexical similarity (blended), support classification, contradiction heuristic |
| `evidence_ranker.py` | Ranks retrieved documents by response-relevance; annotates which claims each supports |
| `citation_builder.py` | Links supported claims to their strongest evidence (citation strength) + missing references |
| `confidence_calculator.py` | Coverage, citation strength, hallucination-risk category + weighted confidence breakdown |
| `schemas.py` | Pydantic frontend contract (request, claim, evidence, citation, metrics, result, history) |

Design contract (identical to every other module): **async everywhere** (RAG
retrieval + embeddings run off the event loop), **best-effort** (missing evidence
or an unavailable embedding model still yields an honest, well-formed result via
the lexical fallback — it never raises), structured **logging**, graceful **error
handling**, and **caching** of repeated requests.

### API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/verification/check` | Verify a response (or generate one via RAG, then verify) against evidence |
| `GET` | `/verification/history` | Paginated list of past verifications (newest first) |
| `GET` | `/verification/{id}` | Full stored result for one verification |
| `DELETE` | `/verification/history` | Clear stored verifications |

### Frontend — Evidence Verification (`/verification`)

`src/pages/EvidenceVerification.jsx` + the reusable `ui/EvidenceVerificationPanel.jsx`
render the required panel: **Evidence Coverage**, a **Confidence Meter**, a
**Hallucination-Risk badge**, the **Retrieved Documents**, **Supporting Citations**
and **Unsupported Statements** — with the verified response shown claim-by-claim and
**unsupported / contradicted claims highlighted in red**. The panel is a standalone
component so it can be dropped next to any AI answer (e.g. the AI Chat) to verify it
inline.

### Configuration (all optional — sensible defaults)

| Env var | Default | Purpose |
|---------|---------|---------|
| `VERIFICATION_DB_URL` | local SQLite (`…/verification.db`) | History store (falls back to `DATABASE_URL`; PostgreSQL-ready). |
| `VERIFICATION_USE_EMBEDDINGS` | `true` | Use the RAG embedding model for semantic similarity (else lexical only). |
| `VERIFICATION_TOP_K` | `6` | Evidence chunks to retrieve when the caller supplies none. |
| `VERIFICATION_SUPPORT_THRESHOLD` | `0.50` | Blended-similarity threshold for "supported". |
| `VERIFICATION_WEAK_THRESHOLD` | `0.32` | Blended-similarity threshold for "weak". |
| `VERIFICATION_CACHE_TTL` | `600` | Result cache lifetime (seconds); `0` disables. |
| `VERIFICATION_CACHE_SIZE` | `256` | Max cached verifications (LRU eviction). |

> ⚕️ **Disclaimer:** evidence verification is an **automated safeguard** that
> estimates how well an AI response is grounded in the retrieved knowledge base. It
> is **not** a guarantee of correctness; unsupported or contradicted claims must be
> checked by a qualified clinician before being relied upon.

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
everything, ten **specialised agents** — OCR, Medicine (Recommendation), Disease
Prediction, Drug Interaction, Medical Knowledge, Clinical Decision, Explainability,
**Evidence Verification**, Report Generation and Audit — collaborate over an
**event-driven pipeline**, sharing a **blackboard memory**, coordinated by a
workflow engine and observed live from the **AI Agent Monitor** page (pipeline
view, a true **Execution Timeline**, and an **Agent Status Dashboard**).
Crucially, the agents **orchestrate the existing services** (OCR, disease
prediction, drug interactions, RAG, clinical decision support, evidence
verification, reports) — nothing was removed or rewritten, and every existing
API still works exactly as before.

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
   │ (Explainability ‖ Evidence Verification) → Report → Audit                    │
   │                        (each delegates to an existing service)               │
   └──────────────────────────────────┬───────────────────────────────────────────┘
                                       │ lifecycle events
                                       ▼
                                   Run Store  ───►  GET /agents/runs/{id}  ───► AI Agent Monitor (live)
                                       │
                                       ▼
                          AgentHealthMonitor  ───►  GET /agents/health  ───► Agent Status Dashboard
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
 ┌──────────────────────┬──────────────────────────────┐   ← concurrent stage (asyncio.gather)
 Explainability Agent    Evidence Verification Agent
 → explanation           → evidence_verification (hallucination risk, citations, confidence
 └──────────────────────┴──────────────────────────────┘    — verifies the Clinical Agent's summary)
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
| `run_store.py` | In-memory live run state, updated from the event bus; powers the monitor (per-agent `started_at`/`finished_at` are recorded live, not just at finalize, so the Execution Timeline renders during a running pipeline too). |
| `health_monitor.py` | `AgentHealthMonitor` — calls each agent's `health_check()` (RAG index, model files, datasets, OCR stack, …), caches results for 30s, and rolls them into an aggregate status for `GET /agents/health`. |
| `logger.py` | Run-scoped structured logging. |
| `schemas.py` | Pydantic contracts (run state, records, timeline, registry, `AgentHealth`/`HealthReport`) — the frontend boundary. |
| `security.py` | Input validation, output sanitisation, **RAG prompt-injection defence**. |
| `router.py` | FastAPI routes under `/agents`. |
| `config/agent_config.py` | Per-agent enable/disable + timeouts (`AGENTS_DISABLED`, `AGENT_TIMEOUT`). |
| `config/llm_config.py` | LLM provider selection + credentials from env (`AGENT_LLM_PROVIDER`). |
| `config/workflow_config.py` | The declarative pipeline (stages) — reshape the flow without engine changes. |
| `implementations/*.py` | The ten agents (`ocr`, `medicine`, `disease`, `drug_interaction`, `knowledge`, `clinical`, `explainability`, `evidence_verification`, `report`, `audit`) — each delegates to an existing service and implements `health_check()`. |
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
| **Evidence Verification** | `evidence_verification.verify_response()` | `clinical`,`knowledge` → `evidence_verification` |
| **Report** | `report_generator` (PDF/JSON/HTML) | `ocr_result`,`clinical`,`interactions` → `report` |
| **Audit** | the execution trail | records → `audit` |

Every agent also implements `health_check()` — a cheap, side-effect-free probe
of its underlying dependency (the RAG index for Knowledge/Evidence Verification,
the disease model file, the interaction dataset, the OCR stack, the medicine
dataset, the LLM layer, …) that never runs the agent's real pipeline logic.

### API endpoints

| Method & path | Purpose |
|---------------|---------|
| `POST /agents/run` | Start a run from an image and/or symptoms/medicines/text (multipart). Returns `{ run_id }` (or the final state with `?wait=true`). |
| `GET /agents/runs/{run_id}` | Live/final run state — pipeline, timeline, logs, confidence (polled by the monitor). |
| `GET /agents/runs` | Recent runs (now surfaced in the frontend's Agent Status Dashboard). |
| `GET /agents/registry` | Agents, workflow stages and available LLM providers. |
| `GET /agents/health` | Per-agent liveness probes (`AgentHealth[]`) + an aggregate `HealthReport` (`ok`/`degraded`/`down`). Pass `?force=true` to bypass the 30s cache. |

### Frontend — AI Agent Monitor (`/agents`)

- An animated pipeline of the ten agent nodes (pending → running → completed /
  skipped / failed with per-agent latency + confidence), an overall progress bar,
  current-agent indicator, a **result summary** and live **execution logs**.
- **Execution Timeline** — a true time-axis view built from each agent's actual
  `started_at`/`finished_at`, rendered as horizontal bars; concurrent agents
  (Disease ‖ Drug-Interaction, Explainability ‖ Evidence Verification) show as
  visibly overlapping bars, not just near-identical log timestamps.
- **Agent Status Dashboard** — a live health grid (one tile per agent: healthy /
  unavailable / disabled, from `GET /agents/health`, auto-refreshed every 30s)
  plus a **recent runs** panel (`GET /agents/runs`) — click any past run to load
  it back into the monitor.

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
- **Observable** — every agent reports its own liveness via `health_check()`
  (distinct from admin enable/disable), rolled up into `GET /agents/health` and
  the Agent Status Dashboard, so a broken dependency is visible before a run
  ever starts, not just after an agent fails mid-pipeline.
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

## 🫀 Medical Digital Twin

A **Digital Twin** is a continuously-evolving virtual health profile for each
patient — one intelligent model that fuses **every** prior analysis (OCR results,
disease predictions, medicines, drug interactions, clinical decisions and
generated reports) into a health score, trend analysis, future-risk prediction, a
timeline and RAG-enriched recommendations.

### How it works (derived, not duplicated)

The twin is **computed live** from the existing **Medical-Report store** — which
already auto-captures each OCR analysis together with its medicines, disease
prediction, interaction report and clinical decision. The service groups a
patient's reports (**by patient name → a stable `patient_id` slug**), folds them
oldest→newest through the pure engines, and persists a **snapshot** per patient
(for analytics + durability). Nothing existing is modified — the reports DB is read
**read-only**.

```
 Reports store (per patient, chronological)
        │  _to_encounter()  → compact encounter series
        ▼
 ┌───────────────┬──────────────┬─────────────┬────────────────┬───────────────┐
 health_score    trend_engine    risk_engine   prediction_eng.   timeline_engine
 (0–100 + 6      (improving/      (low→critical (next-visit       (health journey
  factors)        stable/          future risk)  forecast)         milestones)
                  worsening)
 └───────────────┴──────────────┴─────────────┴────────────────┴───────────────┘
        │                          + RAG evidence (recommendations)
        ▼
   DigitalTwin  ──►  snapshot upsert (DIGITAL_TWIN_DB_URL)  ──►  analytics
```

### Health score (0–100) — six weighted factors

Medicine adherence *(regimen-continuity proxy)* · risk level · disease
progression · drug interactions · prediction confidence · clinical warnings. Each
is a 0–100 sub-score; the weighted blend is the overall score, computed **per
encounter** to produce the Health-Score-Timeline chart.

### Trend analysis & risk

Every tracked metric is classified **improving / stable / worsening** via a
least-squares slope with a polarity-aware dead-band: Health-Score, Disease,
Medicine (adherence), OCR-Confidence and Risk trends. The **risk engine** predicts
future risk on a four-level scale (**low / medium / high / critical**) from the
latest clinical + interaction state, nudged by the health trajectory, with
human-readable drivers. The **prediction engine** forecasts the next-visit health
score + risk.

### Backend module — `backend/digital_twin/`

Every file created, and what it does:

| File | Responsibility |
|------|----------------|
| `schemas.py` | Pydantic contracts — `DigitalTwin`, `TrendResult`, `RiskAssessment`, `Prediction`, timeline/medicine/disease history, analytics (the frontend boundary). |
| `models.py` | SQLAlchemy ORM `TwinSnapshot` (one upserted snapshot per patient; SQLite now, PostgreSQL-ready). |
| `health_score.py` | The 0–100 score + six-factor breakdown + per-encounter series (pure). |
| `trend_engine.py` | Least-squares slope → improving/stable/worsening + chart series (pure). |
| `risk_engine.py` | Future-risk prediction (low→critical) with drivers (pure). |
| `prediction_engine.py` | Short-horizon forecast of the next health score + risk (pure). |
| `timeline_engine.py` | Chronological health-journey events (reports, new medicines, high-risk flags) (pure). |
| `service.py` | Aggregates the reports store by patient, runs the engines, enriches via RAG, persists snapshots; analytics + recalculation (async). |
| `router.py` | Async FastAPI routes under `/digital-twin`. |
| `__init__.py` | Public surface: `router`, `get_service`. |

### API endpoints

| Method & path | Purpose |
|---------------|---------|
| `GET  /digital-twin/{patientId}` | The full, live Digital Twin (computed fresh + snapshot saved). |
| `GET  /digital-twin/analytics` | Population-level analytics across all patients' snapshots. |
| `POST /digital-twin/recalculate` | Recompute one patient (`{ "patient_id": "..." }`) or **all** patients. |
| `GET  /digital-twin/patients` | Patients with data (drives the UI picker). |

### Frontend — Digital Twin page (`/digital-twin`)

A patient picker + **Recalculate** action, a circular **health-score gauge** with
its status, a segmented **risk meter**, the six score-factor bars, a **forecast**
card, five **recharts** trend charts (Health-Score, Risk, OCR-Confidence, Disease,
Medicine), **medicine history** (active/past), **disease progress**, a vertical
**timeline**, the **AI summary**, RAG-backed **recommendations** and **evidence**.
New API helpers: `getDigitalTwin`, `getDigitalTwinPatients`,
`getDigitalTwinAnalytics`, `recalculateDigitalTwin`.

### Configuration (all optional — sensible defaults)

| Env var | Default | Purpose |
|---------|---------|---------|
| `DIGITAL_TWIN_DB_URL` | local SQLite (`…/digital_twin.db`) | Snapshot store (falls back to `DATABASE_URL`; PostgreSQL-ready). |
| `DIGITAL_TWIN_USE_RAG` | `true` | Enrich twin recommendations with RAG evidence. |

> ⚕️ **Disclaimer:** the Digital Twin is an automated, aggregated view for
> educational support only — not a diagnosis or a medical record. All values must
> be verified by a qualified clinician.

---

## 🛡️ Clinical AI Audit, Explainability & Governance

An **enterprise-grade AI governance layer** that makes every AI decision in the
platform **explainable, traceable, auditable, reproducible and versioned** — the
difference between a demo and a system a healthcare organisation could actually
run. It is strictly **additive**: it reads the existing Medical-Report store
read-only, owns its own database, and changes no existing route or behaviour.

### How it fits in (non-invasive by design)

The governance layer **derives** its data rather than duplicating it. Every OCR
analysis already flows through OCR → Medicine Matching → Disease Prediction →
Drug Interaction → RAG → Clinical Decision → Report. The tracker captures that as
a single **reproducible decision trace** — live (a best-effort hook after OCR)
and by **backfilling** the existing report store — then the pure engines explain
it, score its confidence and render its pipeline.

```
                        ┌─────────────────────────────────────────────┐
   Existing pipeline    │  OCR → Matching → Disease → Interactions →   │
   (unchanged)          │  RAG → Clinical Decision → Medical Report    │
                        └───────────────┬─────────────────────────────┘
                                        │ read-only + best-effort hook
                                        ▼
              ┌──────────────────────────────────────────────────┐
              │              backend/ai_governance/              │
              │                                                  │
              │  decision_tracker ──► ai_decision_traces (DB)    │
              │        │                                         │
              │        ├──► explanation_engine   (the "why")     │
              │        ├──► confidence_analyzer  (reliability)   │
              │        └──► pipeline_tracker     (visual flow)   │
              │                                                  │
              │  audit_logger ──────► audit_logs (DB)  ◄── ASGI  │
              │  model_registry ────► model_registry (DB)  middleware
              │  dataset_registry ──► dataset_registry (DB)      │
              │  version_manager ───► pinned component versions  │
              │                                                  │
              │  service (DI composition root) ──► router        │
              └───────────────────────┬──────────────────────────┘
                                      ▼
        Frontend: AI Governance · Pipeline Viewer · Model Registry ·
                  Dataset Registry · Audit Logs
```

### Architecture (SOLID + Dependency Injection)

The `service.py` is a **composition root**: it owns no persistence of its own and
instead injects focused collaborators, each testable in isolation.

| Component | Responsibility |
|-----------|----------------|
| `decision_tracker.py` | Build/persist/search reproducible **decision traces**; backfill from reports; dashboard aggregation |
| `explanation_engine.py` | Pure engine — the **"why"** behind every sub-decision (OCR word, medicine match, disease chosen/rejected, interaction flagged, RAG doc, recommendation) |
| `confidence_analyzer.py` | Pure engine — **reliability, calibration, evidence strength, model uncertainty, missing information** |
| `pipeline_tracker.py` | Pure engine — the 8-step **visual pipeline** with per-step time / status / confidence / warnings |
| `audit_logger.py` | Immutable **audit log** of every API request (background, non-blocking) + ASGI middleware + PHI masking |
| `model_registry.py` | Registry of every AI **model** (name, version, accuracy, training date, dataset, status) — seeded with the shipped models |
| `dataset_registry.py` | Registry of every **dataset** (version, source, size, date added, purpose) — seeded with the shipped datasets |
| `version_manager.py` | Single source of truth for **model / dataset / prompt / pipeline / RAG-index** versions (env-overridable) |
| `service.py` / `router.py` | DI composition root + async FastAPI routes |
| `models.py` / `schemas.py` | SQLAlchemy ORM (4 portable tables) + Pydantic v2 contracts |

### AI Decision Trace (what is stored for every prediction)

Timestamp · Patient ID · OCR result & provider · Medicines (+ candidates) ·
Disease prediction · Confidence · Drug interaction · Clinical decision · RAG
documents retrieved · Prompt used · Retrieved chunks · Final recommendation ·
Execution time · Model / Dataset / Pipeline / Prompt / RAG-index versions ·
Status & warnings.

### Sequence — capturing & explaining a decision

```
User        OCR Router      Governance         Engines            DB
 │  upload      │               │                  │               │
 ├─────────────►│ run pipeline  │                  │               │
 │              ├──(OCR→…→Report)                   │               │
 │              ├─ record_trace_from_ocr ──────────►│ derive trace  │
 │              │               ├─ _save ──────────────────────────►│
 │◄─ response ──┤ (never blocked by governance)     │               │
 │                              │                   │               │
 │  GET /governance/decisions/{id}/explanation      │               │
 ├─────────────────────────────►│ get trace ───────────────────────►│
 │                              │◄── trace ─────────────────────────┤
 │                              ├─ explain(trace) ─►│               │
 │◄──── ExplanationReport ──────┤                   │               │
```

### AI Pipeline view

```
Image Upload → OCR → Medicine Matching → Disease Prediction →
Drug Interaction → RAG Retrieval → Clinical Decision → Report Generation
```

Each step reports **execution time, status (completed / warning / skipped /
failed), confidence and warnings**. The Pipeline Viewer renders this as a visual
workflow of connected step cards.

### Governance workflow

```
Analyse (or Sync)  ──►  Trace stored + versioned  ──►  Dashboard KPIs
        │                                                    │
        └──► Search (patient / medicine / disease / version / date)
                        │
                        └──► Drill-down: Explainability + Confidence + Pipeline
                                        │
                                        └──► Export (CSV / JSON / PDF)
```

### Audit workflow

```
Every API request ─► ASGI AuditMiddleware ─► asyncio.create_task (fire-and-forget)
                                                     │ PHI-masked
                                                     ▼
                                         audit_logs table (background write)
                                                     │
                              Audit Logs page  ◄──────┘  + CSV / JSON / PDF export
```

Auditing is **non-blocking**: a logging failure can never break or slow the
request being audited.

### Explainability workflow

For any trace, `explanation_engine` derives grounded rationales — every "why"
points back at concrete numbers (match scores, prediction probabilities,
retrieval similarity) so it is reproducible:

```
Trace ─► Why OCR read a word (row confidence)
      ─► Why a medicine was matched (top vs runner-up score)
      ─► Why a disease was chosen (highest probability, margin over next)
      ─► Why another disease was rejected (lower probability)
      ─► Why an interaction was flagged (severity + mechanism)
      ─► Why each RAG document was retrieved (semantic similarity)
      ─► Why the final recommendation was generated (grounded-in sources)
```

### API endpoints

| Method & path | Description |
|---------------|-------------|
| `GET  /governance/dashboard` | KPIs: total decisions, avg confidence, avg time, failed, audit failures, low-confidence, most-common diseases/medicines |
| `GET  /governance/versions` | Pinned model / dataset / prompt / pipeline / RAG-index versions |
| `POST /governance/sync` | Backfill decision traces from the report store (idempotent) |
| `GET  /governance/decisions` | Search traces (patient, medicine, disease, prediction, status, model/dataset version, confidence, date) |
| `GET  /governance/decisions/export?fmt=csv\|json\|pdf` | Export decision traces |
| `GET  /governance/decisions/{trace_id}` | Full, reproducible decision trace |
| `GET  /governance/decisions/{trace_id}/explanation` | Explainability report |
| `GET  /governance/decisions/{trace_id}/confidence` | Confidence / reliability / calibration analysis |
| `GET  /governance/decisions/{trace_id}/pipeline` | Per-step pipeline view |
| `GET  /governance/audit-logs` | Search the immutable audit log |
| `GET  /governance/audit-logs/export?fmt=csv\|json\|pdf` | Export audit logs |
| `GET  /governance/models` · `POST /governance/models` | Model registry (list / register-update) |
| `GET  /governance/datasets` · `POST /governance/datasets` | Dataset registry (list / register-update) |

### Frontend — five new pages

- **AI Governance** (`/governance`) — dashboard KPIs, versions, decisions-over-time chart, most-common diseases/medicines, searchable decision table with an explainability + confidence drill-down drawer.
- **Pipeline Viewer** (`/governance/pipeline`) — the visual 8-step workflow for any decision (time / status / confidence / warnings).
- **Model Registry** (`/governance/models`) — every model with accuracy & lifecycle status; register new versions.
- **Dataset Registry** (`/governance/datasets`) — every dataset with source, size & purpose; register new versions.
- **Audit Logs** (`/governance/audit-logs`) — searchable request log with CSV / JSON / PDF export.

### Performance & security

- **Async** FastAPI throughout; the reports store is read through a dedicated read-only async engine.
- **Background logging** — audit writes are fire-and-forget (`asyncio.create_task`), never blocking a response.
- **Idempotent** backfill + lazy first-read auto-sync so the dashboard is populated without new OCR runs.
- **Sensitive-data masking** — emails, phone numbers and long identifiers are redacted from audit prompts/sources/errors before persistence and export; names can be reduced to initials.
- **Input validation** (Pydantic v2 + typed query params) and **actionable error handling** on every route.

### Configuration (all optional — sensible defaults)

| Variable | Default | Purpose |
|----------|---------|---------|
| `AI_GOVERNANCE_DB_URL` | local SQLite | Governance store (traces, audit logs, registries). Set to PostgreSQL in prod. |
| `GOVERNANCE_AUDIT_REQUESTS` | `true` | Log every API request via the audit middleware. |
| `GOVERNANCE_AUTO_ON_OCR` | `true` | Capture a live decision trace after each OCR analysis. |
| `GOV_MODEL_VERSION`, `GOV_DATASET_VERSION`, `GOV_PROMPT_VERSION`, `GOV_PIPELINE_VERSION`, `GOV_RAG_INDEX_VERSION`, … | descriptive defaults | Pin exact component versions without a code deploy. |

### Future roadmap

- Bias / fairness monitoring and drift detection across model versions
- Human-in-the-loop review queue with sign-off + override capture on decisions
- Role-based access control and authenticated per-user audit identity
- Cryptographic hash-chaining of audit rows for tamper-evidence
- SHAP / attention-based token attributions layered onto the explanation engine
- Scheduled compliance exports (HIPAA / GDPR) and configurable retention policies

> ⚕️ **Disclaimer:** the governance layer observes and explains AI behaviour for
> transparency and oversight — it does not itself make clinical decisions. All AI
> output remains educational decision-support only and must be verified by a
> qualified clinician.

---

## 🧾 Medical Document Intelligence

Generalizes document intake beyond prescriptions: **Handwritten Prescriptions,
Blood Test Reports, CBC, Liver Function Test (LFT), Kidney Function Test
(KFT), Lipid Profile, Thyroid Reports, Discharge Summaries and Medical
Certificates** are all detected automatically and analyzed end to end —
structured lab values with High/Low/Normal grading, labeled sections for
narrative documents, a RAG-grounded clinical summary, and an AI explanation of
any abnormal findings.

### What it analyses

- **Lab-style reports** (Blood Test, CBC, LFT, KFT, Lipid Profile, Thyroid):
  per-test name, patient value, unit, reference range, and High/Low/Normal
  status, rolled up into an abnormal-findings count.
- **Narrative documents** (Discharge Summary, Medical Certificate, Handwritten
  Prescription): common fields (patient, age, gender, date, doctor, hospital)
  plus a catch-all of labeled sections (e.g. Diagnosis, Discharge Date, Fit
  From/To) detected from headings in the extracted text.
- Every document gets a **clinical summary**, **possible clinical meaning**
  per abnormal finding, **follow-up suggestions**, and a plain-language **AI
  explanation** — grounded in the RAG knowledge base when available, and
  always backed by a deterministic, rule-based fallback so results never
  depend on a configured LLM.

### Backend module — `backend/document_intelligence/` (clean architecture)

| File | Responsibility |
|------|----------------|
| `schemas.py` | Pydantic contracts — document types, lab results, structured fields, clinical summary, history list/detail/page, stats. |
| `document_classifier.py` | Keyword-scoring auto-detection of the document type from extracted text (+ filename); callers can override it explicitly. |
| `report_parser.py` | Text-extraction dispatch (images via the existing OCR engines, PDFs via `pypdf`, with optional `pymupdf` rasterization for scanned PDFs) + heading/label parsing of narrative sections. |
| `lab_report_analyzer.py` | Regex-based lab-row extraction, fuzzy-matched (`rapidfuzz`) against a built-in reference-range table, graded High/Low/Normal. |
| `clinical_summary.py` | RAG retrieval + provider-agnostic LLM generation (`backend/llm`) for the summary/explanation, with a deterministic rule-based fallback for possible meanings and follow-up suggestions. |
| `service.py` | Orchestrates the full workflow and owns persistence: async engine/session setup, CRUD, filtering, pagination, statistics, file retention. |
| `router.py` | Async FastAPI routes under `/documents`, delegating to the service with logging + exception handling. |
| `models.py` | SQLAlchemy ORM model (`DocumentRecord`) + portable column types (SQLite **and** PostgreSQL). |

Image/PDF recognition reuses the existing OCR engines directly via a small,
behavior-preserving addition to `backend/ocr/pipeline.py`
(`extract_raw_text()`, factored out of the existing `run_pipeline()` so both
share one recognition code path) — no OCR logic is duplicated.

### Storage & database

- **Default:** a local SQLite file (`backend/document_intelligence/document_intelligence.db`)
  via the async `aiosqlite` driver. Retained files live in
  `backend/document_intelligence/images/`.
- **PostgreSQL (production):** set one environment variable — no code changes:

  ```bash
  export DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/medisense"
  pip install asyncpg
  ```

### API endpoints

| Method & path | Description |
|---------------|-------------|
| `POST /documents/analyze` | Upload an image or PDF; runs the full workflow. Query params: `document_type` (override auto-detection), `provider` (OCR engine override). |
| `GET /documents/history` | Paginated list. Query params: `q`, `document_type`, `status`, `date_from`, `date_to`, `sort` (`newest`/`oldest`/`confidence`), `page`, `page_size`. |
| `GET /documents/stats` | Aggregate stats: totals, breakdown by document type, total abnormal findings, average confidence. |
| `GET /documents/{id}` | Full record (raw text, structured fields, lab analysis, clinical summary). |
| `GET /documents/{id}/image` | Serves the retained original file (image or PDF). |
| `GET /documents/{id}/json` | Downloads the structured report as JSON. |
| `DELETE /documents/{id}` | Delete one record (and its retained file). |
| `DELETE /documents` | Clear the entire document history. |

### Frontend — Medical Document Intelligence (`/documents`)

- Drag-and-drop or browse upload for images and PDFs, with a manual
  document-type override dropdown (auto-detect by default)
- Auto-detected type badge + confidence, extraction warnings
- Structured "Extracted Data" panel (common fields + labeled sections)
- Lab-results table with color-coded High/Low/Normal badges
- Collapsible raw extracted text
- AI Clinical Summary panel: summary, abnormal findings, possible clinical
  meaning per finding, follow-up suggestions, AI explanation, safety note
- Evidence Sources panel (RAG source documents + retrieval confidence)
- "Download Structured Report" (JSON) and a "Recent Documents" history panel

### How the workflow operates

1. **Upload** — `POST /documents/analyze` saves the file, same pattern as the OCR endpoint (deleted after processing; only a retained copy persists).
2. **Extract Text** — images go through the existing OCR engines; PDFs are read directly via `pypdf`, falling back to OCR of a rasterized page for scanned PDFs.
3. **Detect Document Type** — `document_classifier.classify()` scores the extracted text against each known type (or uses the caller's override).
4. **Parse Structured Data** — lab-style types go through `lab_report_analyzer`; narrative types go through `report_parser`'s section parser.
5. **Retrieve Medical Knowledge (RAG)** — `clinical_summary.generate_summary()` queries the existing knowledge base retriever for relevant context.
6. **Generate Clinical Summary + Highlight Abnormal Findings** — abnormal lab rows are flagged and paired with a possible clinical meaning.
7. **Generate AI Explanation** — the provider-agnostic LLM layer (or a deterministic offline fallback) writes the plain-language summary and explanation.
8. The full result is persisted (best-effort, never blocks the response) and surfaced on the **Medical Document Intelligence** page and history endpoints.

### Configuration (all optional — sensible defaults)

| Variable | Default | Purpose |
|----------|---------|---------|
| `DOCUMENT_INTELLIGENCE_DB_URL` | local SQLite | Persistence store (or `DATABASE_URL` for a shared Postgres). |
| `DOCUMENT_INTELLIGENCE_IMAGE_DIR` | `backend/document_intelligence/images` | Where retained files are stored. |
| `DOCUMENT_USE_RAG` | `true` | Enrich the clinical summary with the RAG knowledge base. |
| `DOCUMENT_USE_LLM` | `true` | Use the provider-agnostic LLM layer for the summary/explanation narrative. |
| `DOCUMENT_LAB_MATCH_THRESHOLD` | `80` | Fuzzy-match floor (0-100) for resolving a lab row to a known test. |

---

## 📚 Evidence-Based Medical Response Engine

Every AI-generated medical response is grounded in evidence retrieved from the
RAG knowledge base **before** it is written. Instead of asking an LLM to
answer directly, the engine runs a strict retrieve → rerank → cite → generate
pipeline and returns the response together with the exact evidence behind it —
reducing hallucination and making every answer auditable.

### Architecture

```
 User Question
      │
      ▼
 Retrieve relevant documents from ChromaDB     (retriever.py — reuses backend/rag)
      │
      ▼
 Rank retrieved passages using semantic
 similarity (+ lexical overlap)                (reranker.py)
      │
      ▼
 Build numbered citations with highlighted
 matching terms                                (citation_builder.py)
      │
      ▼
 Provide top-k evidence to the LLM and
 generate a grounded response                  (response_builder.py — backend/llm)
      │
      ▼
 Return response + citations + confidence
 score + retrieved chunks                      (service.py, router.py)
```

### Backend module — `backend/evidence_engine/` (clean architecture)

| File | Responsibility |
|------|----------------|
| `schemas.py` | Pydantic contracts — request/response models, retrieved chunks, citations, history list/detail/page. |
| `retriever.py` | Thin async adapter over the existing `backend/rag` retriever (embedder + ChromaDB) — no second vector store or model. |
| `reranker.py` | Pure hybrid reranking: blends the original embedding similarity with a lexical query/chunk term-overlap score, no extra model required. |
| `citation_builder.py` | Builds numbered citations (`[1]`, `[2]`, …) from the reranked chunks, with matching query terms **highlighted** in each snippet. |
| `response_builder.py` | Builds the grounded prompt, generates the response via the provider-agnostic LLM layer (`backend/llm`), falls back to a deterministic extractive answer when no LLM is configured, and computes a confidence score from evidence strength alone. |
| `service.py` | Orchestrates the full pipeline, owns the in-memory chat-session store (for `/evidence/chat` follow-ups) and async persistence (SQLAlchemy). |
| `router.py` | Async FastAPI routes under `/evidence`, delegating to the service with logging + exception handling. |

Retrieval reuses `backend/rag`'s embedder (`all-MiniLM-L6-v2`) and ChromaDB
collection directly — this module never re-embeds or re-indexes documents.
Generation reuses the provider-agnostic LLM layer (`backend/llm`), so it is
offline-safe by design: with no cloud/local model configured, responses are
composed directly from the retrieved evidence text.

### API endpoints

| Method & path | Description |
|---------------|-------------|
| `POST /evidence/query` | Retrieve evidence for a question and generate a single grounded, cited response. |
| `POST /evidence/chat` | Same pipeline, but session-aware — pass the returned `session_id` back to continue the conversation with context. |
| `GET /evidence/history` | Paginated list of past queries/chats. Query params: `page`, `page_size`. |
| `GET /evidence/{id}` | Full stored result for one past query (response, citations, retrieved chunks, confidence). |
| `DELETE /evidence/history` | Clear the entire evidence-query history. |

### Frontend — Evidence Explorer (`/evidence`)

- Single Query / Chat Session toggle
- AI Response panel with **Copy Response** and **Download Report** (PDF)
- Confidence indicator (evidence-strength meter)
- Supporting Sources badges + numbered citation cards with highlighted matching terms
- Expandable Retrieved Chunks (collapsible per-passage detail with relevance score)
- Recent-queries history panel

### Configuration (all optional — sensible defaults)

| Variable | Default | Purpose |
|----------|---------|---------|
| `EVIDENCE_ENGINE_DB_URL` | local SQLite | Persistence store (or `DATABASE_URL` for a shared Postgres). |
| `EVIDENCE_ENGINE_TOP_K` | `6` | Chunks retrieved from the vector store before reranking. |
| `EVIDENCE_ENGINE_RERANK_TOP_K` | `4` | Chunks kept after reranking (used for citations + generation). |
| `EVIDENCE_ENGINE_MIN_SIMILARITY` | `0.15` | Similarity floor (0..1) below which a chunk is dropped. |
| `EVIDENCE_ENGINE_SESSION_TTL` | `3600` | Seconds an idle chat session is retained in memory. |
| `EVIDENCE_ENGINE_MAX_SESSIONS` | `300` | Max concurrent chat sessions (LRU eviction of the oldest). |

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