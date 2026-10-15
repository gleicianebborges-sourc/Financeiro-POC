"""Parser de extratos bancários em formato CSV (suporte a layouts nacionais e internacionais)."""

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from models.statement import BankStatement
from models.transaction import BankStatementTransaction


class CSVStatementParser:
    """Extrai transações estruturadas a partir de arquivos CSV de extratos bancários."""

    @staticmethod
    def parse(
        content: str,
        banco: str = "Banco Padrão",
        conta: str = "00000-0",
        agencia: str = "0001"
    ) -> BankStatement:
        """Processa o conteúdo textual de um CSV bancário e retorna o BankStatement."""
        lines = [line.strip() for line in content.strip().splitlines() if line.strip()]
        if not lines:
            return BankStatement(banco=banco, conta=conta, agencia=agencia)

        # Detecta delimitador
        header = lines[0]
        delimiter = ";" if ";" in header else ("," if "," in header else "\t")
        
        reader = csv.DictReader(lines, delimiter=delimiter)
        transactions: List[BankStatementTransaction] = []

        for index, row in enumerate(reader, start=1):
            normalized_row = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items() if k}

            # Localiza colunas de data
            data_val = (
                normalized_row.get("data")
                or normalized_row.get("dtposted")
                or normalized_row.get("date")
                or normalized_row.get("data_lancamento")
                or ""
            )
            tx_date = CSVStatementParser._parse_date(data_val)

            # Localiza valor
            valor_raw = (
                normalized_row.get("valor")
                or normalized_row.get("amount")
                or normalized_row.get("valor_lancamento")
                or "0.00"
            )
            valor_dec, is_negative = CSVStatementParser._parse_amount(valor_raw)

            # Localiza tipo (débito / crédito)
            tipo_raw = normalized_row.get("tipo", "").upper()
            if not tipo_raw:
                tipo = "DEBITO" if is_negative or valor_dec < 0 else "CREDITO"
            else:
                tipo = "DEBITO" if any(x in tipo_raw for x in ["D", "DEB", "SAIDA"]) else "CREDITO"

            valor_positivo = abs(valor_dec)

            # Localiza descrição / histórico
            descricao = (
                normalized_row.get("descricao")
                or normalized_row.get("historico")
                or normalized_row.get("memo")
                or normalized_row.get("description")
                or "Lançamento bancário"
            )

            # Documento / FITID
            doc = (
                normalized_row.get("documento")
                or normalized_row.get("doc")
                or normalized_row.get("fitid")
                or normalized_row.get("id")
                or f"DOC-{index:05d}"
            )

            # Contraparte
            contraparte_doc = (
                normalized_row.get("cpf_cnpj")
                or normalized_row.get("documento_favorecido")
                or normalized_row.get("contraparte")
                or None
            )
            contraparte_nome = (
                normalized_row.get("nome_favorecido")
                or normalized_row.get("favorecido")
                or normalized_row.get("contraparte_nome")
                or None
            )

            # Se o documento da contraparte não estiver explícito, tenta extrair dígitos da descrição
            if not contraparte_doc:
                contraparte_doc = CSVStatementParser._extract_cpf_cnpj(descricao)

            canal = normalized_row.get("canal", "PIX/TED")

            tx = BankStatementTransaction(
                entity_id=f"TX-CSV-{index:04d}",
                data=tx_date,
                valor=valor_positivo,
                tipo=tipo,
                descricao_bruta=descricao,
                documento=doc,
                canal=canal,
                identificador_contraparte=contraparte_doc,
                nome_contraparte=contraparte_nome or "Contraparte Identificada"
            )
            transactions.append(tx)

        statement = BankStatement(
            banco=banco,
            conta=conta,
            agencia=agencia,
            transacoes=transactions
        )
        if transactions:
            statement.periodo_inicio = min(t.data for t in transactions)
            statement.periodo_fim = max(t.data for t in transactions)
        return statement

    @staticmethod
    def _parse_date(date_str: str) -> date:
        date_str = date_str.strip()
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        return date.today()

    @staticmethod
    def _parse_amount(val_str: str) -> tuple[Decimal, bool]:
        val_clean = val_str.replace("R$", "").replace(" ", "").strip()
        is_negative = val_clean.startswith("-") or val_clean.endswith("-") or "(" in val_clean
        val_clean = val_clean.replace("-", "").replace("(", "").replace(")", "").strip()

        # Trata formato brasileiro (1.000,50) vs americano (1000.50)
        if "," in val_clean and "." in val_clean:
            if val_clean.rfind(",") > val_clean.rfind("."):
                val_clean = val_clean.replace(".", "").replace(",", ".")
            else:
                val_clean = val_clean.replace(",", "")
        elif "," in val_clean:
            val_clean = val_clean.replace(",", ".")

        try:
            val = Decimal(val_clean)
        except Exception:
            val = Decimal("0.00")

        return val, is_negative

    @staticmethod
    def _extract_cpf_cnpj(text: str) -> Optional[str]:
        # Busca sequências de 11 ou 14 dígitos (com ou sem pontuação)
        cnpj_match = re.search(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b", text)
        if cnpj_match:
            return "".join(c for c in cnpj_match.group(0) if c.isdigit())
        cpf_match = re.search(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", text)
        if cpf_match:
            return "".join(c for c in cpf_match.group(0) if c.isdigit())
        return None
