# 🩺 Medical AI Assistant

An AI-powered healthcare assistant built with **FastAPI**, **React (Vite)**, and **Machine Learning** to help users with disease prediction, handwritten prescription OCR, medicine information lookup, and an intelligent medical chatbot.

## ✨ Features

- 🧠 Disease Prediction using Machine Learning
- 📄 Handwritten Prescription OCR
- 🔎 AI Image Quality Assessment (pre-OCR)
- 🗂️ Prescription OCR History (persistent, searchable)
- ⚠️ Drug Interaction Analysis (auto-run after OCR; severity, warnings & recommendations)
- 💊 Medicine Information Search
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
│   ├── ocr/            # OCR pipeline + image quality assessment
│   ├── history/        # OCR History module (models, schemas, service, router)
│   ├── drug_interactions/  # Drug Interaction Analysis (models, schemas, service, router, utils)
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

- Disease Prediction
- Prescription OCR
- Image Quality Assessment
- Prescription OCR History
- Medicine Search
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