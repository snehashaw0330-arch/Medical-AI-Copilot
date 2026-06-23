"""Retrieval-Augmented Generation (RAG) package for the Medical AI Assistant.

A self-contained, modular RAG subsystem that indexes local medical knowledge
documents (txt / pdf / markdown) into a vector database and answers questions
using the retrieved context — optionally augmented by a cloud or local LLM.

Public surface lives in :mod:`backend.rag.rag_service` (orchestration) and
:mod:`backend.rag.router` (FastAPI endpoints). Every heavy dependency
(sentence-transformers, chromadb, pypdf) is imported lazily so the rest of the
application keeps working even when the RAG extras are not installed.
"""

from __future__ import annotations
