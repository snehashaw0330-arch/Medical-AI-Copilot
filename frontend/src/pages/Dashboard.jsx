import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AreaChart,
  Area,
  ResponsiveContainer,
  XAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts'
import {
  Stethoscope,
  ScanLine,
  Pill,
  MessageSquareText,
  ArrowRight,
  Activity,
  TrendingUp,
  ShieldCheck,
  Clock,
  BrainCircuit,
  AlertOctagon,
  ShieldAlert,
  ClipboardList,
  FileText,
  FileStack,
  CalendarClock,
} from 'lucide-react'
import Card from '@/ui/Card'
import Button from '@/ui/Button'
import Badge from '@/ui/Badge'
import { getPredictions, getReports } from '@/lib/storage'
import { getClinicalStats, getReportStats } from '@/lib/api'

const FEATURES = [
  {
    to: '/predict',
    icon: Stethoscope,
    title: 'Disease Prediction',
    desc: 'Enter symptoms and get calibrated top-3 conditions with explanations.',
  },
  {
    to: '/ocr',
    icon: ScanLine,
    title: 'Prescription OCR',
    desc: 'Read messy handwritten prescriptions and extract medicines instantly.',
  },
  {
    to: '/medicine',
    icon: Pill,
    title: 'Medicine Intelligence',
    desc: 'Uses, side effects, substitutes and therapeutic class for any drug.',
  },
  {
    to: '/chat',
    icon: MessageSquareText,
    title: 'AI Assistant',
    desc: 'Discuss symptoms and get medicine explanations conversationally.',
  },
]

const CHART_DATA = [
  { d: 'Mon', v: 12 },
  { d: 'Tue', v: 19 },
  { d: 'Wed', v: 14 },
  { d: 'Thu', v: 23 },
  { d: 'Fri', v: 28 },
  { d: 'Sat', v: 18 },
  { d: 'Sun', v: 31 },
]

function StatCard({ icon: Icon, label, value, trend, tone = 'primary' }) {
  return (
    <Card hover className="flex items-center gap-4">
      <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-primary-soft text-primary">
        <Icon size={22} />
      </span>
      <div className="min-w-0">
        <p className="text-sm text-muted">{label}</p>
        <p className="text-2xl font-bold text-foreground">{value}</p>
      </div>
      {trend && (
        <Badge tone={tone} className="ml-auto">
          <TrendingUp size={12} /> {trend}
        </Badge>
      )}
    </Card>
  )
}

// Color-coded clinical-risk card for the CDSS dashboard row (Requirement 8).
function RiskCard({ icon: Icon, label, value, tone }) {
  const TONES = {
    danger: 'bg-danger/15 text-danger',
    warning: 'bg-warning/15 text-warning',
    primary: 'bg-primary-soft text-primary',
    neutral: 'bg-surface-2 text-muted',
  }
  return (
    <Card hover className="flex items-center gap-4">
      <span className={`grid h-12 w-12 shrink-0 place-items-center rounded-xl ${TONES[tone] || TONES.neutral}`}>
        <Icon size={22} />
      </span>
      <div className="min-w-0">
        <p className="text-sm text-muted">{label}</p>
        <p className="text-2xl font-bold text-foreground">{value}</p>
      </div>
    </Card>
  )
}

