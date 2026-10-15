import os
import sys
import unittest
from datetime import date
from decimal import Decimal

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from models.transaction import BankStatementTransaction
from models.schemas.compliance import ComplianceDecision
from models.schemas.transaction import (
    TransactionClassificationOutput,
    TransactionType,
    FinancialCategory,
    FiscalNature,
    ComplianceStatus,
    EngineType,
    Counterparty,
    ClassificationDetail,
    FiscalComplianceDetail,
)
from services.compliance_service import FiscalComplianceService
from services.rag_service import RAGService
from services.classification_service import HybridClassificationPipelineService


class TestFiscalComplianceRules(unittest.IsolatedAsyncioTestCase):
    """Bateria de testes das regras normativas da Receita Federal e Código Civil."""

    def setUp(self) -> None:
        self.compliance = FiscalComplianceService()
        self.rag = RAGService()

    def test_efinanceira_pj_15k_threshold(self) -> None:
        """Movimentação de PJ >= R$ 15.000 deve disparar alerta de e-Financeira."""
        tx_out = TransactionClassificationOutput(
            transaction_id="TX-PJ-15K",
            data=date(2026, 10, 5),
            valor=Decimal("15000.00"),
            tipo=TransactionType.DEBITO,
            contraparte=Counterparty(
                identificador="12345678000195",  # CNPJ (14 dígitos)
                nome="Fornecedor Corporativo S.A."
            ),
            classificacao=ClassificationDetail(
                categoria_financeira=FinancialCategory.FORNECEDORES,
                centro_custo="OPERACIONAL",
                conta_debito="3.1.2.01",
                conta_credito="1.1.1.02",
                dedutivel=True,
                confidence_score=0.98,
                motor_usado=EngineType.JEV
            ),
            fiscal_compliance=FiscalComplianceDetail(
                natureza_pj_pf=FiscalNature.OPERACIONAL,
                limite_e_financeira_atingido=False,
                status_conformidade=ComplianceStatus.REGULAR
            )
        )

        audit = self.compliance.audit_transaction(tx_out)

        self.assertTrue(audit.alerta_e_financeira)
        self.assertIn("TETO_EFINANCEIRA_PJ_15K", audit.flags_de_risco)
        self.assertEqual(audit.status_compliance, ComplianceDecision.ALERTA)

    def test_efinanceira_pf_5k_threshold(self) -> None:
        """Movimentação individual para CPF >= R$ 5.000 deve disparar alerta de e-Financeira."""
        tx_out = TransactionClassificationOutput(
            transaction_id="TX-PF-5K",
            data=date(2026, 10, 6),
            valor=Decimal("5000.00"),
            tipo=TransactionType.DEBITO,
            contraparte=Counterparty(
                identificador="12345678901",  # CPF (11 dígitos)
                nome="Sócio Carlos"
            ),
            classificacao=ClassificationDetail(
                categoria_financeira=FinancialCategory.RETIRO_SOCIOS,
                centro_custo="DIRETORIA",
                conta_debito="2.3.1.05",
                conta_credito="1.1.1.02",
                dedutivel=False,
                confidence_score=0.98,
                motor_usado=EngineType.RAG_LLM
            ),
            fiscal_compliance=FiscalComplianceDetail(
                natureza_pj_pf=FiscalNature.LUCRO,
                limite_e_financeira_atingido=False,
                status_conformidade=ComplianceStatus.REGULAR
            )
        )

        audit = self.compliance.audit_transaction(tx_out)

        self.assertTrue(audit.alerta_e_financeira)
        self.assertIn("TETO_EFINANCEIRA_PF_5K", audit.flags_de_risco)

    def test_distribuicao_lucros_retencao_10_pct_excedente_50k(self) -> None:
        """Distribuição de lucros acima de R$ 50.000 no mês por CPF deve reter 10% de IRRF sobre excedente."""
        cpf = "98765432100"
        
        # 1ª Parcela: R$ 40.000 (Dentro do limite de R$ 50k -> Isento)
        tx1 = TransactionClassificationOutput(
            transaction_id="TX-LUCRO-01",
            data=date(2026, 10, 10),
            valor=Decimal("40000.00"),
            tipo=TransactionType.DEBITO,
            contraparte=Counterparty(identificador=cpf, nome="Sócia Mariana"),
            classificacao=ClassificationDetail(
                categoria_financeira=FinancialCategory.RETIRO_SOCIOS,
                centro_custo="DIRETORIA",
                conta_debito="2.3.1.05",
                conta_credito="1.1.1.02",
                dedutivel=False,
                confidence_score=0.98,
                motor_usado=EngineType.RAG_LLM
            ),
            fiscal_compliance=FiscalComplianceDetail(
                natureza_pj_pf=FiscalNature.LUCRO,
                status_conformidade=ComplianceStatus.REGULAR
            )
        )
        audit1 = self.compliance.audit_transaction(tx1)
        self.assertEqual(audit1.valor_retido_irrf, Decimal("0.00"))
        self.assertEqual(audit1.acumulado_mes_cpf, Decimal("40000.00"))

        # 2ª Parcela: R$ 25.000 (Acumula R$ 65.000 -> Excede R$ 15.000 -> Retenção de 10% = R$ 1.500)
        tx2 = TransactionClassificationOutput(
            transaction_id="TX-LUCRO-02",
            data=date(2026, 10, 15),
            valor=Decimal("25000.00"),
            tipo=TransactionType.DEBITO,
            contraparte=Counterparty(identificador=cpf, nome="Sócia Mariana"),
            classificacao=ClassificationDetail(
                categoria_financeira=FinancialCategory.RETIRO_SOCIOS,
                centro_custo="DIRETORIA",
                conta_debito="2.3.1.05",
                conta_credito="1.1.1.02",
                dedutivel=False,
                confidence_score=0.98,
                motor_usado=EngineType.RAG_LLM
            ),
            fiscal_compliance=FiscalComplianceDetail(
                natureza_pj_pf=FiscalNature.LUCRO,
                status_conformidade=ComplianceStatus.REGULAR
            )
        )
        audit2 = self.compliance.audit_transaction(tx2)
        
        self.assertEqual(audit2.acumulado_mes_cpf, Decimal("65000.00"))
        self.assertEqual(audit2.valor_retido_irrf, Decimal("1500.00"))  # 10% de (65k - 50k = 15k)
        self.assertIn("EXCEDENTE_LUCROS_50K", audit2.flags_de_risco)

    async def test_confusao_patrimonial_art_50_codigo_civil(self) -> None:
        """Despesa estritamente pessoal paga pela PJ deve ser isolada com Alerta Máximo e bloqueada."""
        tx_dict = {
            "id": "TX-CONFUSAO-01",
            "data": "2026-10-12",
            "valor": "4500.00",
            "tipo": "DEBITO",
            "descricao_bruta": "PAGAMENTO MENSALIDADE ESCOLA INTERNACIONAL FILHOS SOCIO",
            "identificador_contraparte": "12345678901",
            "nome_contraparte": "Escola Internacional"
        }

        output = await self.rag.disambiguate_and_classify(tx_dict)
        audit = self.compliance.audit_transaction(output)

        self.assertEqual(audit.status_compliance, ComplianceDecision.BLOQUEADO)
        self.assertIn("CONFUSAO_PATRIMONIAL_ART50_CC", audit.flags_de_risco)
        self.assertFalse(output.classificacao.dedutivel)
        self.assertEqual(output.classificacao.categoria_financeira, FinancialCategory.RETIRO_SOCIOS)
        self.assertIn("Adiantamentos a Sócios", output.classificacao.conta_debito)


if __name__ == "__main__":
    unittest.main()
