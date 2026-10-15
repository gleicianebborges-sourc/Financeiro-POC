"""Schemas de validação estrita (Type-Safe / JEV) utilizando Pydantic v2.

Define os domínios discretos de categorias contábeis, naturezas fiscais e contratos
de saída para a esteira híbrida de classificação e compliance.
"""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict


class TransactionType(str, Enum):
    """Tipo da transação bancária."""
    DEBITO = "DEBITO"
    CREDITO = "CREDITO"


class FinancialCategory(str, Enum):
    """Categorias financeiras contábeis padronizadas."""
    OPEX = "OPEX"
    CAPEX = "CAPEX"
    FORNECEDORES = "FORNECEDORES"
    FOLHA_PAGAMENTO = "FOLHA_PAGAMENTO"
    IMPOSTOS = "IMPOSTOS"
    SERVICOS_TERCEIROS = "SERVICOS_TERCEIROS"
    RECEITA_OPERACIONAL = "RECEITA_OPERACIONAL"
    RECEITA_FINANCEIRA = "RECEITA_FINANCEIRA"
    RETIRO_SOCIOS = "RETIRO_SOCIOS"


class FiscalNature(str, Enum):
    """Natureza fiscal de repasses e transferências."""
    OPERACIONAL = "OPERACIONAL"
    PRO_LABORE = "PRO_LABORE"
    LUCRO = "LUCRO"
    REEMBOLSO = "REEMBOLSO"
    ALERTA_CONFUSAO = "ALERTA_CONFUSAO"


class ComplianceStatus(str, Enum):
    """Status de auditoria e conformidade fiscal."""
    REGULAR = "REGULAR"
    ATENCAO = "ATENCAO"
    IRREGULAR = "IRREGULAR"


class EngineType(str, Enum):
    """Motor de decisão executado."""
    JEV = "JEV"
    RAG_LLM = "RAG_LLM"


class Counterparty(BaseModel):
    """Dados da contraparte com sanitização estrita de documento (CPF/CNPJ)."""
    model_config = ConfigDict(populate_by_name=True)

    identificador: str = Field(..., description="CNPJ ou CPF numérico limpo de máscaras")
    nome: str = Field(..., description="Razão Social ou Nome Completo")

    @field_validator("identificador")
    @classmethod
    def validate_identifier_digits(cls, value: str) -> str:
        """Sanitização prévia: padroniza a entrada em dígitos puros (11 para CPF ou 14 para CNPJ)."""
        clean = "".join(c for c in value if c.isdigit())
        if len(clean) not in (11, 14):
            raise ValueError(
                f"Identificador '{value}' inválido. Precisa conter exatamente 11 (CPF) ou 14 (CNPJ) dígitos."
            )
        return clean

    @property
    def is_cpf(self) -> bool:
        return len(self.identificador) == 11

    @property
    def is_cnpj(self) -> bool:
        return len(self.identificador) == 14


class ClassificationDetail(BaseModel):
    """Detalhamento contábil e partidas dobradas da transação."""
    categoria_financeira: FinancialCategory
    centro_custo: str = Field(..., min_length=2, description="Centro de custo gerencial")
    conta_debito: str = Field(..., min_length=3, description="Código da conta débito no plano contábil")
    conta_credito: str = Field(..., min_length=3, description="Código da conta crédito no plano contábil")
    dedutivel: bool = Field(..., description="Dedutibilidade para IRPJ e CSLL")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Calibração probabilística do motor")
    motor_usado: EngineType = Field(..., description="Motor responsável pelo julgamento (JEV ou RAG_LLM)")


class FiscalComplianceDetail(BaseModel):
    """Detalhamento do parecer fiscal e obrigações acessórias."""
    natureza_pj_pf: FiscalNature = Field(..., description="Natureza da transferência entre entidades")
    limite_e_financeira_atingido: bool = Field(
        default=False,
        description="Indica se o montante ultrapassou o teto da IN RFB 1571/2015"
    )
    irrf_retido: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        description="Valor de Imposto de Renda Retido na Fonte calculado"
    )
    inss_devido: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        description="Valor de contribuição previdenciária calculada"
    )
    status_conformidade: ComplianceStatus = Field(
        default=ComplianceStatus.REGULAR,
        description="Julgamento de risco fiscal"
    )
    motivo_auditoria: Optional[str] = Field(
        default=None,
        description="Justificativa legal ou parecer normativo"
    )


class TransactionClassificationOutput(BaseModel):
    """Contrato definitivo e canônico de saída para transações classificadas."""
    transaction_id: str = Field(..., min_length=1, description="Identificador único da transação")
    data: date = Field(..., description="Data do lançamento bancário")
    valor: Decimal = Field(..., gt=Decimal("0.00"), description="Valor nominal em moeda corrente")
    tipo: TransactionType = Field(..., description="DEBITO ou CREDITO")
    contraparte: Counterparty = Field(..., description="Contraparte envolvida no pagamento/recebimento")
    classificacao: ClassificationDetail = Field(..., description="Partidas dobradas e categoria")
    fiscal_compliance: FiscalComplianceDetail = Field(..., description="Parecer de compliance tributário")
