"""Agent-layer configuration (LLM, agents, workflow).

Kept import-light and dependency-free of the agent runtime so the LLM factory and
other low-level modules can import it without any import cycle.
"""
