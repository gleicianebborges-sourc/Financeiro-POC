"""Motor de Regras Fiscais e Compliance Tributário (CNPJ ➔ CPF, e-Financeira).

Monitora e intercepta movimentações entre a Pessoa Jurídica e Pessoas Físicas (sócios e colaboradores),
gerenciando limites da IN RFB 1571/2015, retenções na fonte de 10% sobre lucros e confusão patrimonial.
"""

from decimal import Decimal
from typing import Dict, List, Optional
from models.schemas.compliance import FiscalComplianceOutput, ComplianceDecision
from models.schemas.transaction import (
    TransactionClassificationOutput,
    FiscalNature,
    ComplianceStatus,
)


class FiscalComplianceService:
    """Serviço de compliance fiscal responsável por validar limites e auditar contingências."""

    def __init__(self) -> None:
        # Acumuladores de movimentação mensal em memória: CPF -> Decimal
        self._acumulado_mensal_cpf: Dict[str, Decimal] = {}
        # Acumulador total PJ para CPF no mês
        self._volume_total_pj_para_cpf: Decimal = Decimal("0.00")
        
        # Limites normativos da Receita Federal
        self.TETO_EFINANCEIRA_PF = Decimal("5000.00")
        self.TETO_EFINANCEIRA_PJ = Decimal("15000.00")
        self.TETO_ISENCAO_LUCROS = Decimal("50000.00")
        self.ALIQUOTA_IRRF_LUCROS_EXCEDENTE = Decimal("0.10")

    def reset_acumuladores(self) -> None:
        """Reinicia os acumuladores para nova competência mensal."""
        self._acumulado_mensal_cpf.clear()
        self._volume_total_pj_para_cpf = Decimal("0.00")

    def get_acumulado_cpf(self, cpf: str) -> Decimal:
        """Retorna o acumulado do mês para um determinado CPF."""
        clean = "".join(c for c in cpf if c.isdigit())
        return self._acumulado_mensal_cpf.get(clean, Decimal("0.00"))

    def get_volume_total_pj_cpf(self) -> Decimal:
        """Retorna o volume total consolidado de repasses PJ -> CPF."""
        return self._volume_total_pj_para_cpf

    def audit_transaction(self, tx: TransactionClassificationOutput) -> FiscalComplianceOutput:
        """Aplica auditoria fiscal profunda e gera o parecer estrito de conformidade."""
        doc = tx.contraparte.identificador
        is_cpf = tx.contraparte.is_cpf
        valor = tx.valor
        natureza = tx.fiscal_compliance.natureza_pj_pf

        flags_risco: List[str] = []
        status = ComplianceDecision.APROVADO
        irrf_a_reter = Decimal("0.00")
        inss_a_recolher = tx.fiscal_compliance.inss_devido
        justificativas: List[str] = []

        # 1. Auditoria de Confusão Patrimonial (Despesas Pessoais do Sócio via PJ)
        if natureza == FiscalNature.ALERTA_CONFUSAO:
            flags_risco.append("CONFUSAO_PATRIMONIAL_ART50_CC")
            status = ComplianceDecision.BLOQUEADO
            justificativas.append(
                "VIOLAÇÃO DO PRINCÍPIO DA ENTIDADE: Despesa de natureza pessoal assumida pela PJ. "
                "Classificado compulsoriamente como adiantamento a sócio (ativo circulante). "
                "Indedutível para IRPJ/CSLL (Risco de desconsideração da personalidade jurídica)."
            )

        # 2. Movimentações PJ -> CPF
        acumulado_atual = Decimal("0.00")
        alerta_efinanceira = False

        if is_cpf:
            acumulado_anterior = self.get_acumulado_cpf(doc)
            acumulado_atual = acumulado_anterior + valor
            self._acumulado_mensal_cpf[doc] = acumulado_atual
            self._volume_total_pj_para_cpf += valor

            # 2.1 Monitoramento e-Financeira (PF teto R$ 5.000 / Global PJ repasses R$ 15.000)
            if acumulado_atual >= self.TETO_EFINANCEIRA_PF or valor >= self.TETO_EFINANCEIRA_PF:
                alerta_efinanceira = True
                flags_risco.append("TETO_EFINANCEIRA_PF_5K")
                if status != ComplianceDecision.BLOQUEADO:
                    status = ComplianceDecision.ALERTA
                justificativas.append(
                    f"Alerta e-Financeira: Montante acumulado no mês para o CPF atingiu R$ {acumulado_atual:,.2f} "
                    f"(limite individual de reporte automático: R$ {self.TETO_EFINANCEIRA_PF:,.2f})."
                )

            # 2.2 Pró-Labore vs Distribuição de Lucros
            if natureza == FiscalNature.PRO_LABORE:
                if status != ComplianceDecision.BLOQUEADO:
                    status = ComplianceDecision.APROVADO
                irrf_a_reter = tx.fiscal_compliance.irrf_retido
                justificativas.append(
                    f"Pró-Labore regular: Retenção de INSS (R$ {inss_a_recolher:,.2f}) e IRRF progressivo (R$ {irrf_a_reter:,.2f})."
                )

            elif natureza == FiscalNature.LUCRO:
                # Regra dos R$ 50.000 por mês
                if acumulado_atual > self.TETO_ISENCAO_LUCROS:
                    flags_risco.append("EXCEDENTE_LUCROS_50K")
                    if status != ComplianceDecision.BLOQUEADO:
                        status = ComplianceDecision.ALERTA
                    
                    # Cálculo da retenção de 10% sobre o excedente
                    if acumulado_anterior >= self.TETO_ISENCAO_LUCROS:
                        excedente = valor
                    else:
                        excedente = acumulado_atual - self.TETO_ISENCAO_LUCROS
                    
                    irrf_a_reter = (excedente * self.ALIQUOTA_IRRF_LUCROS_EXCEDENTE).quantize(Decimal("0.01"))
                    justificativas.append(
                        f"Distribuição de Lucros acima de R$ 50.000,00 no mês (Total acumulado: R$ {acumulado_atual:,.2f}). "
                        f"Aplicação compulsória de retenção na fonte de 10% de IRRF: R$ {irrf_a_reter:,.2f}."
                    )
                else:
                    if status != ComplianceDecision.BLOQUEADO:
                        status = ComplianceDecision.APROVADO
                    justificativas.append(
                        f"Distribuição de Lucros isenta (Acumulado mês: R$ {acumulado_atual:,.2f} <= R$ 50.000,00)."
                    )
        else:
            # Pessoa Jurídica (CNPJ)
            if valor >= self.TETO_EFINANCEIRA_PJ:
                alerta_efinanceira = True
                flags_risco.append("TETO_EFINANCEIRA_PJ_15K")
                if status != ComplianceDecision.BLOQUEADO:
                    status = ComplianceDecision.ALERTA
                justificativas.append(
                    f"Alerta e-Financeira PJ: Lançamento unitário atingiu R$ {valor:,.2f} "
                    f"(limite PJ de reporte: R$ {self.TETO_EFINANCEIRA_PJ:,.2f})."
                )

        if not justificativas:
            justificativas.append("Operação regular auditada em conformidade com as diretrizes contábeis e fiscais.")

        return FiscalComplianceOutput(
            transacao_id=tx.transaction_id,
            status_compliance=status,
            flags_de_risco=flags_risco,
            valor_retido_irrf=irrf_a_reter,
            inss_a_recolher=inss_a_recolher,
            justificativa_legal=" | ".join(justificativas),
            acumulado_mes_cpf=acumulado_atual,
            alerta_e_financeira=alerta_efinanceira
        )


compliance_service = FiscalComplianceService()
