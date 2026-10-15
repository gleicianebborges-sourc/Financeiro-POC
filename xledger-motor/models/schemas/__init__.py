"""Schemas de entrada e saída (DTOs) do XLedger."""

from .transaction import (
    TransactionType,
    FinancialCategory,
    FiscalNature,
    ComplianceStatus,
    EngineType,
    Counterparty,
    ClassificationDetail,
    FiscalComplianceDetail,
    TransactionClassificationOutput,
)
from .compliance import ComplianceDecision, FiscalComplianceOutput

__all__ = [
    "TransactionType",
    "FinancialCategory",
    "FiscalNature",
    "ComplianceStatus",
    "EngineType",
    "Counterparty",
    "ClassificationDetail",
    "FiscalComplianceDetail",
    "TransactionClassificationOutput",
    "ComplianceDecision",
    "FiscalComplianceOutput",
]
