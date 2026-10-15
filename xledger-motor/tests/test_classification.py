import asyncio
import os
import sys
import unittest
from datetime import date
from decimal import Decimal

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from models.transaction import BankStatementTransaction
from models.schemas.transaction import (
    TransactionClassificationOutput,
    EngineType,
    FinancialCategory,
    FiscalNature,
)
from services.jev_client import JevOpenRouterClient
from services.rag_service import RAGService
from services.classification_service import HybridClassificationPipelineService
from services.compliance_service import FiscalComplianceService


class TestHybridClassificationPipeline(unittest.IsolatedAsyncioTestCase):
    """Bateria de testes da lógica de decisão e chaveamento da esteira híbrida."""

    async def asyncSetUp(self) -> None:
        self.compliance = FiscalComplianceService()
        self.jev = JevOpenRouterClient(mock_mode=True)
        self.rag = RAGService()
        self.pipeline = HybridClassificationPipelineService(
            jev_client=self.jev,
            rag_service=self.rag,
            fiscal_compliance=self.compliance,
            confidence_threshold=0.90,
        )

    async def test_fast_track_jev_score_high_cnpj(self) -> None:
        """Transação operacional com CNPJ e histórico de rotina deve seguir Fast-Track JEV."""
        tx = BankStatementTransaction(
            entity_id="TX-FAST-01",
            data=date(2026, 10, 1),
            valor=Decimal("250.00"),
            tipo="DEBITO",
            descricao_bruta="TARIFA BANCARIA CESTA PJ",
            documento="DOC101",
            canal="TARIFAS",
            identificador_contraparte="00000000000191",
            nome_contraparte="Banco do Brasil S.A."
        )

        output, processed = await self.pipeline.process_single_transaction(tx)

        self.assertEqual(processed.motor_utilizado, "JEV")
        self.assertGreaterEqual(output.classificacao.confidence_score, 0.90)
        self.assertEqual(output.classificacao.categoria_financeira, FinancialCategory.OPEX)
        self.assertTrue(output.classificacao.dedutivel)

    async def test_mandatory_rag_escalation_for_cpf(self) -> None:
        """Qualquer transação com favorecido sob CPF (11 dígitos) DEVE desviar para o RAG."""
        tx = BankStatementTransaction(
            entity_id="TX-CPF-01",
            data=date(2026, 10, 2),
            valor=Decimal("8000.00"),
            tipo="DEBITO",
            descricao_bruta="PAGAMENTO TARIFA POSTO",  # Mesmo com texto de rotina, o fato de ser CPF força RAG
            documento="PIX102",
            canal="PIX",
            identificador_contraparte="12345678901",  # 11 dígitos -> CPF
            nome_contraparte="Carlos Drummond"
        )

        output, processed = await self.pipeline.process_single_transaction(tx)

        self.assertEqual(processed.motor_utilizado, "RAG_LLM")
        self.assertEqual(output.classificacao.motor_usado, EngineType.RAG_LLM)

    async def test_rag_escalation_low_confidence_cnpj(self) -> None:
        """Transação com descrição ambígua gerando score < 0.90 no JEV deve desviar para RAG."""
        tx = BankStatementTransaction(
            entity_id="TX-AMBIGUOUS-01",
            data=date(2026, 10, 3),
            valor=Decimal("1200.00"),
            tipo="DEBITO",
            descricao_bruta="LANCAMENTO DIVERSO EXTRAORDINARIO ALUGUEL EQUIPAMENTO",
            documento="TED103",
            canal="TED",
            identificador_contraparte="12345678000195",  # CNPJ
            nome_contraparte="Locadora Alfa Ltda"
        )

        output, processed = await self.pipeline.process_single_transaction(tx)

        self.assertEqual(processed.motor_utilizado, "RAG_LLM")


if __name__ == "__main__":
    unittest.main()
