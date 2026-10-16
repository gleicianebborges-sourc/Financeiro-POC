"""Esteira Híbrida de Classificação e Decisão Contábil/Fiscal (JEV System 1 + RAG System 2).

Implementa a orquestração de dois tempos: Fast-Track ultrarrápido (< 250ms) via JEV/OpenRouter
e desvio automático para RAG em casos de ambiguidade (score < 0.90), falha de rede ou repasses a CPFs.
"""

import asyncio
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from config.openrouter import openrouter_settings
from models.schemas.transaction import (
    TransactionClassificationOutput,
    EngineType,
)
from models.transaction import BankStatementTransaction, ProcessedTransaction
from services.jev_client import JevOpenRouterClient, JevClientError
from services.rag_service import RAGService
from services.compliance_service import FiscalComplianceService, compliance_service

logger = logging.getLogger("xledger.classification_service")


class HybridClassificationPipelineService:
    """Serviço central da Esteira Híbrida de Classificação e Compliance Contábil."""

    def __init__(
        self,
        jev_client: Optional[JevOpenRouterClient] = None,
        rag_service: Optional[RAGService] = None,
        fiscal_compliance: Optional[FiscalComplianceService] = None,
        confidence_threshold: Optional[float] = None,
        concurrency_limit: int = 20
    ) -> None:
        self.jev_client = jev_client or JevOpenRouterClient()
        self.rag_service = rag_service or RAGService()
        self.fiscal_compliance = fiscal_compliance or compliance_service
        self.threshold = confidence_threshold or openrouter_settings.confidence_threshold
        self.semaphore = asyncio.Semaphore(concurrency_limit)

    async def process_single_transaction(
        self,
        tx: BankStatementTransaction
    ) -> Tuple[TransactionClassificationOutput, ProcessedTransaction]:
        """Processa uma única transação bancária através da esteira híbrida de dois tempos."""
        async with self.semaphore:
            tx_dict = tx.to_dict()
            contraparte_id = str(tx.identificador_contraparte or "")
            clean_digits = "".join(c for c in contraparte_id if c.isdigit())
            is_cpf = len(clean_digits) == 11

            output: Optional[TransactionClassificationOutput] = None
            motor_usado = EngineType.JEV

            # REGRA 1: Repasses diretos a CPF de sócios/colaboradores são compulsoriamente desviados para RAG
            if is_cpf:
                logger.info(
                    "Transação ID=%s com favorecido CPF (%s): Desvio compulsório para RAG Fiscal.",
                    tx.id, clean_digits
                )
                acumulado_mes = self.fiscal_compliance.get_acumulado_cpf(clean_digits)
                output = await self.rag_service.disambiguate_and_classify(tx_dict, acumulado_mes_cpf=acumulado_mes)
                motor_usado = EngineType.RAG_LLM
            else:
                # REGRA 2: Triagem Primária (JEV System 1) Fast-Track (< 250ms)
                try:
                    jev_output = await self.jev_client.classify_transaction(tx_dict)
                    
                    # Se atingir o threshold de confiança >= 0.90 e não for CPF -> Consolidação Imediata
                    if jev_output.classificacao.confidence_score >= self.threshold:
                        output = jev_output
                        motor_usado = EngineType.JEV
                    else:
                        logger.info(
                            "Score JEV insuficiente (%.2f < %.2f) para ID=%s. Escalando para RAG.",
                            jev_output.classificacao.confidence_score, self.threshold, tx.id
                        )
                        output = await self.rag_service.disambiguate_and_classify(tx_dict)
                        motor_usado = EngineType.RAG_LLM

                except JevClientError as err:
                    # Falha de rede, timeout ou resposta fora do contrato no OpenRouter: Fallback para o RAG local
                    logger.warning("Falha no JEV (%s). Acionando contingência via RAG local para ID=%s", err, tx.id)
                    output = await self.rag_service.disambiguate_and_classify(tx_dict)
                    motor_usado = EngineType.RAG_LLM
                except Exception as err:  # noqa: BLE001 - contingência defensiva do System 1
                    # Qualquer falha não prevista no JEV não pode interromper a esteira: desvia para RAG
                    logger.exception("Falha inesperada no JEV para ID=%s (%s). Acionando RAG.", tx.id, err)
                    output = await self.rag_service.disambiguate_and_classify(tx_dict)
                    motor_usado = EngineType.RAG_LLM

            # REGRA 3: Aplicação do Motor de Regras Fiscais e Compliance Tributário
            compliance_audit = self.fiscal_compliance.audit_transaction(output)

            # Atualiza o output com os pareceres finais do serviço de compliance
            output.fiscal_compliance.limite_e_financeira_atingido = compliance_audit.alerta_e_financeira
            output.fiscal_compliance.irrf_retido = compliance_audit.valor_retido_irrf
            output.fiscal_compliance.inss_devido = compliance_audit.inss_a_recolher
            output.fiscal_compliance.motivo_auditoria = compliance_audit.justificativa_legal

            # Converte para a entidade de domínio ProcessedTransaction para persistência e dashboard
            processed = ProcessedTransaction(
                entity_id=output.transaction_id,
                data=output.data,
                valor=output.valor,
                tipo=output.tipo.value,
                descricao_bruta=tx.descricao_bruta,
                documento=tx.documento,
                canal=tx.canal,
                identificador_contraparte=output.contraparte.identificador,
                nome_contraparte=output.contraparte.nome,
                categoria_financeira=output.classificacao.categoria_financeira.value,
                centro_custo=output.classificacao.centro_custo,
                conta_debito=output.classificacao.conta_debito,
                conta_credito=output.classificacao.conta_credito,
                dedutivel=output.classificacao.dedutivel,
                confidence_score=output.classificacao.confidence_score,
                motor_utilizado=motor_usado.value,
                natureza_fiscal=output.fiscal_compliance.natureza_pj_pf.value,
                status_compliance=output.fiscal_compliance.status_conformidade.value,
                irrf_calculado=output.fiscal_compliance.irrf_retido,
                alerta_auditoria=compliance_audit.justificativa_legal
            )

            return output, processed

    async def process_batch(
        self,
        transactions: List[BankStatementTransaction]
    ) -> Tuple[List[TransactionClassificationOutput], List[ProcessedTransaction]]:
        """Processamento paralelo e concorrente de lote de transações bancárias.

        Tolerância a falhas: uma transação com erro é registrada em log e descartada,
        sem interromper o processamento das demais.
        """
        tasks = [self.process_single_transaction(tx) for tx in transactions]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        outputs: List[TransactionClassificationOutput] = []
        processed_list: List[ProcessedTransaction] = []
        for tx, result in zip(transactions, results):
            if isinstance(result, BaseException):
                logger.error("Transação ID=%s falhou na esteira e foi descartada: %r", tx.id, result)
                continue
            outputs.append(result[0])
            processed_list.append(result[1])
        return outputs, processed_list
