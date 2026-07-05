"""Concrete agents. Each delegates to an existing project service and writes its
result to shared memory. Imported lazily by the registry so heavy dependencies
(OCR/ML/RAG) load only when the agent actually runs.
"""
