# 🩺 Medical AI Assistant

An AI-powered healthcare assistant built with **FastAPI**, **React (Vite)**, and **Machine Learning** to help users with disease prediction, handwritten prescription OCR, medicine information lookup, and an intelligent medical chatbot.

## ✨ Features

- 🧠 Disease Prediction using Machine Learning
- 📄 Handwritten Prescription OCR
- 🔎 AI Image Quality Assessment (pre-OCR)
- 🗂️ Prescription OCR History (persistent, searchable)
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