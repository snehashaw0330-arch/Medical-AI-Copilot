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

// ---------------- Image quality assessment ----------------
// Fast OpenCV analysis that runs BEFORE OCR so the user can fix a bad photo.
// Returns { overall_score, rating, passed, threshold, metrics, subscores,
// recommendations, warnings }.
export async function assessImageQuality(file, { signal } = {}) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await API.post('/ocr/image-quality', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    signal,
  })
  return data
}

// ---------------- Dataset evaluation ----------------
// Batch OCR evaluation runs in the background on the server; the UI starts a
// job, polls its status for live progress, and downloads the final report.
export async function getDatasetInfo(dataset) {
  const { data } = await API.get('/ocr/dataset-info', {
    params: dataset ? { dataset } : undefined,
  })
  return data
}

export async function startDatasetEvaluation({ dataset, limit } = {}) {
  const { data } = await API.post('/ocr/evaluate-dataset', null, {
    params: { ...(dataset ? { dataset } : {}), ...(limit ? { limit } : {}) },
  })
  return data
}

export async function getDatasetEvaluationStatus(jobId) {
  const { data } = await API.get(`/ocr/evaluate-dataset/status/${jobId}`)
  return data
}

/** Absolute URL of the downloadable JSON report (used by an <a> / window.open). */
export function datasetReportUrl(jobId) {
  return `${API.defaults.baseURL}/ocr/evaluate-dataset/report/${jobId}`
}

// ---------------- Prescription OCR history ----------------
// Persistent server-side history of every OCR analysis.
export async function getHistory(params = {}) {
  // params: { q, medicine, status, date_from, date_to, sort, page, page_size }
  const clean = Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''),
  )
  const { data } = await API.get('/history', { params: clean })
  return data
}

export async function getHistoryStats() {
  const { data } = await API.get('/history/stats')
  return data
}

export async function getHistoryMedicines() {
  const { data } = await API.get('/history/medicines')
  return data.medicines ?? []
}

export async function getHistoryItem(id) {
  const { data } = await API.get(`/history/${id}`)
  return data
}

export async function deleteHistoryItem(id) {
  const { data } = await API.delete(`/history/${id}`)
  return data
}

export async function clearHistory() {
  const { data } = await API.delete('/history')
  return data
}

/** Absolute URL of a record's retained prescription image (for <img> / fetch). */
export function historyImageUrl(id) {
  return `${API.defaults.baseURL}/history/${id}/image`
}

// ---------------- Medicine info ----------------
export async function getMedicineInfo(name) {
  const { data } = await API.get(`/medicine-info/${encodeURIComponent(name)}`)
  return data
}

// ---------------- RAG / Knowledge Base ----------------
// Retrieval-augmented Q&A over the medical knowledge base. Indexing/generation
// can be slow, so these use a longer timeout than the default fast endpoints.
const RAG_TIMEOUT = 120_000 // 2 min

export async function getRagStatus() {
  const { data } = await API.get('/rag/status')
  return data
}

export async function rebuildRagIndex() {
  const { data } = await API.post('/rag/index', null, { timeout: RAG_TIMEOUT })
  return data
}

export async function queryKnowledgeBase(question, topK) {
  const { data } = await API.post(
    '/rag/query',
    { question, top_k: topK ?? null },
    { timeout: RAG_TIMEOUT },
  )
  return data
}

export async function getRagMedicineInfo(medicines) {
  const { data } = await API.post(
    '/rag/medicine-info',
    { medicines },
    { timeout: RAG_TIMEOUT },
  )
  return data
}

export async function uploadKnowledgeDoc(file, { reindex = true } = {}) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await API.post('/rag/upload', form, {
    params: { reindex },
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: RAG_TIMEOUT,
  })
  return data
}

// OCR an uploaded prescription, then retrieve RAG info for every medicine found.
export async function analyzePrescriptionRag(file, { signal } = {}) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await API.post('/rag/prescription', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: OCR_TIMEOUT,
    signal,
  })
  return data
}

// ---------------- Drug interaction analysis ----------------
// Drug–drug interactions + per-drug warnings. Analysis also runs automatically
// after OCR (the OCR result carries `drug_interactions`), but this lets the UI
// re-check an edited medicine list on demand. RAG enrichment can be slow, so we
// use a longer timeout than the default fast endpoints.
const INTERACTIONS_TIMEOUT = 120_000 // 2 min (RAG enrichment can be slow)

export async function checkInteractions(medicines, { includeRag = true } = {}) {
  const { data } = await API.post(
    '/interactions/check',
    { medicines, include_rag: includeRag },
    { timeout: INTERACTIONS_TIMEOUT },
  )
  return data
}

