"""
Canonical ShredExecutor and ExecNode re-export.
Unifies execution dispatch across tools and orchestration services.
"""
from app.actors.executor_actor import ExecNode, PromptResult, ShredExecutor

__all__ = ["ExecNode", "PromptResult", "ShredExecutor"]
