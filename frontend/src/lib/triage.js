/**
 * Symptom-triage knowledge base + helpers (rule-based, runs in the browser).
 *
 * The chat collects symptoms conversationally, then hands the canonical symptom
 * names to the backend /disease/predict for "possible conditions". Symptom
 * strings here are written in plain words; the backend normalizes/fuzzy-matches
 * them (e.g. "high fever" -> high_fever).
 */

// ---------- Emergency / red-flag detection (Requirement #5) ----------
export const EMERGENCY_RULES = [
  {
    test: /\b(chest pain|pain in (?:my )?chest|chest tightness|tightness in (?:my )?chest|pressure in (?:my )?chest)\b/i,
    title: 'Possible cardiac emergency',
    message:
      'Chest pain or pressure can be a sign of a heart attack — especially with sweating, nausea, or pain spreading to the arm or jaw. Please call your local emergency number now (e.g. 911 / 112 / 108).',
  },
  {
    test: /\b(can'?t breathe|cannot breathe|can not breathe|struggling to breathe|gasping|choking|severe(?:ly)? breathless|difficulty breathing|turning blue)\b/i,
    title: 'Severe breathing difficulty',
    message:
      'Severe difficulty breathing is a medical emergency. Call your local emergency number immediately and sit upright while you wait for help.',
  },
  {
    test: /\b(face (?:is )?droop|slurred speech|can'?t speak|trouble speaking|weakness on one side|numb(?:ness)? on one side|one side of (?:my )?(?:face|body)|sudden confusion)\b/i,
    title: 'Possible stroke (act F.A.S.T.)',
    message:
      'Face drooping, arm weakness or slurred speech can mean a stroke. Time is critical — call your local emergency number right away.',
  },
  {
    test: /\b(passed out|fainted|unconscious|unresponsive|loss of consciousness|blacked out|won'?t wake up)\b/i,
    title: 'Loss of consciousness',
    message:
      'Loss of consciousness needs urgent assessment. Call your local emergency number now; if the person is not breathing, start CPR if trained.',
  },
]

export function detectEmergency(text) {
  for (const rule of EMERGENCY_RULES) {
    if (rule.test.test(text)) return { title: rule.title, message: rule.message }
  }
  return null
}

// ---------- Symptom lexicon (free text -> canonical symptom) ----------
const LEXICON = [
  { re: /\b(chest pain|chest tightness)\b/i, symptom: 'chest pain', label: 'chest pain' },
  { re: /\b(breathless|breathing|short(?:ness)? of breath|out of breath)\b/i, symptom: 'breathlessness', label: 'breathing issues' },
  { re: /\b(fever|temperature|feverish|pyrexia)\b/i, symptom: 'high fever', label: 'fever' },
  { re: /\bcough\b/i, symptom: 'cough', label: 'cough' },
  { re: /\b(headache|head ache|head pain|migraine)\b/i, symptom: 'headache', label: 'headache' },
  { re: /\b(vomit|throwing up|throw up|puking)\b/i, symptom: 'vomiting', label: 'vomiting' },
  { re: /\bnausea|nauseous|feel sick\b/i, symptom: 'nausea', label: 'nausea' },
  { re: /\b(rash|skin rash|hives|itch)\b/i, symptom: 'skin rash', label: 'rash' },
  { re: /\b(stomach (?:pain|ache)|tummy|abdominal|belly)\b/i, symptom: 'stomach pain', label: 'stomach pain' },
  { re: /\b(diarrh|loose motion|loose stool)\b/i, symptom: 'diarrhoea', label: 'diarrhoea' },
  { re: /\bchills?|shivering\b/i, symptom: 'chills', label: 'chills' },
  { re: /\b(body (?:pain|ache)|muscle (?:pain|ache)|bodyache)\b/i, symptom: 'muscle pain', label: 'body pain' },
  { re: /\b(fatigue|tired|exhausted|weakness)\b/i, symptom: 'fatigue', label: 'fatigue' },
  { re: /\b(blurred|blurry) vision\b/i, symptom: 'blurred and distorted vision', label: 'blurred vision' },
  { re: /\b(dizzy|dizziness|spinning|vertigo)\b/i, symptom: 'dizziness', label: 'dizziness' },
  { re: /\b(runny nose|running nose)\b/i, symptom: 'runny nose', label: 'runny nose' },
  { re: /\b(sneez)/i, symptom: 'continuous sneezing', label: 'sneezing' },
  { re: /\bsore throat|throat pain\b/i, symptom: 'throat irritation', label: 'sore throat' },
]

export function detectSymptoms(text) {
  const out = []
  const seen = new Set()
  for (const { re, symptom, label } of LEXICON) {
    if (re.test(text) && !seen.has(symptom)) {
      seen.add(symptom)
      out.push({ symptom, label })
    }
  }
  return out
}

// ---------- Follow-up questions (Requirement #2) ----------
// Each question: { id, q, options:[{label, add?}] }  — `add` is a symptom to record.
export const FOLLOWUPS = {
  fever: [
    { id: 'fever_dur', q: 'How long have you had the fever?', options: [{ label: 'Less than a day' }, { label: '1–3 days' }, { label: 'More than 3 days' }] },
    { id: 'fever_high', q: 'Is it a high fever (above ~102°F / 39°C)?', options: [{ label: 'Yes', add: 'high fever' }, { label: 'Mild', add: 'mild fever' }, { label: 'Not sure' }] },
    { id: 'fever_chills', q: 'Any chills or shivering?', options: [{ label: 'Yes', add: 'chills' }, { label: 'No' }] },
    { id: 'fever_cough', q: 'Is there a cough as well?', options: [{ label: 'Yes', add: 'cough' }, { label: 'No' }] },
    { id: 'fever_body', q: 'Body pain or muscle aches?', options: [{ label: 'Yes', add: 'muscle pain' }, { label: 'No' }] },
    { id: 'fever_vomit', q: 'Any vomiting?', options: [{ label: 'Yes', add: 'vomiting' }, { label: 'No' }] },
  ],
  cough: [
    { id: 'cough_type', q: 'Is the cough dry, or productive with phlegm?', options: [{ label: 'Dry' }, { label: 'With phlegm', add: 'phlegm' }] },
    { id: 'cough_fever', q: 'Do you also have a fever?', options: [{ label: 'Yes', add: 'high fever' }, { label: 'No' }] },
    { id: 'cough_breath', q: 'Any breathlessness?', options: [{ label: 'Yes', add: 'breathlessness' }, { label: 'No' }] },
    { id: 'cough_chest', q: 'Any chest pain when coughing?', options: [{ label: 'Yes', add: 'chest pain' }, { label: 'No' }] },
  ],
  headache: [
    { id: 'ha_dur', q: 'How long have you had the headache?', options: [{ label: 'A few hours' }, { label: '1–3 days' }, { label: 'More than 3 days' }] },
    { id: 'ha_sev', q: 'How severe is it?', options: [{ label: 'Mild' }, { label: 'Moderate' }, { label: 'Severe' }] },
    { id: 'ha_nausea', q: 'Any nausea with it?', options: [{ label: 'Yes', add: 'nausea' }, { label: 'No' }] },
    { id: 'ha_vision', q: 'Any blurred vision or light sensitivity?', options: [{ label: 'Yes', add: 'blurred and distorted vision' }, { label: 'No' }] },
  ],
  vomiting: [
    { id: 'vom_dur', q: 'How long has the vomiting been going on?', options: [{ label: 'Today only' }, { label: '1–2 days' }, { label: 'Longer' }] },
    { id: 'vom_diar', q: 'Any diarrhoea along with it?', options: [{ label: 'Yes', add: 'diarrhoea' }, { label: 'No' }] },
    { id: 'vom_fever', q: 'Do you have a fever too?', options: [{ label: 'Yes', add: 'high fever' }, { label: 'No' }] },
    { id: 'vom_abd', q: 'Any stomach or abdominal pain?', options: [{ label: 'Yes', add: 'stomach pain' }, { label: 'No' }] },
  ],
  rash: [
    { id: 'rash_itch', q: 'Is the rash itchy?', options: [{ label: 'Yes', add: 'itching' }, { label: 'No' }] },
    { id: 'rash_fever', q: 'Any fever with the rash?', options: [{ label: 'Yes', add: 'high fever' }, { label: 'No' }] },
    { id: 'rash_spread', q: 'Is it spreading over the body?', options: [{ label: 'Yes', add: 'red spots over body' }, { label: 'No' }] },
  ],
  'stomach pain': [
    { id: 'abd_loc', q: 'Where is the pain mostly?', options: [{ label: 'Upper abdomen' }, { label: 'Lower abdomen' }, { label: 'All over' }] },
    { id: 'abd_vomit', q: 'Any nausea or vomiting?', options: [{ label: 'Yes', add: 'vomiting' }, { label: 'No' }] },
    { id: 'abd_diar', q: 'Any diarrhoea?', options: [{ label: 'Yes', add: 'diarrhoea' }, { label: 'No' }] },
    { id: 'abd_fever', q: 'Any fever?', options: [{ label: 'Yes', add: 'high fever' }, { label: 'No' }] },
  ],
  'breathing issues': [
    { id: 'br_rest', q: 'Does it happen at rest, or only on exertion?', options: [{ label: 'At rest' }, { label: 'On exertion' }] },
    { id: 'br_chest', q: 'Any chest pain or tightness?', options: [{ label: 'Yes', add: 'chest pain' }, { label: 'No' }] },
    { id: 'br_cough', q: 'Any cough or wheezing?', options: [{ label: 'Yes', add: 'cough' }, { label: 'No' }] },
  ],
}

// Flat registry so the chat can resolve a question by id.
export const QUESTION_REGISTRY = Object.fromEntries(
  Object.values(FOLLOWUPS).flat().map((q) => [q.id, q]),
)

// ---------- Red flags + recommendation (Requirements #3, #5, #10) ----------
export const RED_FLAG_SYMPTOMS = new Set(['chest pain', 'breathlessness'])

export function band(pct) {
  if (pct > 70) return { label: 'High', tone: 'success' }
  if (pct >= 40) return { label: 'Medium', tone: 'warning' }
  return { label: 'Low', tone: 'danger' }
}

export function buildRecommendation({ emergency, redFlags, topConfidence }) {
  if (emergency || redFlags.length) {
    return {
      tone: 'danger',
      text: 'Some of what you described can be serious. Please seek medical attention urgently or call your local emergency number.',
    }
  }
  if (topConfidence < 40) {
    return {
      tone: 'warning',
      text: 'Your symptoms are not specific enough to suggest a likely condition. Monitor how you feel and consult a doctor if they persist or get worse.',
    }
  }
  return {
    tone: 'primary',
    text: 'Rest and stay hydrated. If symptoms persist beyond a few days, worsen, or you develop new concerns, please consult a doctor.',
  }
}

export const QUICK_ACTIONS = [
  'Fever',
  'Headache',
  'Cough',
  'Rash',
  'Stomach Pain',
  'Breathing Issues',
]
