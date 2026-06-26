/**
 * Shared prescription-report PDF generation.
 *
 * Extracted from the OCR page so both the live analysis screen and the
 * Prescription History detail view produce identical reports (no duplicate
 * logic). Lazy-imports jsPDF so the library is only pulled into the bundle
 * when a user actually downloads a report.
 */
import { titleCase, pct, freqText } from '@/lib/utils'

export const DISCLAIMER =
  'This is an AI-assisted transcription of a prescription and may contain errors. ' +
  'Always verify against the original prescription and consult a licensed pharmacist ' +
  'or doctor before taking any medication.'

/** Read a File/Blob as a data URL (for embedding the image into the PDF). */
export function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(r.result)
    r.onerror = reject
    r.readAsDataURL(file)
  })
}

/** Fetch a remote image URL and return it as a data URL (or null on failure). */
export async function urlToDataUrl(url) {
  try {
    const res = await fetch(url)
    if (!res.ok) return null
    return await readFileAsDataUrl(await res.blob())
  } catch {
    return null
  }
}

/**
 * Build and download a MediSense prescription report PDF.
 * @param {object}   o
 * @param {Array}    o.meds          edited/structured medicine list
 * @param {object}   o.fields        parsed patient/visit fields
 * @param {number}   o.score         overall confidence (0..100)
 * @param {string}   [o.imageDataUrl] data URL of the prescription image
 * @param {string}   [o.fileName]    original file name (used in the PDF name)
 * @param {string[]} [o.notes]       doctor's notes
 */
export async function generatePrescriptionPdf({ meds = [], fields = {}, score = 0, imageDataUrl, fileName, notes }) {
  const { jsPDF } = await import('jspdf')
  const doc = new jsPDF({ unit: 'pt', format: 'a4' })
  const W = doc.internal.pageSize.getWidth()
  const H = doc.internal.pageSize.getHeight()
  const M = 40
  let y = M
  const ensure = (s) => { if (y + s > H - M) { doc.addPage(); y = M } }
  const line = (txt, { size = 11, color = [40, 40, 40], gap = 16, bold = false } = {}) => {
    doc.setFont('helvetica', bold ? 'bold' : 'normal')
    doc.setFontSize(size)
    doc.setTextColor(...color)
    doc.splitTextToSize(txt, W - M * 2).forEach((l) => { ensure(gap); doc.text(l, M, y); y += gap })
  }

  doc.setFillColor(37, 99, 235)
  doc.rect(0, 0, W, 70, 'F')
  doc.setTextColor(255, 255, 255)
  doc.setFont('helvetica', 'bold'); doc.setFontSize(20); doc.text('MediSense', M, 34)
  doc.setFont('helvetica', 'normal'); doc.setFontSize(11); doc.text('Prescription Analysis Report', M, 52)
  doc.setFontSize(9); doc.text(new Date().toLocaleString(), W - M, 34, { align: 'right' })
  y = 92

  // Patient / visit
  const f = fields || {}
  const head = [
    f.doctor && `Doctor: ${f.doctor}`,
    f.hospital && `Clinic: ${f.hospital}`,
    f.patient && `Patient: ${f.patient}`,
    (f.age || f.gender) && `Age/Sex: ${[f.age, f.gender].filter(Boolean).join(' / ')}`,
    f.date && `Date: ${f.date}`,
    f.diagnosis && `Diagnosis: ${f.diagnosis}`,
  ].filter(Boolean)
  head.forEach((h) => line(h, { size: 10, color: [70, 70, 70], gap: 15 }))
  const vit = Object.entries(f.vitals || {})
  if (vit.length) line('Vitals: ' + vit.map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`).join('   '), { size: 10, color: [70, 70, 70], gap: 16 })

  line(`Medicines detected: ${meds.length}    Overall confidence: ${score}%`, { size: 12, bold: true, gap: 20 })

  if (imageDataUrl) {
    try {
      const props = doc.getImageProperties(imageDataUrl)
      const w = 190
      const h = (props.height / props.width) * w
      ensure(h + 16)
      line('Uploaded prescription:', { size: 10, color: [120, 120, 120], gap: 14 })
      doc.addImage(imageDataUrl, props.fileType, M, y, w, h); y += h + 18
    } catch { /* skip */ }
  }

  line('Medicines', { size: 14, bold: true, gap: 20, color: [37, 99, 235] })
  meds.forEach((m, i) => {
    ensure(40)
    const name = m.name ? titleCase(m.name) : m.raw_text
    line(`${i + 1}. ${name}   (${pct(m.confidence)}%)`, { size: 12, bold: true, gap: 16 })
    line(`Dosage: ${m.dosage || '-'}    Frequency: ${freqText(m) || '-'}    Duration: ${m.duration || '-'}`,
      { size: 10, color: [80, 80, 80], gap: 15 })
    if (m.details?.uses?.length) line(`Uses: ${m.details.uses.slice(0, 3).join(', ')}`, { size: 10, color: [80, 80, 80], gap: 15 })
    if (m.details?.side_effects?.length) line(`Side effects: ${m.details.side_effects.slice(0, 5).join(', ')}`, { size: 10, color: [80, 80, 80], gap: 15 })
    y += 6
  })

  if (notes?.length) {
    y += 4; line("Doctor's notes", { size: 12, bold: true, gap: 16 })
    notes.forEach((n) => line(`- ${n}`, { size: 10, color: [80, 80, 80], gap: 15 }))
  }

  y += 10; ensure(60); doc.setDrawColor(220); doc.line(M, y, W - M, y); y += 16
  line(DISCLAIMER, { size: 9, color: [130, 130, 130], gap: 13 })
  doc.save(`medisense-report-${(fileName || 'prescription').replace(/\.[^.]+$/, '')}.pdf`)
}
