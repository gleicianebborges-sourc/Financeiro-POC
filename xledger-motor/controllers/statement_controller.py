"""Controladores de Classificação e Ingestão de Extratos Bancários (MVC).

Implementa a hierarquia de controladores com herança polimórfica (BaseClassifierController,
JevClassifierController, RAGClassifierController, HybridOrchestratorController) e a orquestração
assíncrona de ingestão de arquivos OFX/CSV.
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from models.statement import BankStatement
from models.transaction import BankStatementTransaction, ProcessedTransaction
from models.schemas.transaction import TransactionClassificationOutput
from parsers.csv_parser import CSVStatementParser
from parsers.ofx_parser import OFXStatementParser
from services.classification_service import HybridClassificationPipelineService
from services.compliance_service import FiscalComplianceService, compliance_service


# =================== [LAYER 2: CONTROLADORES DE CLASSIFICAÇÃO] ===================

class BaseClassifierController(ABC):
    """Contrato abstrato unificado para os controladores de decisão do XLedger."""

    @abstractmethod
    def classify(self, tx: BankStatementTransaction) -> ProcessedTransaction:
        pass


class JevClassifierController(BaseClassifierController):
    """Controlador síncrono discriminativo de alta velocidade JEV."""

    def __init__(self, api_key: str = "", threshold: float = 0.90) -> None:
        self.api_key = api_key
        self.threshold = threshold

    def classify(self, tx: BankStatementTransaction) -> ProcessedTransaction:
        is_routine = "TARIFA" in tx.descricao_bruta.upper() or "POSTO" in tx.descricao_bruta.upper()
        score = 0.96 if is_routine else 0.72

        return ProcessedTransaction(
            entity_id=tx.id,
            data=tx.data,
            valor=tx.valor,
            tipo=tx.tipo,
            descricao_bruta=tx.descricao_bruta,
            documento=tx.documento,
            canal=tx.canal,
            identificador_contraparte=tx.identificador_contraparte,
            nome_contraparte=tx.nome_contraparte,
            categoria_financeira="OPEX" if is_routine else "INDEFINIDO",
            centro_custo="ADMINISTRATIVO" if is_routine else "GERAL",
            conta_debito="3.1.1.01 - Despesas Operacionais",
            conta_credito="1.1.1.02 - Bancos",
            dedutivel=True,
            confidence_score=score,
            motor_utilizado="JEV",
            natureza_fiscal="OPERACIONAL",
            status_compliance="REGULAR",
            irrf_calculado=Decimal("0.00"),
            alerta_auditoria=None
        )


class RAGClassifierController(BaseClassifierController):
    """Controlador síncrono de auditoria normativa e desambiguação RAG."""

    def __init__(self, vector_store_client: Any = None) -> None:
        self.vector_store = vector_store_client

    def classify(self, tx: BankStatementTransaction) -> ProcessedTransaction:
        is_cpf = bool(tx.identificador_contraparte and len(tx.identificador_contraparte) == 11)
        valor_alto = tx.valor > Decimal("50000.00")
        
        # Despesas pessoais -> Confusão patrimonial
        desc_upper = tx.descricao_bruta.upper()
        is_confusao = any(k in desc_upper for k in ["MERCADO", "ESCOLA", "COLEGIO", "HOSPITAL", "FARMACIA"])

        if is_confusao:
            natureza = "ALERTA_CONFUSAO"
            status = "IRREGULAR"
            irrf = Decimal("0.00")
            motivo = "ALERTA MÁXIMO: Confusão Patrimonial detectada (Art. 50 CC)."
            dedutivel = False
            categoria = "RETIRO_SOCIOS"
            c_debito = "1.1.3.04 - Adiantamento a Sócios (Ativo)"
        elif is_cpf:
            natureza = "LUCRO" if valor_alto else "PRO_LABORE"
            irrf = (tx.valor - Decimal("50000.00")) * Decimal("0.10") if natureza == "LUCRO" else Decimal("0.00")
            status = "ATENCAO" if irrf > Decimal("0.00") else "REGULAR"
            motivo = "Retenção de 10% IRRF sobre excedente de R$ 50k" if irrf > Decimal("0.00") else None
            dedutivel = False
            categoria = "RETIRO_SOCIOS"
            c_debito = "2.3.1.05 - Dividendos Pagos"
        else:
            natureza = "OPERACIONAL"
            status = "REGULAR"
            irrf = Decimal("0.00")
            motivo = None
            dedutivel = True
            categoria = "FORNECEDORES"
            c_debito = "3.1.2.01 - Custos Operacionais"

        return ProcessedTransaction(
            entity_id=tx.id,
            data=tx.data,
            valor=tx.valor,
            tipo=tx.tipo,
            descricao_bruta=tx.descricao_bruta,
            documento=tx.documento,
            canal=tx.canal,
            identificador_contraparte=tx.identificador_contraparte,
            nome_contraparte=tx.nome_contraparte,
            categoria_financeira=categoria,
            centro_custo="DIRETORIA" if is_cpf else "OPERACIONAL",
            conta_debito=c_debito,
            conta_credito="1.1.1.02 - Bancos Conta Movimento",
            dedutivel=dedutivel,
            confidence_score=0.98,
            motor_utilizado="RAG_LLM",
            natureza_fiscal=natureza,
            status_compliance=status,
            irrf_calculado=irrf,
            alerta_auditoria=motivo
        )


class HybridOrchestratorController(BaseClassifierController):
    """Orquestrador híbrido que avalia o threshold do Jev e chaveia para RAG quando necessário."""

    def __init__(self, jev_controller: JevClassifierController, rag_controller: RAGClassifierController) -> None:
        self.jev = jev_controller
        self.rag = rag_controller

    def classify(self, tx: BankStatementTransaction) -> ProcessedTransaction:
        jev_res = self.jev.classify(tx)
        is_cpf = bool(tx.identificador_contraparte and len(tx.identificador_contraparte) == 11)
        if jev_res.confidence_score >= self.jev.threshold and not is_cpf:
            return jev_res
        return self.rag.classify(tx)


# =================== [ORQUESTRADOR DE INGESTÃO E PIPELINE ASYNC] ===================

class BankStatementController:
    """Controller principal responsável pela ingestão de extratos OFX/CSV e execução da esteira."""

    def __init__(
        self,
        pipeline_service: Optional[HybridClassificationPipelineService] = None,
        compliance: Optional[FiscalComplianceService] = None
    ) -> None:
        self.pipeline = pipeline_service or HybridClassificationPipelineService()
        self.compliance = compliance or compliance_service
        self._processed_history: List[ProcessedTransaction] = []

    def get_processed_transactions(self) -> List[ProcessedTransaction]:
        return self._processed_history

    def add_processed_transactions(self, transactions: List[ProcessedTransaction]) -> None:
        self._processed_history.extend(transactions)

    def clear_history(self) -> None:
        self._processed_history.clear()
        self.compliance.reset_acumuladores()

    async def ingest_csv(self, content: str) -> Tuple[List[TransactionClassificationOutput], List[ProcessedTransaction]]:
        """Ingere arquivo CSV de extrato bancário e executa a esteira híbrida."""
        statement = CSVStatementParser.parse(content)
        outputs, processed = await self.pipeline.process_batch(statement.transacoes)
        self.add_processed_transactions(processed)
        return outputs, processed

    async def ingest_ofx(self, content: str) -> Tuple[List[TransactionClassificationOutput], List[ProcessedTransaction]]:
        """Ingere arquivo OFX de extrato bancário e executa a esteira híbrida."""
        statement = OFXStatementParser.parse(content)
        outputs, processed = await self.pipeline.process_batch(statement.transacoes)
        self.add_processed_transactions(processed)
        return outputs, processed

    async def ingest_transactions_batch(
        self,
        transactions: List[BankStatementTransaction]
    ) -> Tuple[List[TransactionClassificationOutput], List[ProcessedTransaction]]:
        """Ingere diretamente uma lista de transações bancárias tipadas."""
        outputs, processed = await self.pipeline.process_batch(transactions)
        self.add_processed_transactions(processed)
        return outputs, processed
