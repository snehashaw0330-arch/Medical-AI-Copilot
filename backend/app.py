from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.medicine_api import router as medicine_router
from backend.ocr.router import router as ocr_router
from backend.disease.router import router as disease_router
from backend.rag.router import router as rag_router
from backend.history.router import router as history_router
from backend.drug_interactions.router import router as interactions_router
from backend.clinical_decision.router import router as clinical_router
from backend.report_generator.router import router as reports_router
from backend.prescription_validation.router import router as validation_router
from backend.symptom_checker.router import router as symptoms_router
from backend.medicine_recommendation.router import router as medicine_rec_router

app = FastAPI(title="Medical AI Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    """Root endpoint that confirms the Medical AI Assistant is running."""
    return {"message": "Medical AI Assistant Running"}


# =========================
# ROUTERS
# Each feature owns its own initialization; app.py only wires routers.
# =========================
app.include_router(disease_router)   # /disease/*       (prediction)
app.include_router(medicine_router)  # /medicine-info/* (drug lookup)
app.include_router(ocr_router)       # /ocr/*           (prescription OCR)
app.include_router(rag_router)       # /rag/*           (retrieval-augmented Q&A)
app.include_router(history_router)   # /history/*       (OCR analysis history)
app.include_router(interactions_router)  # /interactions/* (drug interaction analysis)
app.include_router(clinical_router)  # /clinical/*     (clinical decision support)
app.include_router(reports_router)   # /reports/*      (medical report generator)
app.include_router(validation_router)  # /validation/*  (prescription validation)
app.include_router(symptoms_router)  # /symptoms/*     (symptom checker & triage)
app.include_router(medicine_rec_router)  # /medicine/*  (medicine recommendation)
