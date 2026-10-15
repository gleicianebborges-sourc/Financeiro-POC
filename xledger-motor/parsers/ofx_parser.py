"""Parser nativo de arquivos OFX (Open Financial Exchange 1.0 e 2.0)."""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from models.statement import BankStatement
from models.transaction import BankStatementTransaction


class OFXStatementParser:
    """Extrai lançamentos bancários estruturados a partir de arquivos OFX."""

    @staticmethod
    def parse(content: str) -> BankStatement:
        """Faz a extração das tags de cabeçalho e transações de um arquivo OFX."""
        banco = OFXStatementParser._get_tag_value(content, "BANKID") or "Banco Ingerido"
        conta = OFXStatementParser._get_tag_value(content, "ACCTID") or "00000-0"
        agencia = OFXStatementParser._get_tag_value(content, "BRANCHID") or "0001"
        moeda = OFXStatementParser._get_tag_value(content, "CURDEF") or "BRL"

        # Regex para isolar cada bloco <STMTTRN>...</STMTTRN>
        pattern = re.compile(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|(?=</BANKTRANLIST>))", re.DOTALL | re.IGNORECASE)
        trn_matches = pattern.findall(content)

        transactions: List[BankStatementTransaction] = []

        for idx, block in enumerate(trn_matches, start=1):
            trn_type = (OFXStatementParser._get_tag_value(block, "TRNTYPE") or "OTHER").upper()
            dt_posted_raw = OFXStatementParser._get_tag_value(block, "DTPOSTED") or ""
            tx_date = OFXStatementParser._parse_ofx_date(dt_posted_raw)
            
            amt_raw = OFXStatementParser._get_tag_value(block, "TRNAMT") or "0.00"
            try:
                amt = Decimal(amt_raw.strip())
            except Exception:
                amt = Decimal("0.00")

            tipo = "DEBITO" if (amt < 0 or trn_type in ("DEBIT", "PAYMENT", "CHECK")) else "CREDITO"
            valor = abs(amt)

            fitid = OFXStatementParser._get_tag_value(block, "FITID") or f"OFX-{idx:05d}"
            memo = OFXStatementParser._get_tag_value(block, "MEMO") or "Lançamento OFX"
            checknum = OFXStatementParser._get_tag_value(block, "CHECKNUM") or ""

            # Extração de CNPJ ou CPF do MEMO se presente
            contraparte_doc = OFXStatementParser._extract_cpf_cnpj(memo)
            canal = "PIX" if "PIX" in memo.upper() else ("TED" if "TED" in memo.upper() else "OUTROS")

            tx = BankStatementTransaction(
                entity_id=f"TX-OFX-{fitid}",
                data=tx_date,
                valor=valor,
                tipo=tipo,
                descricao_bruta=memo,
                documento=checknum or fitid,
                canal=canal,
                identificador_contraparte=contraparte_doc,
                nome_contraparte=f"Contraparte {memo.split()[0] if memo else 'Favorecido'}"
            )
            transactions.append(tx)

        statement = BankStatement(
            banco=banco,
            conta=conta,
            agencia=agencia,
            moeda=moeda,
            transacoes=transactions
        )
        if transactions:
            statement.periodo_inicio = min(t.data for t in transactions)
            statement.periodo_fim = max(t.data for t in transactions)
        return statement

    @staticmethod
    def _get_tag_value(block: str, tag: str) -> Optional[str]:
        # Formato SGML <TAG>VALOR ou XML <TAG>VALOR</TAG>
        match = re.search(rf"<{tag}>([^<\r\n]+)(?:</{tag}>)?", block, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    @staticmethod
    def _parse_ofx_date(raw: str) -> date:
        # Formato OFX padrão: YYYYMMDDHHMMSS ou YYYYMMDD
        cleaned = re.sub(r"[^\d]", "", raw)[:8]
        if len(cleaned) == 8:
            try:
                return datetime.strptime(cleaned, "%Y%m%d").date()
            except ValueError:
                pass
        return date.today()

    @staticmethod
    def _extract_cpf_cnpj(text: str) -> Optional[str]:
        cnpj_match = re.search(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b", text)
        if cnpj_match:
            return "".join(c for c in cnpj_match.group(0) if c.isdigit())
        cpf_match = re.search(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", text)
        if cpf_match:
            return "".join(c for c in cpf_match.group(0) if c.isdigit())
        return None
