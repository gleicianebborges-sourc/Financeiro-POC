"""Representação do Extrato Bancário e Metadados do Lote Ingerido."""

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional
from .transaction import BankStatementTransaction, ProcessedTransaction


class BankStatement:
    """Entidade representativa de um extrato bancário consolidado."""

    def __init__(
        self,
        banco: str,
        conta: str,
        agencia: str,
        moeda: str = "BRL",
        periodo_inicio: Optional[date] = None,
        periodo_fim: Optional[date] = None,
        saldo_inicial: Decimal = Decimal("0.00"),
        saldo_final: Decimal = Decimal("0.00"),
        transacoes: Optional[List[BankStatementTransaction]] = None
    ) -> None:
        self.banco = banco
        self.conta = conta
        self.agencia = agencia
        self.moeda = moeda
        self.periodo_inicio = periodo_inicio
        self.periodo_fim = periodo_fim
        self.saldo_inicial = saldo_inicial
        self.saldo_final = saldo_final
        self.transacoes: List[BankStatementTransaction] = transacoes or []

    def adicionar_transacao(self, tx: BankStatementTransaction) -> None:
        self.transacoes.append(tx)

    def total_creditos(self) -> Decimal:
        return sum((t.valor for t in self.transacoes if t.tipo == "CREDITO"), Decimal("0.00"))

    def total_debitos(self) -> Decimal:
        return sum((t.valor for t in self.transacoes if t.tipo == "DEBITO"), Decimal("0.00"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "banco": self.banco,
            "conta": self.conta,
            "agencia": self.agencia,
            "moeda": self.moeda,
            "periodo_inicio": self.periodo_inicio.isoformat() if self.periodo_inicio else None,
            "periodo_fim": self.periodo_fim.isoformat() if self.periodo_fim else None,
            "saldo_inicial": float(self.saldo_inicial),
            "saldo_final": float(self.saldo_final),
            "total_transacoes": len(self.transacoes),
            "total_creditos": float(self.total_creditos()),
            "total_debitos": float(self.total_debitos()),
        }
