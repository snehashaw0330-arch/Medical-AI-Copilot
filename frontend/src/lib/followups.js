/**
 * Curated follow-up questions for conditions that are easily confused on a
 * small symptom dataset. Each question maps to a real dataset symptom; tapping
 * "Yes" adds it and re-runs the prediction to disambiguate.
 *
 * Keyed by a lowercase keyword matched against the predicted disease name
 * (e.g. the dataset labels vertigo as "(vertigo) Paroymsal Positional Vertigo").
 */
export const AMBIGUOUS_FOLLOWUPS = {
  vertigo: [
    { q: 'Does the room feel like it is spinning?', symptom: 'spinning movements' },
    { q: 'Do you feel off-balance or unsteady?', symptom: 'loss of balance' },
    { q: 'Do you feel unsteady when you stand up?', symptom: 'unsteadiness' },
  ],
  migraine: [
    { q: 'Is the headache throbbing or one-sided?', symptom: 'headache' },
    { q: 'Do you see flashes or have visual disturbances?', symptom: 'visual disturbances' },
    { q: 'Is your vision blurred or distorted?', symptom: 'blurred and distorted vision' },
  ],
  malaria: [
    { q: 'Do you get chills with the fever?', symptom: 'chills' },
    { q: 'Do you sweat heavily?', symptom: 'sweating' },
    { q: 'Do you have muscle pain?', symptom: 'muscle pain' },
  ],
  dengue: [
    { q: 'Do you have pain behind the eyes?', symptom: 'pain behind the eyes' },
    { q: 'Do you have joint or muscle pain?', symptom: 'joint pain' },
    { q: 'Do you notice red spots over your body?', symptom: 'red spots over body' },
  ],
  typhoid: [
    { q: 'Do you have abdominal pain?', symptom: 'abdominal pain' },
    { q: 'Are you constipated?', symptom: 'constipation' },
    { q: 'Has the fever stayed high for several days?', symptom: 'high fever' },
  ],
}

const norm = (s) =>
  s.toLowerCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim()

/** Return follow-up questions for a disease, excluding already-selected symptoms. */
export function getFollowups(diseaseName = '', alreadySelected = []) {
  const name = diseaseName.toLowerCase()
  const sel = new Set(alreadySelected.map(norm))
  for (const key of Object.keys(AMBIGUOUS_FOLLOWUPS)) {
    if (name.includes(key)) {
      return AMBIGUOUS_FOLLOWUPS[key].filter((f) => !sel.has(norm(f.symptom)))
    }
  }
  return []
}
