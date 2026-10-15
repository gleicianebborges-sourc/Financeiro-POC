"""Módulo de configuração do XLedger."""
from .openrouter import openrouter_settings, OpenRouterSettings
from .database import db_manager, NormativeVectorStore, VectorDocument

__all__ = [
    "openrouter_settings",
    "OpenRouterSettings",
    "db_manager",
    "NormativeVectorStore",
    "VectorDocument",
]
