from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.medicine_api import router as medicine_router
from backend.ocr.router import router as ocr_router
from backend.disease.router import router as disease_router
from backend.rag.router import router as rag_router

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
