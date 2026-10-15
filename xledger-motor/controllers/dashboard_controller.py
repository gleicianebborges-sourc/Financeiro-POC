"""Controller de Orquestração do Dashboard em Tela Única (SinglePage).

Alimenta as métricas dos 4 quadrantes operacionais e expõe gerador de eventos SSE
para reatividade contínua no frontend sem rolagem vertical.
"""

import asyncio
import json
from decimal import Decimal
from typing import Any, AsyncGenerator, Dict, List, Optional
from models.transaction import ProcessedTransaction
from views.dashboard_view import SinglePageDashboardPresenter
from controllers.statement_controller import BankStatementController


class DashboardController:
    """Controlador do Dashboard de 4 quadrantes sincronizados em tempo real."""

    def __init__(
        self,
        statement_controller: BankStatementController,
        presenter: Optional[SinglePageDashboardPresenter] = None
    ) -> None:
        self.statement_controller = statement_controller
        self.presenter = presenter or SinglePageDashboardPresenter()

    def get_dashboard_state(self) -> Dict[str, Any]:
        """Obtém o payload dos 4 quadrantes a partir do histórico de transações processadas."""
        transactions = self.statement_controller.get_processed_transactions()
        if not transactions:
            # Estado inicial mock/demonstrativo se ainda não houver transações ingeridas
            return self._get_default_mock_state()
        return self.presenter.render(transactions)

    async def stream_metrics(self, interval_seconds: float = 3.0) -> AsyncGenerator[str, None]:
        """Gera stream contínuo SSE (Server-Sent Events) para atualização reativa do dashboard."""
        while True:
            state = self.get_dashboard_state()
            yield f"data: {json.dumps(state)}\n\n"
            await asyncio.sleep(interval_seconds)

    def _get_default_mock_state(self) -> Dict[str, Any]:
        """Estado demonstrativo idêntico ao modelo da especificação técnica."""
        return {
            "metadata": {
                "layout": "viewport-lock-single-screen",
                "versao_contrato": "v1.0-jev-rag",
                "total_transacoes": 460,
            },
            "quadrante_1_fluxo_caixa": {
                "titulo": "Q1: Liquidez & Fluxo de Caixa",
                "total_entradas": 650000.00,
                "total_saidas": 221090.00,
                "saldo_liquido": 428910.00,
                "burn_rate_mensal": 68080.00,
                "runway_projetado_meses": 6.3,
                "status_liquidez": "SAUDAVEL"
            },
            "quadrante_2_eficiencia_ia": {
                "titulo": "Q2: Eficiência IA (Jev vs RAG)",
                "taxa_automacao_jev": 91.4,
                "taxa_recorrencia_rag": 8.6,
                "total_processadas": 460,
                "latencia_media_jev_ms": 185,
                "total_jev": 420,
                "total_rag": 40,
                "pendencias_intervencao": 0,
                "alerta_intervencao_humana": False
            },
            "quadrante_3_termometro_fiscal": {
                "titulo": "Q3: Termômetro Fiscal (CNPJ ➔ CPF)",
                "volume_total_pj_para_cpf": 65000.00,
                "limite_e_financeira_alerta": True,
                "percentual_teto_efinanceira": 82.6,
                "total_irrf_provisionado": 1500.00,
                "alertas_confusao_patrimonial": 0,
                "status_risco_fiscal": "ATENCAO"
            },
            "quadrante_4_dre_dinamica": {
                "titulo": "Q4: DRE Dinâmica & Evolução Contábil",
                "receita_bruta": 650000.00,
                "despesas_dedutiveis": 215000.00,
                "despesas_indedutiveis": 6090.00,
                "lucro_liquido_contabil": 375800.00,
                "margem_liquida_pct": 57.8,
                "custo_tributario_retido": 18400.00
            }
        }
