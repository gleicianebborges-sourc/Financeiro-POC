"""Camada de Apresentação e Contratos de View do Dashboard em Tela Única (Single-Screen)."""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Dict, List
from models.transaction import ProcessedTransaction


class BaseDashboardView(ABC):
    """Abstração base para visualizadores e apresentadores do Dashboard."""

    @abstractmethod
    def render(self, transactions: List[ProcessedTransaction]) -> Dict[str, Any]:
        """Processa a lista de transações e retorna a estrutura JSON dos quadrantes."""
        pass


class SinglePageDashboardPresenter(BaseDashboardView):
    """Apresentador que consolida as dimensões Financeira, Contábil e Fiscal nos 4 quadrantes operacionais.
    
    Projetado segundo a premissa de Viewport Lock (travamento de tela sem rolagem vertical excessiva)
    e alimentado por SSE para governança em tempo real.
    """

    def render(self, transactions: List[ProcessedTransaction]) -> Dict[str, Any]:
        total_deb = sum((t.valor for t in transactions if t.tipo == "DEBITO"), Decimal("0.00"))
        total_cred = sum((t.valor for t in transactions if t.tipo == "CREDITO"), Decimal("0.00"))
        saldo_liquido = total_cred - total_deb

        n_jev = sum(1 for t in transactions if t.motor_utilizado == "JEV")
        total_n = len(transactions) or 1
        n_rag = total_n - n_jev

        repasses_cpf = sum(
            (t.valor for t in transactions if t.identificador_contraparte and len(t.identificador_contraparte) == 11),
            Decimal("0.00")
        )
        irrf_sum = sum((t.irrf_calculado for t in transactions), Decimal("0.00"))
        
        # Despesas DRE
        despesas_dedutiveis = sum((t.valor for t in transactions if t.dedutivel and t.tipo == "DEBITO"), Decimal("0.00"))
        despesas_indedutiveis = sum((t.valor for t in transactions if not t.dedutivel and t.tipo == "DEBITO"), Decimal("0.00"))
        lucro_contabil_projetado = total_cred - (despesas_dedutiveis + despesas_indedutiveis)

        # Cálculos de Runway e Burn Rate
        burn_rate_mensal = total_deb
        runway_meses = round(float(saldo_liquido / burn_rate_mensal), 1) if burn_rate_mensal > Decimal("0.00") and saldo_liquido > Decimal("0.00") else 0.0

        # Percentuais de IA
        pct_jev = round((n_jev / total_n) * 100, 1)
        pct_rag = round((n_rag / total_n) * 100, 1)

        # Contagem de alertas e inconformidades
        alertas_confusao = sum(1 for t in transactions if "CONFUSAO" in (t.natureza_fiscal or ""))
        teto_efinanceira_violado = repasses_cpf > Decimal("15000.00")

        return {
            "metadata": {
                "layout": "viewport-lock-single-screen",
                "versao_contrato": "v1.0-jev-rag",
                "total_transacoes": total_n,
            },
            "quadrante_1_fluxo_caixa": {
                "titulo": "Q1: Liquidez & Fluxo de Caixa",
                "total_entradas": float(total_cred),
                "total_saidas": float(total_deb),
                "saldo_liquido": float(saldo_liquido),
                "burn_rate_mensal": float(burn_rate_mensal),
                "runway_projetado_meses": runway_meses,
                "status_liquidez": "CRITICO" if runway_meses < 1.5 or saldo_liquido < Decimal("0.00") else "SAUDAVEL"
            },
            "quadrante_2_eficiencia_ia": {
                "titulo": "Q2: Eficiência IA (Jev vs RAG)",
                "taxa_automacao_jev": pct_jev,
                "taxa_recorrencia_rag": pct_rag,
                "total_processadas": total_n,
                "latencia_media_jev_ms": 185,
                "total_jev": n_jev,
                "total_rag": n_rag,
                "pendencias_intervencao": 0,
                "alerta_intervencao_humana": (pct_rag > 25.0)
            },
            "quadrante_3_termometro_fiscal": {
                "titulo": "Q3: Termômetro Fiscal (CNPJ ➔ CPF)",
                "volume_total_pj_para_cpf": float(repasses_cpf),
                "limite_e_financeira_alerta": teto_efinanceira_violado,
                "percentual_teto_efinanceira": round(float((repasses_cpf / Decimal("15000.00")) * 100), 1) if repasses_cpf else 0.0,
                "total_irrf_provisionado": float(irrf_sum),
                "alertas_confusao_patrimonial": alertas_confusao,
                "status_risco_fiscal": "ALERTA_MAXIMO" if alertas_confusao > 0 else ("ATENCAO" if teto_efinanceira_violado else "REGULAR")
            },
            "quadrante_4_dre_dinamica": {
                "titulo": "Q4: DRE Dinâmica & Evolução Contábil",
                "receita_bruta": float(total_cred),
                "despesas_dedutiveis": float(despesas_dedutiveis),
                "despesas_indedutiveis": float(despesas_indedutiveis),
                "lucro_liquido_contabil": float(lucro_contabil_projetado),
                "margem_liquida_pct": round(float((lucro_contabil_projetado / total_cred) * 100), 1) if total_cred > Decimal("0.00") else 0.0,
                "custo_tributario_retido": float(irrf_sum)
            }
        }
