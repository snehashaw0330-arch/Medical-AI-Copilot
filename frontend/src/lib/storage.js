/**
 * Lightweight localStorage-backed history. The backend has no persistence yet,
 * so we record predictions and OCR reports client-side to power the Profile
 * page. Swap these for real API calls when a user/records service exists.
 */

const KEYS = {
  predictions: 'medisense-predictions',
  reports: 'medisense-ocr-reports',
  profile: 'medisense-profile',
}

const MAX_ITEMS = 50

function read(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback
  } catch {
    return fallback
  }
}

function write(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* quota / private mode — ignore */
  }
}

export function savePrediction(entry) {
  const list = read(KEYS.predictions, [])
  list.unshift({ id: crypto.randomUUID(), at: new Date().toISOString(), ...entry })
  write(KEYS.predictions, list.slice(0, MAX_ITEMS))
}
export const getPredictions = () => read(KEYS.predictions, [])

export function saveReport(entry) {
  const list = read(KEYS.reports, [])
  list.unshift({ id: crypto.randomUUID(), at: new Date().toISOString(), ...entry })
  write(KEYS.reports, list.slice(0, MAX_ITEMS))
}
export const getReports = () => read(KEYS.reports, [])

export function clearHistory() {
  write(KEYS.predictions, [])
  write(KEYS.reports, [])
}

const DEFAULT_PROFILE = {
  name: '',
  email: '',
  role: '',
}
export const getProfile = () => read(KEYS.profile, DEFAULT_PROFILE)
export const setProfile = (p) => write(KEYS.profile, p)
