"""Deprecated compatibility layer for :mod:`agent_dealer`."""

from agent_dealer import MMACError, TaskStore, ValidationReport, __version__, validate_task

__all__ = ["MMACError", "TaskStore", "ValidationReport", "__version__", "validate_task"]
