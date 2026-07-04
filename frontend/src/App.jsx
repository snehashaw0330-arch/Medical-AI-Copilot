import { Routes, Route } from 'react-router-dom'
import AppLayout from './layout/AppLayout'
import Dashboard from './pages/Dashboard'
import DiseasePrediction from './pages/DiseasePrediction'
import SymptomChecker from './pages/SymptomChecker'
import PrescriptionOCR from './pages/PrescriptionOCR'
import ClinicalDecision from './pages/ClinicalDecision'
import MedicalReports from './pages/MedicalReports'
import PrescriptionHistory from './pages/PrescriptionHistory'
import DatasetEvaluation from './pages/DatasetEvaluation'
import KnowledgeBase from './pages/KnowledgeBase'
import MedicineSearch from './pages/MedicineSearch'
import Chat from './pages/Chat'
import Profile from './pages/Profile'
import NotFound from './pages/NotFound'

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="predict" element={<DiseasePrediction />} />
        <Route path="symptoms" element={<SymptomChecker />} />
        <Route path="ocr" element={<PrescriptionOCR />} />
        <Route path="clinical" element={<ClinicalDecision />} />
        <Route path="reports" element={<MedicalReports />} />
        <Route path="history" element={<PrescriptionHistory />} />
        <Route path="dataset" element={<DatasetEvaluation />} />
        <Route path="knowledge" element={<KnowledgeBase />} />
        <Route path="medicine" element={<MedicineSearch />} />
        <Route path="chat" element={<Chat />} />
        <Route path="profile" element={<Profile />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