export async function getInteractionHistory(params = {}) {
  // params: { page, page_size }
  const { data } = await API.get('/interactions/history', { params })
  return data
}

export async function getInteractionReport(id) {
  const { data } = await API.get(`/interactions/${id}`)
  return data
}

// ---------------- Clinical Decision Support (CDSS) ----------------
// Fuses OCR medicines, disease prediction, drug interactions and RAG into one
// risk-graded clinical report. Analysis also runs automatically after OCR (the
// OCR result carries `clinical_report`), but this endpoint lets the dedicated
// Clinical Decision page and edited-list re-checks run it on demand. Disease
// prediction + RAG can be slow, so use a longer timeout than the fast defaults.
const CLINICAL_TIMEOUT = 120_000 // 2 min (disease model + RAG can be slow)

export async function analyzeClinical(payload) {
  // payload: { medicines, symptoms, disease, diagnosis, age, gender,
  //            include_rag, run_disease_prediction, persist, source_record_id }
  const { data } = await API.post('/clinical/analyze', payload, {
    timeout: CLINICAL_TIMEOUT,
  })
  return data
}

export async function getClinicalHistory(params = {}) {
  // params: { page, page_size }
  const { data } = await API.get('/clinical/history', { params })
  return data
}

export async function getClinicalStats() {
  const { data } = await API.get('/clinical/stats')
  return data
}

export async function getClinicalReport(id) {
  const { data } = await API.get(`/clinical/${id}`)
  return data
}

// ---------------- Medical Report Generator ----------------
// Durable, exportable reports (PDF / JSON / HTML) assembled from an OCR analysis.
// A report is also generated automatically after every OCR run (the OCR result
// carries `report_id`); these endpoints power the Medical Reports page + viewer.
export async function generateReport(payload) {
  // payload: { ocr_result, filename, processing_time, source_record_id,
  //            image_data_url, persist }
  const { data } = await API.post('/reports/generate', payload, { timeout: 60_000 })
  return data
}

export async function getReports(params = {}) {
  // params: { q, patient, date_from, date_to, page, page_size }
  const clean = Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''),
  )
  const { data } = await API.get('/reports', { params: clean })
  return data
}

export async function getReportStats() {
  const { data } = await API.get('/reports/stats')
  return data
}

export async function getReport(id) {
  const { data } = await API.get(`/reports/${id}`)
  return data
}

export async function deleteReport(id) {
  const { data } = await API.delete(`/reports/${id}`)
  return data
}

/** Absolute URL of a report's retained prescription image (for <img> / fetch). */
export function reportImageUrl(id) {
  return `${API.defaults.baseURL}/reports/${id}/image`
}

/** Absolute URL of a report export (format: 'pdf' | 'json' | 'html'). */
export function reportExportUrl(id, format) {
  return `${API.defaults.baseURL}/reports/${id}/${format}`
}

/**
 * Fetch a report export as a Blob (robust cross-origin download). Returns the
 * Blob so the caller can trigger a client-side save with the right filename.
 */
export async function fetchReportBlob(id, format) {
  const params = format === 'html' ? { download: 1 } : undefined
  const res = await API.get(`/reports/${id}/${format}`, {
    responseType: 'blob',
    timeout: 60_000,
    params,
  })
  return res.data
}

// ---------------- Prescription Validation ----------------
// Deterministic prescription-safety validation (duplicates, missing dosing info,
// unsafe abbreviations, suspicious / low-confidence names, prescription errors).
// Validation also runs automatically after OCR (the OCR result carries
// `validation_report`), but this endpoint lets the UI re-validate an edited
// medicine list on demand. The checks are fast, so the default timeout is fine.
export async function checkValidation({ medicines, rawText = '', fields = null, overallConfidence = null, persist = false } = {}) {
  const { data } = await API.post('/validation/check', {
    medicines,
    raw_text: rawText,
    fields,
    overall_confidence: overallConfidence,
    persist,
  })
  return data
}

export async function getValidationHistory(params = {}) {
  // params: { page, page_size }
  const { data } = await API.get('/validation/history', { params })
  return data
}

export async function getValidationReport(id) {
  const { data } = await API.get(`/validation/${id}`)
  return data
}

// ---------------- Symptom Checker & Triage ----------------
// Categorized symptom checker: resolves symptoms, runs disease prediction + RAG,
// and returns a triage assessment (possible conditions, urgency, specialist,
// tests, home care, red flags, related documents). Disease inference + RAG can
// be slow, so `analyzeSymptoms` uses a longer timeout than the fast defaults.
const SYMPTOM_TIMEOUT = 120_000 // 2 min (disease model + RAG can be slow)

