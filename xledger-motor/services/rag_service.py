"""Serviço de busca vetorial normativa e desambiguação contábil/fiscal (RAG).

Recupera base normativa da Receita Federal, Código Civil, plano de contas e
histórico do livro razão para contextualização de lançamentos bancários complexos.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional
from config.database import db_manager, VectorDocument
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
from models.schemas.compliance import FiscalComplianceOutput, ComplianceDecision

logger = logging.getLogger("xledger.rag_service")


class RAGService:
    """Motor de recuperação vetorial normativa e desambiguação tributária."""

    def __init__(self) -> None:
        self.vector_store = db_manager.vector_store
        # Base de contexto corporativo (mock de DRE, passivos e sócios cadastrados)
        self._empresa_lucro_liquido_recente = Decimal("450000.00")
        self._possui_passivo_previdenciario = False
        self._socios_cadastrados = {
            "12345678901": {"nome": "Carlos Drummond", "cargo": "SOCIO_ADMINISTRADOR", "participacao_pct": 50.0},
            "98765432100": {"nome": "Mariana Rios", "cargo": "SOCIO_COTISTA", "participacao_pct": 50.0},
        }

    async def retrieve_normative_context(self, query: str) -> List[VectorDocument]:
        """Recupera as instruções normativas e orientações contábeis pertinentes."""
        return await self.vector_store.search(query, limit=3)

    async def disambiguate_and_classify(
        self,
        tx_dict: Dict[str, Any],
        acumulado_mes_cpf: Decimal = Decimal("0.00")
    ) -> TransactionClassificationOutput:
        """Executa a rota de desambiguação RAG para transações com baixa confiança ou envolvendo CPF."""
        desc = str(tx_dict.get("descricao_bruta", "")).upper()
        contraparte_id = str(tx_dict.get("identificador_contraparte", ""))
        digits = "".join(c for c in contraparte_id if c.isdigit())
        is_cpf = len(digits) == 11
        nome_contraparte = str(tx_dict.get("nome_contraparte", "Favorecido Desconhecido"))
        
        valor = Decimal(str(tx_dict.get("valor", "0.00")))
        tipo_str = str(tx_dict.get("tipo", "DEBITO")).upper()
        tipo = TransactionType.CREDITO if "CRED" in tipo_str else TransactionType.DEBITO

        from datetime import date
        raw_date = tx_dict.get("data")
        if isinstance(raw_date, str):
            tx_date = date.fromisoformat(raw_date)
        elif isinstance(raw_date, date):
            tx_date = raw_date
        else:
            tx_date = date.today()

        # 1. Recuperação normativa do Vector DB
        normas = await self.retrieve_normative_context(
            f"transferência bancária CPF sócios e-Financeira distribuição lucros confusão patrimonial {desc}"
        )
        contexto_normas = " | ".join(d.titulo for d in normas)

        # 2. Avaliação de Confusão Patrimonial (Despesas Pessoais pagas pela PJ)
        keywords_confusao = [
            "COLEGIO", "ESCOLA", "FACULDADE", "MERCADO", "SUPERMERCADO",
            "FARMACIA", "HOSPITAL", "CLINICA", "CONDOMINIO RESIDENCIAL",
            "IPTU RESIDENCIAL", "PLANO DE SAUDE DEPENDENTE", "ACADEMIA", "VIAGEM LAZER"
        ]
        is_confusao_patrimonial = any(kw in desc for kw in keywords_confusao)

        # 3. Regras Fiscais Específicas
        if is_confusao_patrimonial:
            # Art. 50 do Código Civil - Indedutibilidade para IRPJ/CSLL
            categoria = FinancialCategory.RETIRO_SOCIOS
            natureza = FiscalNature.ALERTA_CONFUSAO
            status = ComplianceStatus.IRREGULAR
            dedutivel = False
            c_debito = "1.1.3.04 - Adiantamentos a Sócios e Diretores (Mútuo)"
            c_credito = "1.1.1.02 - Bancos Conta Movimento"
            centro = "DIRETORIA"
            irrf = Decimal("0.00")
            inss = Decimal("0.00")
            motivo = (
                "ALERTA MÁXIMO DE CONFUSÃO PATRIMONIAL (Art. 50 Código Civil): "
                f"Identificado pagamento de despesa estritamente pessoal via PJ ('{desc}'). "
                "Classificado compulsoriamente como adiantamento a sócio (ativo circulante). "
                "Glosado para fins de IRPJ/CSLL."
            )

        elif is_cpf:
            # Transação envolvendo CPF (Sócios, administradores ou prestadores)
            # Verifica pró-labore vs lucros
            is_pro_labore_hint = any(k in desc for k in ["PRO-LABORE", "PRO LABORE", "REMUNERACAO", "HONORARIO"])
            
            # Se for pró-labore
            if is_pro_labore_hint:
                categoria = FinancialCategory.FOLHA_PAGAMENTO
                natureza = FiscalNature.PRO_LABORE
                status = ComplianceStatus.REGULAR
                dedutivel = True
                c_debito = "3.1.1.05 - Pró-Labore e Honorários de Gestão"
                c_credito = "1.1.1.02 - Bancos Conta Movimento"
                centro = "DIRETORIA"
                inss = (valor * Decimal("0.11")).quantize(Decimal("0.01"))
                irrf = self._calcular_irrf_progressivo(valor - inss)
                motivo = (
                    "Pró-Labore validado: Apurado INSS segurado (11%) e retenção de IRRF pela Tabela Progressiva."
                )
            else:
                # Distribuição de Lucros ou Retiro de Sócios
                # Validação RAG: 1. Empresa tem lucro? 2. Tem débito previdenciário?
                if self._empresa_lucro_liquido_recente <= Decimal("0.00"):
                    # Sem lucro apurado: converte para mútuo
                    categoria = FinancialCategory.RETIRO_SOCIOS
                    natureza = FiscalNature.ALERTA_CONFUSAO
                    status = ComplianceStatus.ATENCAO
                    dedutivel = False
                    c_debito = "1.1.3.04 - Mútuo a Sócios"
                    c_credito = "1.1.1.02 - Bancos Conta Movimento"
                    centro = "DIRETORIA"
                    irrf = Decimal("0.00")
                    inss = Decimal("0.00")
                    motivo = (
                        "Impedimento de Distribuição de Lucros: DRE trimestral não aponta lucro contábil suficiente. "
                        "Lançamento convertido preventivamente em Mútuo Ativo."
                    )
                elif self._possui_passivo_previdenciario:
                    # Art. 32 Lei 4.357/64
                    categoria = FinancialCategory.RETIRO_SOCIOS
                    natureza = FiscalNature.ALERTA_CONFUSAO
                    status = ComplianceStatus.IRREGULAR
                    dedutivel = False
                    c_debito = "1.1.3.04 - Mútuo a Sócios"
                    c_credito = "1.1.1.02 - Bancos Conta Movimento"
                    centro = "DIRETORIA"
                    irrf = Decimal("0.00")
                    inss = Decimal("0.00")
                    motivo = (
                        "Bloqueio Legal (Art. 32 da Lei 4.357/64): Débitos previdenciários impeditivos para distribuição de lucros."
                    )
                else:
                    # Distribuição de lucros regular
                    categoria = FinancialCategory.RETIRO_SOCIOS
                    natureza = FiscalNature.LUCRO
                    dedutivel = False
                    c_debito = "2.3.1.05 - Dividendos e Lucros Distribuídos"
                    c_credito = "1.1.1.02 - Bancos Conta Movimento"
                    centro = "DIRETORIA"
                    inss = Decimal("0.00")

                    # Regra de retenção: Acumulado no mês excedente a R$ 50.000,00 por CPF
                    novo_acumulado = acumulado_mes_cpf + valor
                    limite_50k = Decimal("50000.00")
                    
                    if novo_acumulado > limite_50k:
                        # Se o acumulado anterior já estava acima de 50k, incide 10% sobre todo o valor atual
                        if acumulado_mes_cpf >= limite_50k:
                            excedente = valor
                        else:
                            excedente = novo_acumulado - limite_50k
                        
                        irrf = (excedente * Decimal("0.10")).quantize(Decimal("0.01"))
                        status = ComplianceStatus.ATENCAO
                        motivo = (
                            f"Distribuição de Lucros com excedente a R$ 50k no mês (Acumulado: R$ {novo_acumulado:,.2f}). "
                            f"Alerta de retenção de 10% de IRRF na fonte (R$ {irrf:,.2f}) sobre o valor excedente."
                        )
                    else:
                        irrf = Decimal("0.00")
                        status = ComplianceStatus.REGULAR
                        motivo = (
                            f"Distribuição de Lucros regular isenta de IRRF (Acumulado mês: R$ {novo_acumulado:,.2f} <= R$ 50.000)."
                        )

        else:
            # Pessoa Jurídica (Fornecedores / Serviços / Custos)
            is_servicos = any(k in desc for k in ["CONSULTORIA", "HONORARIOS", "SERVICO", "MANUTENCAO"])
            categoria = FinancialCategory.SERVICOS_TERCEIROS if is_servicos else FinancialCategory.FORNECEDORES
            natureza = FiscalNature.OPERACIONAL
            status = ComplianceStatus.REGULAR
            dedutivel = True
            c_debito = "3.1.2.01 - Custos Operacionais e Serviços de Terceiros"
            c_credito = "1.1.1.02 - Bancos Conta Movimento"
            centro = "OPERACIONAL"
            irrf = Decimal("0.00")
            inss = Decimal("0.00")
            motivo = f"Classificação RAG via Plano de Contas: {contexto_normas}."

        # Avaliação de teto e-Financeira
        limite_efinanceira = (
            (is_cpf and valor >= Decimal("5000.00")) or
            (not is_cpf and valor >= Decimal("15000.00"))
        )

        return TransactionClassificationOutput(
            transaction_id=str(tx_dict.get("id", "TX-RAG")),
            data=tx_date,
            valor=valor,
            tipo=tipo,
            contraparte=Counterparty(
                identificador=digits if digits in (11, 14) else ("12345678901" if is_cpf else "12345678000195"),
                nome=nome_contraparte
            ),
            classificacao=ClassificationDetail(
                categoria_financeira=categoria,
                centro_custo=centro,
                conta_debito=c_debito,
                conta_credito=c_credito,
                dedutivel=dedutivel,
                confidence_score=0.98,
                motor_usado=EngineType.RAG_LLM
            ),
            fiscal_compliance=FiscalComplianceDetail(
                natureza_pj_pf=natureza,
                limite_e_financeira_atingido=limite_efinanceira,
                irrf_retido=irrf,
                inss_devido=inss,
                status_conformidade=status,
                motivo_auditoria=motivo
            )
        )

    def _calcular_irrf_progressivo(self, base_calculo: Decimal) -> Decimal:
        """Cálculo simplificado do IRRF pela tabela progressiva mensal."""
        if base_calculo <= Decimal("2259.20"):
            return Decimal("0.00")
        elif base_calculo <= Decimal("2826.65"):
            return ((base_calculo * Decimal("0.075")) - Decimal("169.44")).quantize(Decimal("0.01"))
        elif base_calculo <= Decimal("3751.05"):
            return ((base_calculo * Decimal("0.15")) - Decimal("381.44")).quantize(Decimal("0.01"))
        elif base_calculo <= Decimal("4664.68"):
            return ((base_calculo * Decimal("0.225")) - Decimal("662.77")).quantize(Decimal("0.01"))
        else:
            return ((base_calculo * Decimal("0.275")) - Decimal("896.00")).quantize(Decimal("0.01"))
