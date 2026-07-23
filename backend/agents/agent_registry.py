"""Agent registry — discovery + lazy construction of agents.

Holds the catalogue of available agents as lightweight *specs* (name, title,
description, read/write slots and where the implementation lives). Instances are
built **lazily** on first use, so importing the registry does not pull heavy
dependencies (EasyOCR, sklearn, RAG embeddings) until an agent is actually
needed. Disabled agents (via :mod:`agent_config`) are reported but never built.

Adding an agent = adding one spec here + its implementation file. Nothing else in
the engine changes (Open-Closed).
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass

from backend.agents.base_agent import BaseAgent
from backend.agents.config import agent_config as ac
from backend.agents.config.agent_config import AgentConfig, get_agent_config
from backend.agents.context_manager import MemoryKeys as K
from backend.agents.logger import get_logger
from backend.agents.schemas import AgentMeta

logger = get_logger("registry")

_IMPL = "backend.agents.implementations"


@dataclass(frozen=True)
class AgentSpec:
    """Static description of an agent + where to import it from."""

    name: str
    title: str
    description: str
    reads: tuple[str, ...]
    writes: tuple[str, ...]
    module: str
    cls: str


# The catalogue. Order mirrors the pipeline for readability.
AGENT_SPECS: dict[str, AgentSpec] = {
    ac.OCR: AgentSpec(
        ac.OCR, "OCR Agent",
        "Preprocess the prescription image, assess quality and run OCR into structured JSON.",
        (K.INPUTS,), (K.OCR,), f"{_IMPL}.ocr_agent", "OCRAgent"),
    ac.MEDICINE: AgentSpec(
        ac.MEDICINE, "Medicine Agent",
        "Detect medicines, correct spelling via fuzzy matching, extract dosage and find alternatives.",
        (K.OCR, K.INPUTS), (K.MEDICINES,), f"{_IMPL}.medicine_agent", "MedicineAgent"),
    ac.DISEASE: AgentSpec(
        ac.DISEASE, "Disease Prediction Agent",
        "Predict likely conditions from symptoms with confidence and alternatives.",
        (K.INPUTS, K.OCR), (K.DISEASE,), f"{_IMPL}.disease_agent", "DiseaseAgent"),
    ac.DRUG_INTERACTION: AgentSpec(
        ac.DRUG_INTERACTION, "Drug Interaction Agent",
        "Detect drug-drug interactions, risk level, contraindications, pregnancy and food warnings.",
        (K.MEDICINES,), (K.INTERACTIONS,), f"{_IMPL}.drug_interaction_agent", "DrugInteractionAgent"),
    ac.KNOWLEDGE: AgentSpec(
        ac.KNOWLEDGE, "Medical Knowledge Agent",
        "The sole gateway to the RAG knowledge base — retrieve guidelines and clinical references.",
        (K.MEDICINES, K.DISEASE), (K.KNOWLEDGE,), f"{_IMPL}.knowledge_agent", "KnowledgeAgent"),
    ac.CLINICAL: AgentSpec(
        ac.CLINICAL, "Clinical Decision Agent",
        "Synthesise all prior outputs into recommendations, warnings and a risk assessment.",
        (K.MEDICINES, K.DISEASE, K.INTERACTIONS, K.KNOWLEDGE), (K.CLINICAL,),
        f"{_IMPL}.clinical_agent", "ClinicalAgent"),
    ac.EXPLAINABILITY: AgentSpec(
        ac.EXPLAINABILITY, "Explainability Agent",
        "Explain WHY each conclusion was reached, with the evidence and confidence behind it.",
        (K.DISEASE, K.MEDICINES, K.INTERACTIONS, K.KNOWLEDGE, K.CLINICAL), (K.EXPLANATION,),
        f"{_IMPL}.explainability_agent", "ExplainabilityAgent"),
    ac.EVIDENCE_VERIFICATION: AgentSpec(
        ac.EVIDENCE_VERIFICATION, "Evidence Verification Agent",
        "Verify the clinical assessment against retrieved evidence — hallucination risk, citations and confidence.",
        (K.CLINICAL, K.KNOWLEDGE, K.MEDICINES, K.DISEASE), (K.EVIDENCE_VERIFICATION,),
        f"{_IMPL}.evidence_verification_agent", "EvidenceVerificationAgent"),
    ac.REPORT: AgentSpec(
        ac.REPORT, "Report Agent",
        "Generate the durable clinical report (PDF / JSON / HTML) from the assembled findings.",
        (K.OCR, K.CLINICAL, K.INTERACTIONS), (K.REPORT,), f"{_IMPL}.report_agent", "ReportAgent"),
    ac.AUDIT: AgentSpec(
        ac.AUDIT, "Audit Agent",
        "Record every step, agent, execution time, confidence and error into a decision log.",
        (), (K.AUDIT,), f"{_IMPL}.audit_agent", "AuditAgent"),
}


class AgentRegistry:
    """Builds and caches agent instances on demand, honouring config toggles."""

    def __init__(self, config: AgentConfig | None = None) -> None:
        self._config = config or get_agent_config()
        self._cache: dict[str, BaseAgent] = {}

    def is_enabled(self, name: str) -> bool:
        return name in AGENT_SPECS and self._config.is_enabled(name)

    def get(self, name: str) -> BaseAgent:
        """Return (constructing + caching on first use) the named agent."""
        if name in self._cache:
            return self._cache[name]
        spec = AGENT_SPECS[name]
        module = importlib.import_module(spec.module)
        agent: BaseAgent = getattr(module, spec.cls)()
        self._cache[name] = agent
        return agent

    def meta(self) -> list[AgentMeta]:
        """Static metadata for every agent (no heavy imports)."""
        return [
            AgentMeta(
                name=s.name, title=s.title, description=s.description,
                reads=list(s.reads), writes=list(s.writes),
                enabled=self._config.is_enabled(s.name),
            )
            for s in AGENT_SPECS.values()
        ]
