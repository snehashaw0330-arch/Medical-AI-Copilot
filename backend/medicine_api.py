from fastapi import APIRouter
import pandas as pd
from rapidfuzz import process

router = APIRouter()

# Load dataset
df = pd.read_csv(
    "datasets/medicines/medicine_dataset.csv",
    low_memory=False
)

medicine_names = (
    df['name']
    .dropna()
    .astype(str)
    .str.lower()
    .tolist()
)

@router.get("/medicine-info/{medicine_name}")
def medicine_info(medicine_name: str):

    # Fuzzy search
    match = process.extractOne(
        medicine_name.lower(),
        medicine_names,
        score_cutoff=70
    )

    if not match:
        return {
            "error": "Medicine not found"
        }

    matched_name = match[0]

    # Find medicine row
    row = df[
        df['name'].str.lower() == matched_name
    ].iloc[0]

    return {

        "medicine": row["name"],

        "uses": [
            str(row["use0"]) if "use0" in row else "",
            str(row["use1"]) if "use1" in row else "",
            str(row["use2"]) if "use2" in row else ""
        ],

        "side_effects": [
            str(row["sideEffect0"]) if "sideEffect0" in row else "",
            str(row["sideEffect1"]) if "sideEffect1" in row else "",
            str(row["sideEffect2"]) if "sideEffect2" in row else ""
        ],

        "substitutes": [
            str(row["substitute0"]) if "substitute0" in row else "",
            str(row["substitute1"]) if "substitute1" in row else "",
            str(row["substitute2"]) if "substitute2" in row else ""
        ],

        "chemical_class": str(
            row["Chemical Class"]
        ) if "Chemical Class" in row else "",

        "therapeutic_class": str(
            row["Therapeutic Class"]
        ) if "Therapeutic Class" in row else "",

        "action_class": str(
            row["Action Class"]
        ) if "Action Class" in row else ""
    }