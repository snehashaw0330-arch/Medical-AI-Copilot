import {
  LayoutDashboard,
  Stethoscope,
  ScanLine,
  Pill,
  MessageSquareText,
  User,
  Database,
  BookOpen,
  History,
  BrainCircuit,
  FileText,
  ActivitySquare,
} from 'lucide-react'

export const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/predict', label: 'Disease Prediction', icon: Stethoscope },
  { to: '/symptoms', label: 'Symptom Checker', icon: ActivitySquare },
  { to: '/ocr', label: 'Prescription OCR', icon: ScanLine },
  { to: '/clinical', label: 'Clinical Decision', icon: BrainCircuit },
  { to: '/reports', label: 'Medical Reports', icon: FileText },
  { to: '/history', label: 'Prescription History', icon: History },
  { to: '/dataset', label: 'Dataset Evaluation', icon: Database },
  { to: '/knowledge', label: 'Knowledge Base', icon: BookOpen },
  { to: '/medicine', label: 'Medicine Search', icon: Pill },
  { to: '/chat', label: 'AI Assistant', icon: MessageSquareText },
  { to: '/profile', label: 'Profile', icon: User },
]
