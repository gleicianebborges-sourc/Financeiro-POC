"""Schema de auditoria e compliance fiscal estrito (FiscalComplianceOutput)."""

from decimal import Decimal
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class ComplianceDecision(str, Enum):
    """Status de julgamento do compliance fiscal."""
    APROVADO = "Aprovado"
    ALERTA = "Alerta"
    BLOQUEADO = "Bloqueado"


class FiscalComplianceOutput(BaseModel):
    """Schema específico de auditoria de conformidade fiscal e tributária.
    
    Atende aos requisitos de auditoria contábil, e-Financeira e prevenção de confusão patrimonial.
    """
    transacao_id: str = Field(..., min_length=1, description="ID da transação auditada")
    status_compliance: ComplianceDecision = Field(
        ...,
        description="Veredito da esteira de compliance: Aprovado, Alerta ou Bloqueado"
    )
    flags_de_risco: List[str] = Field(
        default_factory=list,
        description="Lista de violações e riscos identificados (ex: 'Confusão Patrimonial', 'Teto e-Financeira')"
    )
    valor_retido_irrf: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        description="Montante provisionado ou retido de IRRF"
    )
    inss_a_recolher: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        description="Montante de INSS apurado sobre pró-labore ou serviços"
    )
    justificativa_legal: str = Field(
        ...,
        description="Embasamento normativo fundamentado (IN RFB 1571/2015, CC Art. 50, Lei 4.357/64)"
    )
    acumulado_mes_cpf: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        description="Totalizador acumulado transferido ao CPF no mês corrente"
    )
    alerta_e_financeira: bool = Field(
        default=False,
        description="Indicador de acionamento do gatilho de informe e-Financeira da RFB"
    )
