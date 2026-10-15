"""Camada de Modelos com Herança de Classes (Entidades de Domínio do XLedger)."""

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import Any, Dict, Optional


class BaseEntity(ABC):
    """Abstração fundamental para todas as entidades persistíveis do XLedger."""

    def __init__(self, entity_id: str) -> None:
        self.id = entity_id

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        pass


class BaseTransaction(BaseEntity):
    """Entidade base para movimentações financeiras de fluxo de caixa."""

    def __init__(
        self,
        entity_id: str,
        data: date,
        valor: Decimal,
        tipo: str,
        descricao_bruta: str
    ) -> None:
        super().__init__(entity_id)
        self.data = data
        self.valor = valor
        self.tipo = tipo
        self.descricao_bruta = descricao_bruta

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "data": self.data.isoformat(),
            "valor": float(self.valor),
            "tipo": self.tipo,
            "descricao_bruta": self.descricao_bruta,
        }


class BankStatementTransaction(BaseTransaction):
    """Especialização para extratos bancários brutos ingeridos (OFX/CSV)."""

    def __init__(
        self,
        entity_id: str,
        data: date,
        valor: Decimal,
        tipo: str,
        descricao_bruta: str,
        documento: str,
        canal: str,
        identificador_contraparte: Optional[str] = None,
        nome_contraparte: Optional[str] = None
    ) -> None:
        super().__init__(entity_id, data, valor, tipo, descricao_bruta)
        self.documento = documento
        self.canal = canal
        self.identificador_contraparte = identificador_contraparte
        self.nome_contraparte = nome_contraparte

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "documento": self.documento,
            "canal": self.canal,
            "identificador_contraparte": self.identificador_contraparte,
            "nome_contraparte": self.nome_contraparte,
        })
        return d


class ProcessedTransaction(BankStatementTransaction):
    """Lançamento enriquecido com classificação contábil e parecer fiscal."""

    def __init__(
        self,
        entity_id: str,
        data: date,
        valor: Decimal,
        tipo: str,
        descricao_bruta: str,
        documento: str,
        canal: str,
        identificador_contraparte: Optional[str] = None,
        nome_contraparte: Optional[str] = None,
        categoria_financeira: str = "",
        centro_custo: str = "",
        conta_debito: str = "",
        conta_credito: str = "",
        dedutivel: bool = False,
        confidence_score: float = 0.0,
        motor_utilizado: str = "",
        natureza_fiscal: str = "",
        status_compliance: str = "REGULAR",
        irrf_calculado: Decimal = Decimal("0.00"),
        alerta_auditoria: Optional[str] = None
    ) -> None:
        super().__init__(
            entity_id,
            data,
            valor,
            tipo,
            descricao_bruta,
            documento,
            canal,
            identificador_contraparte,
            nome_contraparte
        )
        self.categoria_financeira = categoria_financeira
        self.centro_custo = centro_custo
        self.conta_debito = conta_debito
        self.conta_credito = conta_credito
        self.dedutivel = dedutivel
        self.confidence_score = confidence_score
        self.motor_utilizado = motor_utilizado
        self.natureza_fiscal = natureza_fiscal
        self.status_compliance = status_compliance
        self.irrf_calculado = irrf_calculado
        self.alerta_auditoria = alerta_auditoria

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "categoria_financeira": self.categoria_financeira,
            "centro_custo": self.centro_custo,
            "conta_debito": self.conta_debito,
            "conta_credito": self.conta_credito,
            "dedutivel": self.dedutivel,
            "confidence_score": self.confidence_score,
            "motor_utilizado": self.motor_utilizado,
            "natureza_fiscal": self.natureza_fiscal,
            "status_compliance": self.status_compliance,
            "irrf_calculado": float(self.irrf_calculado),
            "alerta_auditoria": self.alerta_auditoria,
        })
        return d