export async function getSymptomCatalog() {
  const { data } = await API.get('/symptoms/catalog')
  return data
}

export async function suggestSymptomTerms(q, limit = 8) {
  const { data } = await API.get('/symptoms/suggest', { params: { q, limit } })
  return data.suggestions ?? []
}

export async function analyzeSymptoms(payload) {
  // payload: { symptoms, severity, duration, age, gender, include_rag, top_k, persist }
  const { data } = await API.post('/symptoms/analyze', payload, {
    timeout: SYMPTOM_TIMEOUT,
  })
  return data
}

export async function getSymptomHistory(params = {}) {
  // params: { page, page_size }
  const { data } = await API.get('/symptoms/history', { params })
  return data
}

export async function getSymptomAssessment(id) {
  const { data } = await API.get(`/symptoms/${id}`)
  return data
}

// ---------------- Medicine Alternatives & Recommendations ----------------
// Resolves medicines against the dataset, finds generic/brand/similar
// alternatives and enriches with RAG evidence. A report is also generated
// automatically after OCR (the OCR result carries `recommendation_report`);
// these endpoints power the Medicine Recommendations page. Dataset + RAG lookups
// can be slow, so use a longer timeout than the fast defaults.
const RECOMMEND_TIMEOUT = 120_000 // 2 min (dataset + RAG can be slow)

export async function recommendMedicines(payload) {
  // payload: { medicines, include_rag, max_alternatives, persist, source_record_id }
  const { data } = await API.post('/medicine/recommend', payload, {
    timeout: RECOMMEND_TIMEOUT,
  })
  return data
}

export async function getMedicineRecommendations(params = {}) {
  // params: { page, page_size }
  const { data } = await API.get('/medicine/recommendations', { params })
  return data
}

export async function getMedicineRecommendation(id) {
  const { data } = await API.get(`/medicine/recommendations/${id}`)
  return data
}

// ---------------- Multi-Agent Medical Copilot ----------------
// Orchestrates the existing capabilities (OCR, disease, interactions, RAG,
// clinical, reports) as collaborating agents. A run executes in the background;
// the AI Agent Monitor page polls `getAgentRun` for live pipeline state.
const AGENT_TIMEOUT = 300_000 // 5 min — the full pipeline can include OCR

export async function startAgentRun({ file, symptoms, medicines, text, age, gender, diagnosis } = {}) {
  const form = new FormData()
  if (file) form.append('file', file)
  if (symptoms) form.append('symptoms', Array.isArray(symptoms) ? symptoms.join(',') : symptoms)
  if (medicines) form.append('medicines', Array.isArray(medicines) ? medicines.join(',') : medicines)
  if (text) form.append('text', text)
  if (age) form.append('age', age)
  if (gender) form.append('gender', gender)
  if (diagnosis) form.append('diagnosis', diagnosis)
  const { data } = await API.post('/agents/run', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: AGENT_TIMEOUT,
  })
  return data // { run_id, status, task_type }
}

export async function getAgentRun(runId) {
  const { data } = await API.get(`/agents/runs/${runId}`)
  return data
}

export async function getAgentRuns(limit = 20) {
  const { data } = await API.get('/agents/runs', { params: { limit } })
  return data
}

export async function getAgentRegistry() {
  const { data } = await API.get('/agents/registry')
  return data
}

// ---------------- Digital Twin ----------------
// A continuously-evolving virtual health profile per patient, aggregated from
// every prior analysis (OCR, disease, medicines, interactions, clinical, reports)
// and enriched with RAG evidence. Building a twin recomputes live + persists a
// snapshot, so allow a longer timeout than the fast defaults.
const TWIN_TIMEOUT = 120_000 // 2 min (aggregation + RAG can be slow)

export async function getDigitalTwinPatients() {
  const { data } = await API.get('/digital-twin/patients')
  return data
}

export async function getDigitalTwin(patientId) {
  const { data } = await API.get(`/digital-twin/${encodeURIComponent(patientId)}`, {
    timeout: TWIN_TIMEOUT,
  })
  return data
}

export async function getDigitalTwinAnalytics() {
  const { data } = await API.get('/digital-twin/analytics')
  return data
}

export async function recalculateDigitalTwin(patientId = null) {
  const { data } = await API.post('/digital-twin/recalculate', { patient_id: patientId }, {
    timeout: TWIN_TIMEOUT,
  })
  return data
}

// ---------------- Health (used by Dashboard) ----------------
export async function getHealth() {
  const { data } = await API.get('/')
  return data
}

export default API
