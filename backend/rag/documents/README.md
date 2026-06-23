# Knowledge Base Documents

Every `.txt`, `.md` / `.markdown`, and `.pdf` file in this folder is
automatically indexed into the RAG vector database when you run **Rebuild Index**
(or call `POST /rag/index`).

## How to add knowledge
1. Drop a document here (or upload it from the **Knowledge Base** page in the UI).
2. Rebuild the index.
3. Ask questions in the Knowledge Base search box or the AI Assistant.

## Recommended structure for medicine documents
For the best offline (no-LLM) extraction, structure medicine documents with these
markdown headings — the system maps them to the structured drug-profile fields:

- `## Uses`
- `## Dosage`
- `## Side Effects`
- `## Drug Interactions`
- `## Contraindications`
- `## Warnings`
- `## Pregnancy Safety`
- `## Food Interactions`
- `## Storage`

When an LLM provider (OpenAI / Gemini) is configured, answers are generated from
the same retrieved context. With no provider, the assistant still works using
extractive retrieval over these documents.

> All content here is educational only and not a substitute for professional
> medical advice.
