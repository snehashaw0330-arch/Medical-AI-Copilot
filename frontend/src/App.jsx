import { Routes, Route } from 'react-router-dom'
import AppLayout from './layout/AppLayout'
import Dashboard from './pages/Dashboard'
import DiseasePrediction from './pages/DiseasePrediction'
import SymptomChecker from './pages/SymptomChecker'
import PrescriptionOCR from './pages/PrescriptionOCR'
import DocumentIntelligence from './pages/DocumentIntelligence'
import ClinicalDecision from './pages/ClinicalDecision'
import ClinicalReasoning from './pages/ClinicalReasoning'
import CopilotWorkspace from './pages/CopilotWorkspace'
import TreatmentSimulator from './pages/TreatmentSimulator'
import EvidenceVerification from './pages/EvidenceVerification'
import EvidenceExplorer from './pages/EvidenceExplorer'
import MedicalReports from './pages/MedicalReports'
import PrescriptionHistory from './pages/PrescriptionHistory'
import DatasetEvaluation from './pages/DatasetEvaluation'
import KnowledgeBase from './pages/KnowledgeBase'
import MedicineSearch from './pages/MedicineSearch'
import MedicineRecommendations from './pages/MedicineRecommendations'
import AgentMonitor from './pages/AgentMonitor'
import DigitalTwin from './pages/DigitalTwin'
import PatientContext from './pages/PatientContext'
import AIGovernance from './pages/AIGovernance'
import ModelRegistry from './pages/ModelRegistry'
import DatasetRegistry from './pages/DatasetRegistry'
import AuditLogs from './pages/AuditLogs'
import PipelineViewer from './pages/PipelineViewer'
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
        <Route path="documents" element={<DocumentIntelligence />} />
        <Route path="clinical" element={<ClinicalDecision />} />
        <Route path="reasoning" element={<ClinicalReasoning />} />
        <Route path="copilot" element={<CopilotWorkspace />} />
        <Route path="simulator" element={<TreatmentSimulator />} />
        <Route path="verification" element={<EvidenceVerification />} />
        <Route path="evidence" element={<EvidenceExplorer />} />
        <Route path="reports" element={<MedicalReports />} />
        <Route path="history" element={<PrescriptionHistory />} />
        <Route path="dataset" element={<DatasetEvaluation />} />
        <Route path="knowledge" element={<KnowledgeBase />} />
        <Route path="medicine" element={<MedicineSearch />} />
        <Route path="recommendations" element={<MedicineRecommendations />} />
        <Route path="agents" element={<AgentMonitor />} />
        <Route path="digital-twin" element={<DigitalTwin />} />
        <Route path="patient-context" element={<PatientContext />} />
        <Route path="governance" element={<AIGovernance />} />
        <Route path="governance/models" element={<ModelRegistry />} />
        <Route path="governance/datasets" element={<DatasetRegistry />} />
        <Route path="governance/audit-logs" element={<AuditLogs />} />
        <Route path="governance/pipeline" element={<PipelineViewer />} />
        <Route path="chat" element={<Chat />} />
        <Route path="profile" element={<Profile />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
