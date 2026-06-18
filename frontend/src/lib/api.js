import axios from 'axios'

/**
 * API service layer. One axios instance, one function per backend capability.
 * Components never touch axios directly — they import these functions.
 *
 * Base URL: set VITE_API_URL in a .env file for production; defaults to the
 * local FastAPI server (which has permissive CORS in dev).
 */
// Default timeout is for FAST endpoints (predict, lookups). OCR is slow and
// gets its own long timeout per-request — see OCR_TIMEOUT below.
const DEFAULT_TIMEOUT = 30_000 // 30s
export const OCR_TIMEOUT = 300_000 // 5 min — local handwriting OCR can be slow

const API = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000',
  timeout: DEFAULT_TIMEOUT,
})

// ---------------- Disease prediction ----------------
export async function predictDisease(symptoms, topK = 3) {
  const { data } = await API.post('/disease/predict', {
    symptoms,
    top_k: topK,
  })
  return data
}

export async function getSymptoms() {
  const { data } = await API.get('/disease/symptoms')
  return data.symptoms ?? []
}

export async function suggestSymptoms(q, limit = 8) {
  const { data } = await API.get('/disease/symptoms/suggest', {
    params: { q, limit },
  })
  return data.suggestions ?? []
}

// ---------------- Prescription OCR ----------------
// Slow by nature. Uses OCR_TIMEOUT (5 min) and accepts an AbortController
// `signal` so the UI can cancel on user request (and ONLY on user request).
export async function extractPrescription(file, { provider, onProgress, signal } = {}) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await API.post('/ocr/extract-prescription', form, {
    params: provider ? { provider } : undefined,
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: OCR_TIMEOUT,
    signal,
    onUploadProgress: (e) => {
      if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100))
    },
  })
  return data
}

// ---------------- Medicine info ----------------
export async function getMedicineInfo(name) {
  const { data } = await API.get(`/medicine-info/${encodeURIComponent(name)}`)
  return data
}

// ---------------- Health (used by Dashboard) ----------------
export async function getHealth() {
  const { data } = await API.get('/')
  return data
}

export default API
