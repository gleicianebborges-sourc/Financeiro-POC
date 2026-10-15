"""Componentes e formatadores dos 4 quadrantes para CLI e Terminal."""

from typing import Any, Dict


class QuadrantCardsRenderer:
    """Formatador de visualização em texto rico / ASCII para os quadrantes do XLedger."""

    @staticmethod
    def render_cli(payload: Dict[str, Any]) -> str:
        q1 = payload.get("quadrante_1_fluxo_caixa", {})
        q2 = payload.get("quadrante_2_eficiencia_ia", {})
        q3 = payload.get("quadrante_3_termometro_fiscal", {})
        q4 = payload.get("quadrante_4_dre_dinamica", {})

        border = "=" * 80
        divider = "-" * 80

        lines = [
            border,
            "               XLEDGER • MOTOR CONTÁBIL & FISCAL (VIEWPORT LOCK)",
            border,
            f" [Q1: FLUXO DE CAIXA]                          | [Q2: EFICIÊNCIA IA (JEV VS RAG)]",
            f"  • Entradas:   R$ {q1.get('total_entradas', 0):>12,.2f}          |  • Jev (<250ms): {q2.get('taxa_automacao_jev', 0):>5.1f}%",
            f"  • Saídas:     R$ {q1.get('total_saidas', 0):>12,.2f}          |  • RAG Normativo: {q2.get('taxa_recorrencia_rag', 0):>5.1f}%",
            f"  • Saldo Líq:  R$ {q1.get('saldo_liquido', 0):>12,.2f}          |  • Processadas:   {q2.get('total_processadas', 0):>5d}",
            f"  • Runway:     {q1.get('runway_projetado_meses', 0):>5.1f} meses ({q1.get('status_liquidez', '')})     |  • Latência Média: {q2.get('latencia_media_jev_ms', 0)} ms",
            divider,
            f" [Q3: TERMOMETRO FISCAL (CNPJ -> CPF)]          | [Q4: DRE DINAMICA & AUDITORIA]",
            f"  • Repasses CPF: R$ {q3.get('volume_total_pj_para_cpf', 0):>10,.2f}          |  • Receita Bruta: R$ {q4.get('receita_bruta', 0):>10,.2f}",
            f"  • Teto e-Fin:   {q3.get('percentual_teto_efinanceira', 0):>5.1f}% ({'ALERTA' if q3.get('limite_e_financeira_alerta') else 'REGULAR'})          |  • Desp. Dedut:   R$ {q4.get('despesas_dedutiveis', 0):>10,.2f}",
            f"  • IRRF Retido:  R$ {q3.get('total_irrf_provisionado', 0):>10,.2f}          |  • Desp. Indedut: R$ {q4.get('despesas_indedutiveis', 0):>10,.2f}",
            f"  • Conf. Patrim: {q3.get('alertas_confusao_patrimonial', 0):>5d} alertas ({q3.get('status_risco_fiscal', '')})  |  • Margem Líq:    {q4.get('margem_liquida_pct', 0):>5.1f}%",
            border,
        ]
        return "\n".join(lines)
