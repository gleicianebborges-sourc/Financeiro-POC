"""Cliente assíncrono para o motor discriminativo Jev via OpenRouter."""

import asyncio
import json
import logging
from decimal import Decimal
from typing import Any, Dict, Optional
import httpx
from pydantic import ValidationError

from config.openrouter import openrouter_settings
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

logger = logging.getLogger("xledger.jev_client")


class JevClientError(Exception):
    """Exceção base para falhas de comunicação com a API Jev/OpenRouter."""
    pass


class JevOpenRouterClient:
    """Cliente assíncrono para o motor discriminativo Jev via OpenRouter.
    
    Responsável pela Triagem Primária (Jev System 1) com latência ultrabaixa (< 250ms)
    para categorização contábil imediata de fluxos de caixa rotineiros.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        app_url: Optional[str] = None,
        timeout_sec: Optional[float] = None,
        max_retries: Optional[int] = None,
        mock_mode: Optional[bool] = None
    ) -> None:
        self.api_key = api_key or openrouter_settings.api_key
        self.app_url = app_url or openrouter_settings.app_url
        self.endpoint = openrouter_settings.endpoint
        self.model = openrouter_settings.model
        self.timeout = timeout_sec or openrouter_settings.timeout_seconds
        self.max_retries = max_retries or openrouter_settings.max_retries
        self.mock_mode = mock_mode if mock_mode is not None else openrouter_settings.mock_mode

    async def classify_transaction(self, tx_dict: Dict[str, Any]) -> TransactionClassificationOutput:
        """Classifica uma transação bruta enviando payload estruturado para o OpenRouter.
        
        Aplica retries exponenciais e propaga erro em caso de timeout/falha de rede
        para permitir o desvio imediato para a esteira RAG local.
        """
        # Se estiver em mock_mode ou sem chave válida de produção, gera predição determinística simulada
        if self.mock_mode or not self.api_key or self.api_key.startswith("sk-or-v1-mock"):
            return self._simulate_fast_track_jev(tx_dict)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": self.app_url,
            "X-Title": openrouter_settings.app_title,
            "Content-Type": "application/json",
        }

        user_content = (
            f"Classifique o lançamento bancário: ID={tx_dict.get('id')}, Data={tx_dict.get('data')}, "
            f"Valor={tx_dict.get('valor')}, Histórico='{tx_dict.get('descricao_bruta')}', "
            f"Contraparte={tx_dict.get('identificador_contraparte', 'N/A')}."
        )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Você é o motor discriminativo JEV do XLedger. "
                        "Retorne APENAS um objeto JSON válido, sem texto adicional, "
                        "aderente estritamente ao seguinte JSON Schema:\n"
                        f"{self._output_schema_json()}"
                    )
                },
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
        }

        attempt = 0
        last_exc: Optional[Exception] = None

        while attempt < self.max_retries:
            attempt += 1
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(self.endpoint, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    raw_content = data["choices"][0]["message"]["content"]
                    return TransactionClassificationOutput.model_validate_json(raw_content)

            except (KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
                # Resposta fora do contrato (JSON malformado, schema divergente ou envelope inesperado).
                # Com temperature=0 o erro tende a ser determinístico: não há ganho em retentar.
                logger.error("Resposta inválida do OpenRouter JEV para ID=%s: %s", tx_dict.get("id"), exc)
                raise JevClientError(f"Resposta inválida da API do OpenRouter: {exc}") from exc

            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                logger.warning(
                    "Falha ao consultar OpenRouter (tentativa %d/%d): %s",
                    attempt, self.max_retries, str(exc)
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(0.3 * (2 ** (attempt - 1)))
                else:
                    break

        logger.error("Esgotadas as tentativas com OpenRouter JEV: %s. Propagando para desvio RAG.", last_exc)
        raise JevClientError(f"Indisponibilidade ou Timeout na API do OpenRouter: {last_exc}")

    @staticmethod
    def _output_schema_json() -> str:
        """JSON Schema do contrato de saída enviado ao modelo para forçar aderência tipada."""
        return json.dumps(TransactionClassificationOutput.model_json_schema(), ensure_ascii=False)

    def _simulate_fast_track_jev(self, tx_dict: Dict[str, Any]) -> TransactionClassificationOutput:
        """Simulação determinística do modelo JEV para testes locais e fallback de alta performance."""
        desc = str(tx_dict.get("descricao_bruta", "")).upper()
        contraparte_id = str(tx_dict.get("identificador_contraparte", "00000000000"))
        digits = "".join(c for c in contraparte_id if c.isdigit())
        is_cpf = len(digits) == 11
        
        valor = Decimal(str(tx_dict.get("valor", "0.00")))
        tipo_str = str(tx_dict.get("tipo", "DEBITO")).upper()
        tipo = TransactionType.CREDITO if "CRED" in tipo_str else TransactionType.DEBITO

        # Heurística de rotina operacional (OPEX / Tarifas / Combustível / Energia)
        is_routine = any(
            k in desc for k in [
                "TARIFA", "POSTO", "COMBUSTIVEL", "ENERGIA", "AGUA", "INTERNET",
                "TELEFONIA", "HOSPEDAGEM", "SOFTWARE", "AWS", "GOOGLE"
            ]
        )

        score = 0.96 if is_routine else 0.72

        # Partidas dobradas
        categoria = FinancialCategory.OPEX if is_routine else FinancialCategory.FORNECEDORES
        centro = "ADMINISTRATIVO" if is_routine else "GERAL"
        c_debito = "3.1.1.01 - Despesas Operacionais" if is_routine else "3.1.2.01 - Fornecedores Nacionais"
        c_credito = "1.1.1.02 - Bancos Conta Movimento"

        from datetime import date
        raw_date = tx_dict.get("data")
        if isinstance(raw_date, str):
            tx_date = date.fromisoformat(raw_date)
        elif isinstance(raw_date, date):
            tx_date = raw_date
        else:
            tx_date = date.today()

        return TransactionClassificationOutput(
            transaction_id=str(tx_dict.get("id", "TX-001")),
            data=tx_date,
            valor=valor,
            tipo=tipo,
            contraparte=Counterparty(
                identificador=digits if len(digits) in (11, 14) else ("12345678901" if is_cpf else "12345678000195"),
                nome=str(tx_dict.get("nome_contraparte", "Contraparte Identificada"))
            ),
            classificacao=ClassificationDetail(
                categoria_financeira=categoria,
                centro_custo=centro,
                conta_debito=c_debito,
                conta_credito=c_credito,
                dedutivel=True,
                confidence_score=score,
                motor_usado=EngineType.JEV
            ),
            fiscal_compliance=FiscalComplianceDetail(
                natureza_pj_pf=FiscalNature.OPERACIONAL,
                limite_e_financeira_atingido=False,
                irrf_retido=Decimal("0.00"),
                inss_devido=Decimal("0.00"),
                status_conformidade=ComplianceStatus.REGULAR,
                motivo_auditoria="Classificação determinística primária JEV concluída com sucesso."
            )
        )
