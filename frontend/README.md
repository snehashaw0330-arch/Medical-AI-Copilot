# 🩺 Medical AI Assistant

An AI-powered healthcare assistant built with **FastAPI**, **React (Vite)**, and **Machine Learning** to help users with disease prediction, handwritten prescription OCR, medicine information lookup, and an intelligent medical chatbot.

## ✨ Features

- 🧠 Disease Prediction using Machine Learning
- 📄 Handwritten Prescription OCR
- 💊 Medicine Information Search
- 🤖 AI Medical Chat Assistant
- 📊 Confidence-based Predictions
- 📑 Downloadable OCR Reports
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

---

## 📁 Project Structure

```
medical-ai-assistant/
│
├── backend/
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
- Medicine Search
- AI Chat Assistant

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