export default function Dashboard() {
  const predictions = getPredictions()
  const reports = getReports()
  const medsFound = reports.reduce((a, r) => a + (r.medicineCount || 0), 0)

  // Clinical decision-support aggregates (best-effort — dashes if backend down).
  const [clinical, setClinical] = useState(null)
  const [reportStats, setReportStats] = useState(null)
  useEffect(() => {
    getClinicalStats().then(setClinical).catch(() => setClinical(null))
    getReportStats().then(setReportStats).catch(() => setReportStats(null))
  }, [])
  const cv = (k) => (clinical ? clinical[k] ?? 0 : '—')
  const rv = (k) => (reportStats ? reportStats[k] ?? 0 : '—')

  return (
    <div className="space-y-6">
      {/* Hero */}
      <section className="animate-fade-up overflow-hidden rounded-3xl border border-border bg-gradient-to-br from-primary to-accent p-8 text-white shadow-xl shadow-primary/20 lg:p-12">
        <Badge className="bg-white/15 text-white backdrop-blur">
          <Activity size={12} /> AI-Powered Healthcare
        </Badge>
        <h2 className="mt-4 max-w-2xl text-3xl font-bold leading-tight text-white lg:text-4xl">
          Smarter clinical decisions, from symptoms to prescriptions.
        </h2>
        <p className="mt-3 max-w-xl text-white/85">
          MediSense combines disease prediction, handwriting OCR, and medicine
          intelligence into one calibrated, explainable assistant.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link to="/predict">
            <Button className="bg-white text-primary hover:bg-white/90">
              Start Diagnosis <ArrowRight size={16} />
            </Button>
          </Link>
          <Link to="/ocr">
            <Button className="border border-white/40 bg-white/10 text-white hover:bg-white/20">
              Scan Prescription
            </Button>
          </Link>
        </div>
      </section>

      {/* Stats */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard icon={Stethoscope} label="Diagnoses run" value={predictions.length} trend="live" />
        <StatCard icon={ScanLine} label="Prescriptions scanned" value={reports.length} trend="live" />
        <StatCard icon={Pill} label="Medicines extracted" value={medsFound} />
        <StatCard icon={ShieldCheck} label="Model accuracy*" value="—" />
      </section>

      {/* Clinical Decision Support risk overview (Requirement 8) */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BrainCircuit size={18} className="text-primary" />
            <h3 className="text-lg font-semibold text-foreground">Clinical Decision Support</h3>
          </div>
          <Link to="/clinical" className="inline-flex items-center gap-1 text-sm font-medium text-primary">
            Open <ArrowRight size={14} />
          </Link>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <RiskCard icon={ClipboardList} label="Total Clinical Reports" value={cv('total_reports')} tone="primary" />
          <RiskCard icon={AlertOctagon} label="High Risk Cases" value={cv('high_risk_cases')} tone="danger" />
          <RiskCard icon={ShieldAlert} label="Moderate Risk Cases" value={cv('moderate_risk_cases')} tone="warning" />
          <RiskCard icon={ShieldCheck} label="Low Risk Cases" value={cv('low_risk_cases')} tone="primary" />
        </div>
      </section>

      {/* Medical Reports overview (Requirement 8) */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileText size={18} className="text-primary" />
            <h3 className="text-lg font-semibold text-foreground">Medical Reports</h3>
          </div>
          <Link to="/reports" className="inline-flex items-center gap-1 text-sm font-medium text-primary">
            Open <ArrowRight size={14} />
          </Link>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <RiskCard icon={FileStack} label="Total Reports" value={rv('total_reports')} tone="primary" />
          <RiskCard icon={CalendarClock} label="Generated Today" value={rv('reports_today')} tone="primary" />
          <RiskCard
            icon={ShieldCheck}
            label="Average OCR Confidence"
            value={reportStats ? `${Math.round((reportStats.average_confidence || 0) * 100)}%` : '—'}
            tone="primary"
          />
          <RiskCard icon={AlertOctagon} label="High Risk Reports" value={rv('high_risk_reports')} tone="danger" />
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Activity chart */}
        <Card className="lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="font-semibold text-foreground">Activity overview</h3>
              <p className="text-sm text-muted">Sample weekly usage</p>
            </div>
            <Badge tone="success">
              <TrendingUp size={12} /> +18%
            </Badge>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={CHART_DATA} margin={{ left: -20, right: 8, top: 8 }}>
                <defs>
                  <linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="var(--primary)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="d" stroke="var(--muted)" fontSize={12} tickLine={false} axisLine={false} />
                <Tooltip
                  contentStyle={{
                    background: 'var(--surface)',
                    border: '1px solid var(--border)',
                    borderRadius: 12,
                    color: 'var(--foreground)',
                  }}
                />
                <Area type="monotone" dataKey="v" stroke="var(--primary)" strokeWidth={2.5} fill="url(#grad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Recent activity */}
        <Card>
          <h3 className="mb-4 font-semibold text-foreground">Recent activity</h3>
          {predictions.length === 0 && reports.length === 0 ? (
            <p className="text-sm text-muted">
              No activity yet. Run a diagnosis or scan a prescription to get
              started.
            </p>
          ) : (
            <ul className="space-y-3">
              {[...predictions.slice(0, 3).map((p) => ({
                icon: Stethoscope,
                text: p.topDisease || 'Diagnosis',
                at: p.at,
              })),
              ...reports.slice(0, 2).map((r) => ({
                icon: ScanLine,
                text: `${r.medicineCount || 0} medicines scanned`,
                at: r.at,
              }))].map((item, i) => (
                <li key={i} className="flex items-center gap-3">
                  <span className="grid h-9 w-9 place-items-center rounded-lg bg-surface-2 text-primary">
                    <item.icon size={16} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-foreground">{item.text}</p>
                    <p className="flex items-center gap-1 text-xs text-muted">
                      <Clock size={11} /> {new Date(item.at).toLocaleDateString()}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {/* Feature cards */}
      <section>
        <h3 className="mb-4 text-lg font-semibold text-foreground">Explore tools</h3>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((f) => (
            <Link key={f.to} to={f.to}>
              <Card hover className="group h-full">
                <span className="grid h-12 w-12 place-items-center rounded-xl bg-primary-soft text-primary transition-transform group-hover:scale-110">
                  <f.icon size={22} />
                </span>
                <h4 className="mt-4 font-semibold text-foreground">{f.title}</h4>
                <p className="mt-1 text-sm text-muted">{f.desc}</p>
                <span className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-primary">
                  Open <ArrowRight size={14} className="transition-transform group-hover:translate-x-1" />
                </span>
              </Card>
            </Link>
          ))}
        </div>
      </section>

      <p className="text-center text-xs text-muted">
        * MediSense is an AI triage aid, not a medical diagnosis. Always consult
        a licensed clinician.
      </p>
    </div>
  )
}
