"""Prompt templates for RAG answer generation.

Centralising prompts keeps tone/safety consistent and makes them easy to tune
without touching orchestration logic. Every prompt is grounded: the model is
instructed to answer **only** from the retrieved context and to say when the
context is insufficient — this is what keeps a medical assistant from
hallucinating drug facts.
"""

from __future__ import annotations

from backend.rag.vector_store import RetrievedChunk

# The structured fields we try to surface for any detected medicine
# (Requirement 8). Order here is the display order.
MEDICINE_FIELDS: list[str] = [
    "uses",
    "dosage",
    "side_effects",
    "drug_interactions",
    "contraindications",
    "warnings",
    "pregnancy_safety",
    "food_interactions",
    "storage",
]

SYSTEM_PROMPT = (
    "You are MediSense, a careful medical knowledge assistant. Answer using ONLY "
    "the provided context from the knowledge base. If the context does not "
    "contain the answer, say so plainly and suggest consulting a licensed "
    "pharmacist or doctor. Never invent dosages, interactions, or drug facts. "
    "Be concise, structured, and always remind the user this is informational, "
    "not a prescription."
)

SAFETY_FOOTER = (
    "This information is educational only and not a substitute for professional "
    "medical advice. Always confirm with a licensed pharmacist or doctor."
)


def format_context(chunks: list[RetrievedChunk]) -> str:
    """Render retrieved chunks into a numbered, source-attributed context block."""
    if not chunks:
        return "(no relevant context found)"
    blocks = []
    for i, c in enumerate(chunks, 1):
        blocks.append(f"[{i}] (source: {c.source}, similarity: {c.score:.2f})\n{c.text}")
    return "\n\n".join(blocks)


def build_qa_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    """User-turn prompt for a general knowledge-base question."""
    return (
        f"Context from the medical knowledge base:\n\n{format_context(chunks)}\n\n"
        f"Question: {question}\n\n"
        "Answer the question grounded strictly in the context above. Cite sources "
        "inline as [1], [2] where relevant. If the answer isn't in the context, "
        "say what is missing."
    )


def build_medicine_prompt(medicine: str, chunks: list[RetrievedChunk]) -> str:
    """Prompt asking for the structured drug profile (Requirement 8)."""
    fields = "\n".join(f"- {f.replace('_', ' ').title()}" for f in MEDICINE_FIELDS)
    return (
        f"Context from the medical knowledge base:\n\n{format_context(chunks)}\n\n"
        f"Using ONLY the context above, summarise what is known about "
        f"\"{medicine}\". Cover these fields when present (omit a field if the "
        f"context has nothing reliable for it):\n{fields}\n\n"
        "Keep each field to 1-2 short sentences. Do not fabricate values."
    )


def build_interaction_prompt(medicines: list[str], chunks: list[RetrievedChunk]) -> str:
    """Prompt for checking interactions across multiple detected medicines."""
    names = ", ".join(medicines)
    return (
        f"Context from the medical knowledge base:\n\n{format_context(chunks)}\n\n"
        f"The following medicines were detected together: {names}.\n"
        "Based ONLY on the context above, list any known or potential drug-drug "
        "interactions between them, the severity if stated, and what the patient "
        "should do. If the context contains no interaction information, say that "
        "no interaction data was found in the knowledge base."
    )
