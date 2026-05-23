import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
import joblib

# Load dataset
df = pd.read_csv(
    "disease-prediction/datasets/Training.csv"
)

# Features + target
X = df.drop("prognosis", axis=1)
y = df["prognosis"]

# Encode disease labels
encoder = LabelEncoder()
y_encoded = encoder.fit_transform(y)

# Train model
model = RandomForestClassifier()
model.fit(X, y_encoded)

# Save model
joblib.dump(model, "disease-prediction/models/disease_model.pkl")
joblib.dump(encoder, "disease-prediction/models/label_encoder.pkl")

print("Disease model saved successfully")