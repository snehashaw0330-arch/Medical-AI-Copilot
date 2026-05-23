from backend.medicine_api import router as medicine_router
from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
import pandas as pd
import joblib
import shutil
import easyocr
from rapidfuzz import process

app = FastAPI()

# =========================
# OCR SETUP
# =========================

reader = easyocr.Reader(['en'])

medicine_df = pd.read_csv(
    "datasets/medicines/medicine_dataset.csv",
    usecols=[
        "name",
        "substitute0",
        "substitute1",
        "substitute2",
        "use0",
        "use1",
        "use2",
        "sideEffect0",
        "sideEffect1",
        "sideEffect2",
        "Chemical Class",
        "Therapeutic Class",
        "Action Class"
    ]
)

medicine_names = (
    medicine_df['name']
    .dropna()
    .astype(str)
    .str.lower()
    .tolist()
)

# =========================
# DISEASE MODEL SETUP
# =========================

model = joblib.load(
    "disease-prediction/models/disease_model.pkl"
)

encoder = joblib.load(
    "disease-prediction/models/label_encoder.pkl"
)

df = pd.read_csv(
    "disease-prediction/datasets/Training.csv"
)

symptom_columns = df.drop("prognosis", axis=1).columns

# =========================
# REQUEST MODEL
# =========================

class SymptomsInput(BaseModel):
    symptoms: list[str]

# =========================
# HOME API
# =========================

@app.get("/")
def home():
    return {
        "message": "Medical AI Assistant Running"
    }

# =========================
# DISEASE PREDICTION API
# =========================

@app.post("/predict-disease")
def predict_disease(data: SymptomsInput):

    input_data = [0] * len(symptom_columns)

    for symptom in data.symptoms:

        symptom = symptom.strip().lower()

        if symptom in symptom_columns:
            index = list(symptom_columns).index(symptom)
            input_data[index] = 1

    prediction = model.predict([input_data])

    disease = encoder.inverse_transform(prediction)[0]

    return {
        "predicted_disease": disease
    }

# =========================
# PRESCRIPTION OCR API
# =========================

@app.post("/extract-prescription")
async def extract_prescription(
    file: UploadFile = File(...)
):

    # Save uploaded image
    file_path = (
        f"prescription-ocr/raw-images/{file.filename}"
    )

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # OCR extraction
    results = reader.readtext(
        file_path,
        detail=0
    )

    detected_medicines = []

    for word in results:

        match = process.extractOne(
            word.lower(),
            medicine_names,
            score_cutoff=85
        )

        if match:

            medicine_name = match[0]

            if len(medicine_name) > 3:
                detected_medicines.append(
                    medicine_name
                )

    unique_medicines = list(
        set(detected_medicines)
    )

    return {
        "image": file.filename,
        "medicines": unique_medicines,
        "total_detected": len(unique_medicines),
        "ocr_text": results
    }
app.include_router(medicine_router)
