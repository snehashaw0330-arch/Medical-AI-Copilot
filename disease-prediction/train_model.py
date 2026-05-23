import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

#load dataset
df = pd.read_csv(
    "disease-prediction/datasets/Training.csv"
)

# Features and target
X = df.drop("prognosis", axis=1)
y = df["prognosis"]

# Split dataset
X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42
)

# Train model
model = RandomForestClassifier()

model.fit(X_train, y_train)

# Predictions
predictions = model.predict(X_test)

# Accuracy
accuracy = accuracy_score(y_test, predictions)

print("\n===== MODEL TRAINED =====\n")

print(f"Accuracy: {accuracy * 100:.2f}%")