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


class TestRegressionFixes(unittest.IsolatedAsyncioTestCase):
    """Regressões: identificador da contraparte, contingência do JEV e tolerância a falhas do lote."""

    async def asyncSetUp(self) -> None:
        self.compliance = FiscalComplianceService()
        self.rag = RAGService()

    def _make_pipeline(self, jev: JevOpenRouterClient) -> HybridClassificationPipelineService:
        return HybridClassificationPipelineService(
            jev_client=jev,
            rag_service=self.rag,
            fiscal_compliance=self.compliance,
            confidence_threshold=0.90,
        )

    @staticmethod
    def _tx(entity_id: str, valor: str, desc: str, doc_id: str, nome: str) -> BankStatementTransaction:
        return BankStatementTransaction(
            entity_id=entity_id,
            data=date(2026, 10, 5),
            valor=Decimal(valor),
            tipo="DEBITO",
            descricao_bruta=desc,
            documento="DOC",
            canal="PIX",
            identificador_contraparte=doc_id,
            nome_contraparte=nome,
        )

    async def test_identificador_real_preservado(self) -> None:
        """O CPF/CNPJ real deve ser mantido (antes era substituído por placeholder fixo)."""
        pipeline = self._make_pipeline(JevOpenRouterClient(mock_mode=True))
        out_cnpj, _ = await pipeline.process_single_transaction(
            self._tx("TX-ID-01", "100.00", "TARIFA BANCARIA", "99888777000166", "Banco X")
        )
        out_cpf, _ = await pipeline.process_single_transaction(
            self._tx("TX-ID-02", "1000.00", "DISTRIBUICAO DE LUCROS", "98765432100", "Mariana Rios")
        )
        self.assertEqual(out_cnpj.contraparte.identificador, "99888777000166")
        self.assertEqual(out_cpf.contraparte.identificador, "98765432100")

    async def test_acumuladores_separados_por_cpf(self) -> None:
        """Sócios distintos não podem ter seus repasses somados no mesmo acumulador."""
        pipeline = self._make_pipeline(JevOpenRouterClient(mock_mode=True))
        await pipeline.process_single_transaction(
            self._tx("TX-AC-01", "40000.00", "DISTRIBUICAO DE LUCROS", "12345678901", "Carlos Drummond")
        )
        out, _ = await pipeline.process_single_transaction(
            self._tx("TX-AC-02", "40000.00", "DISTRIBUICAO DE LUCROS", "98765432100", "Mariana Rios")
        )
        self.assertEqual(self.compliance.get_acumulado_cpf("12345678901"), Decimal("40000.00"))
        self.assertEqual(self.compliance.get_acumulado_cpf("98765432100"), Decimal("40000.00"))
        # 40k por CPF está abaixo do teto de 50k: nenhuma retenção
        self.assertEqual(out.fiscal_compliance.irrf_retido, Decimal("0.00"))

    async def test_resposta_invalida_jev_aciona_rag(self) -> None:
        """Resposta fora do schema vinda do OpenRouter deve desviar para o RAG sem quebrar."""
        jev = JevOpenRouterClient(api_key="sk-or-v1-real-key", mock_mode=False, max_retries=1)

        class _FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"choices": [{"message": {"content": "{\"campo\": \"fora do schema\"}"}}]}

        class _FakeClient:
            def __init__(self, *args, **kwargs) -> None:
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc) -> None:
                return None

            async def post(self, *args, **kwargs):
                return _FakeResponse()

        from unittest.mock import patch
        with patch("services.jev_client.httpx.AsyncClient", _FakeClient):
            pipeline = self._make_pipeline(jev)
            _, processed = await pipeline.process_single_transaction(
                self._tx("TX-INV-01", "300.00", "TARIFA BANCARIA", "99888777000166", "Banco X")
            )
        self.assertEqual(processed.motor_utilizado, "RAG_LLM")

    async def test_lote_tolera_falha_individual(self) -> None:
        """Uma transação com erro não pode derrubar o processamento do lote inteiro."""
        pipeline = self._make_pipeline(JevOpenRouterClient(mock_mode=True))
        ok_tx = self._tx("TX-OK", "100.00", "TARIFA BANCARIA", "99888777000166", "Banco X")
        bad_tx = self._tx("TX-BAD", "100.00", "TARIFA BANCARIA", "99888777000166", "Banco X")

        original = pipeline.process_single_transaction

        async def _flaky(tx):
            if tx.id == "TX-BAD":
                raise RuntimeError("falha simulada")
            return await original(tx)

        pipeline.process_single_transaction = _flaky  # type: ignore[method-assign]
        outputs, processed = await pipeline.process_batch([ok_tx, bad_tx])

        self.assertEqual(len(processed), 1)
        self.assertEqual(processed[0].id, "TX-OK")


if __name__ == "__main__":
    unittest.main()
