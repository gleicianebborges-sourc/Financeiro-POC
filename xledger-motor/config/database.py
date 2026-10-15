"""Conexões de banco de dados relacional e base de dados vetorial normativa."""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class VectorDocument:
    """Documento indexado no Vector DB para auditoria contábil e fiscal."""
    doc_id: str
    titulo: str
    categoria: str  # RFB, CODIGO_CIVIL, PLANO_CONTAS, LIVRO_RAZAO, DRE
    conteudo: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class NormativeVectorStore:
    """Base vetorial normativa para desambiguação e compliance contábil (RAG).
    
    Indexa normas da RFB (e-Financeira, IRPF), Código Civil (Art. 50),
    Plano de Contas Referencial e demonstrativos contábeis históricos (DRE/Razão).
    """

    def __init__(self) -> None:
        self._corpus: List[VectorDocument] = []
        self._seed_normative_knowledge()

    def _seed_normative_knowledge(self) -> None:
        """Inicializa base de conhecimento com as diretrizes fiscais e contábeis."""
        docs = [
            VectorDocument(
                doc_id="RFB_IN_1571_2015",
                titulo="Instrução Normativa RFB nº 1571/2015 - e-Financeira",
                categoria="RFB",
                conteudo=(
                    "Art. 7º As instituições financeiras prestarão informações relativas às operações financeiras "
                    "quando o montante global movimentado no mês, por tipo de operação, for superior a "
                    "R$ 5.000,00 (cinco mil reais) para pessoas físicas e R$ 15.000,00 (quinze mil reais) para pessoas jurídicas. "
                    "Transferências acumuladas via PIX, TED e DOC que atinjam este teto devem ser reportadas à Receita Federal."
                ),
                metadata={"limite_pf": 5000.0, "limite_pj": 15000.0, "orgao": "RFB"}
            ),
            VectorDocument(
                doc_id="CC_ART_50",
                titulo="Código Civil Brasileiro - Artigo 50 (Confusão Patrimonial)",
                categoria="CODIGO_CIVIL",
                conteudo=(
                    "Art. 50. Em caso de abuso da personalidade jurídica, caracterizado pelo desvio de finalidade "
                    "ou pela confusão patrimonial, pode o juiz desconsiderá-la para que os efeitos de certas e determinadas "
                    "relações de obrigações sejam estendidos aos bens particulares de administradores ou de sócios. "
                    "Caracteriza-se confusão patrimonial o cumprimento repetitivo pela sociedade de obrigações do sócio "
                    "ou do administrador ou vice-versa, tais como despesas de educação, supermercado, saúde e moradia pessoal."
                ),
                metadata={"risco": "DESCONSIDERACAO_PERSONALIDADE_JURIDICA", "dedutibilidade": False}
            ),
            VectorDocument(
                doc_id="LEI_4357_ART_32",
                titulo="Lei nº 4.357/1964 - Artigo 32 (Impedimento à Distribuição de Lucros)",
                categoria="RFB",
                conteudo=(
                    "Art. 32. As pessoas jurídicas, enquanto estiverem em débito, não garantido, para com a União "
                    "e suas autarquias de Previdência e Assistência Social, por falta de recolhimento de imposto, taxa ou "
                    "contribuição, não podem distribuir bonificações a seus acionistas, nem dar ou atribuir participação de lucros "
                    "a seus sócios ou cotistas, bem como a seus diretores e demais membros de órgãos dirigentes, fiscais ou consultivos."
                ),
                metadata={"restricao": "DEBITO_PREVIDENCIARIO", "natureza": "DISTRIBUICAO_LUCROS"}
            ),
            VectorDocument(
                doc_id="REGRA_LUCROS_50K",
                titulo="Diretriz Fiscal de Distribuição de Lucros acima de R$ 50.000/mês",
                categoria="RFB",
                conteudo=(
                    "A distribuição de lucros é isenta de IRPF até o limite do lucro apurado na DRE trimestral/anual. "
                    "Em caso de pagamentos acumulados no mês superiores a R$ 50.000,00 para o mesmo CPF, incide o monitoramento "
                    "estrito com retenção de 10% de IRRF sobre a parcela excedente para fins de provisionamento e auditoria tributária preventiva."
                ),
                metadata={"aliquota_excedente": 0.10, "limite_isencao_mensal": 50000.0}
            ),
            VectorDocument(
                doc_id="PRO_LABORE_PREVIDENCIA",
                titulo="INSS e IRRF sobre Remuneração de Pró-Labore de Sócios Administradores",
                categoria="RFB",
                conteudo=(
                    "O pró-labore configura remuneração pelo trabalho dos sócios administradores. Sujeita-se à contribuição "
                    "previdenciária de 11% a cargo do segurado (retido na fonte) e 20% de cota patronal, além da incidência do "
                    "Imposto de Renda Retido na Fonte (IRRF) calculado pela Tabela Progressiva mensal."
                ),
                metadata={"inss_segurado": 0.11, "inss_patronal": 0.20}
            ),
            VectorDocument(
                doc_id="PLANO_CONTAS_PADRAO",
                titulo="Plano de Contas Referencial CFC / SPED Contábil",
                categoria="PLANO_CONTAS",
                conteudo=(
                    "Conta 1.1.1.02: Bancos Conta Movimento (Ativo Circulante)\n"
                    "Conta 2.3.1.05: Dividendos e Lucros Pagos (Patrimônio Líquido)\n"
                    "Conta 1.1.3.04: Adiantamentos a Sócios e Diretores (Ativo Circulante - Mútuo)\n"
                    "Conta 3.1.1.01: Despesas Operacionais Gerais (Resultado)\n"
                    "Conta 3.1.2.01: Custos Operacionais e Serviços de Terceiros\n"
                    "Conta 3.1.1.05: Pró-Labore e Honorários da Diretoria"
                ),
                metadata={"versao": "2026.1"}
            )
        ]
        self._corpus.extend(docs)

    async def search(self, query: str, limit: int = 3) -> List[VectorDocument]:
        """Busca semântica simplificada por relevância léxica/vetorial nos documentos."""
        tokens = query.lower().split()
        scored: List[tuple[int, VectorDocument]] = []
        for doc in self._corpus:
            score = 0
            doc_text = f"{doc.titulo} {doc.conteudo}".lower()
            for token in tokens:
                if len(token) > 2 and token in doc_text:
                    score += 1
            if score > 0:
                scored.append((score, doc))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [doc for _, doc in scored[:limit]]
        if not results:
            results = self._corpus[:limit]
        return results


class DatabaseConnection:
    """Gerenciador de conexões com banco de dados e vector store."""

    def __init__(self) -> None:
        self.vector_store = NormativeVectorStore()
        self._connected = True

    async def get_vector_store(self) -> NormativeVectorStore:
        return self.vector_store


db_manager = DatabaseConnection()
