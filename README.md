# XLedger • Motor Contábil & Fiscal

Arquitetura V1.0 • JEV + RAG | Classificação Bancária Autônoma em Tempo Real  
**Normativas**: RFB e-Financeira (IN 1571/2015) / IRPF / CFC / Código Civil (Art. 50)

---

## 1. Visão Geral da Arquitetura Híbrida

O ecossistema **XLedger** opera uma esteira de dois tempos para ingestão massiva de extratos bancários (OFX/CSV/Open Finance):

1. **Estágio 1 (Jev System 1 - Fast-Track)**:
   - Processa primitivas estruturadas com latência ultrabaixa (< 250ms) via OpenRouter (`typesafe/jev-latest`).
   - Se o score de calibração for **≥ 0.90** e a contraparte **não for CPF**, o lançamento é classificado e consolidado imediatamente em partidas dobradas.
2. **Estágio 2 (RAG System 2 - Desambiguação & Auditoria Fiscal)**:
   - Disparado automaticamente se o score for **< 0.90**, em falha de rede/timeout da API externa, ou se o favorecido for **CPF** (sócios, administradores ou colaboradores).
   - Consulta a base vetorial contendo normas da RFB (IN 1571/2015, Lei 4.357/64, Código Civil Art. 50), Plano de Contas e histórico contábil para fundamentar o lançamento e apurar retenções.

---

## 2. Estrutura do Repositório (Padrão MVC / Clean Architecture)

```
xledger-motor/
├── config/                  # Configurações globais e variáveis de ambiente
│   ├── database.py          # Conexão com banco e base vetorial normativa
│   └── openrouter.py        # Configurações do OpenRouter (typesafe/jev-latest)
├── controllers/             # Orquestração do fluxo de dados e endpoints
│   ├── dashboard_controller.py  # Orquestra os 4 quadrantes e streaming SSE
│   └── statement_controller.py  # Recebe OFX/CSV e coordena pipeline
├── models/                  # Definição de dados e validações (Pydantic v2)
│   ├── schemas/             # Contratos de entrada/saída (Data Transfer Objects)
│   │   ├── compliance.py    # FiscalComplianceOutput
│   │   └── transaction.py   # TransactionClassificationOutput
│   ├── statement.py         # Representação do Extrato Bancário
│   └── transaction.py       # Representação da Transação individual
├── services/                # Camada de Negócio (regras fiscais e IA)
│   ├── classification_service.py # Esteira híbrida (Jev >= 0.90 vs RAG)
│   ├── compliance_service.py     # Validador de regras CNPJ -> CPF, e-Financeira
│   ├── jev_client.py        # Integração HTTP/SDK assíncrona com OpenRouter
│   └── rag_service.py       # Consulta à base vetorial normativa (RFB / CC)
├── views/                   # Componentes visuais (Dashboard 4 quadrantes)
│   ├── components/          # Quadrantes e template HTML Viewport-Lock
│   └── dashboard_view.py    # Apresentador em tela única sem rolagem vertical
├── parsers/                 # Utilitários de extração e conversão de arquivos
│   ├── csv_parser.py        # Leitor universal de extratos CSV
│   └── ofx_parser.py        # Parser nativo de arquivos OFX bancários
├── samples/                 # Amostras para testes rápidos
│   ├── extrato_amostra.csv
│   └── extrato_amostra.ofx
├── tests/                   # Testes unitários e de integração
│   ├── test_classification.py   # Validação Fast-Track vs RAG
│   └── test_compliance.py       # Validação 15k, 5k, 10% retenção e confusão patrimonial
└── main.py                  # Ponto de entrada / Injeção PicoClaw / FastAPI
```

---

## 3. Diretrizes Fiscais Implementadas (CNPJ ➔ CPF)

| Operação Bancária | Gatilho / Limite Normativo | Incidências Tributárias | Conduta Autônoma XLedger |
|---|---|---|---|
| **Pró-Labore** | Transferência mensal a sócios administradores | INSS Segurado (11%) + IRRF Tabela Progressiva | Gera provisão de folha e retém guias. |
| **Distribuição de Lucros** | Exige lucro líquido na DRE e regularidade fiscal prévia | Isento de IRPF até R$ 50k/mês. Acima de R$ 50k: **Retenção de 10% de IRRF** sobre excedente | Alerta e provisiona retenção no DARF. Se DRE negativa, converte em mútuo. |
| **Alerta e-Financeira (RFB)** | Repasses mensais ≥ R$ 15k (PJ) ou ≥ R$ 5k (PF) | Obrigação acessória bancária direta à RFB | Totalizador em tempo real e sinalização de risco. |
| **Confusão Patrimonial** | Pagamento de despesas particulares do sócio (escola, mercado, saúde) via PJ | Indedutibilidade IRPJ/CSLL + Risco Art. 50 CC | Bloqueio imediato, classificação compulsória em Ativo (Adiantamento a Sócio) e Alerta Máximo. |

---

## 4. Como Executar

### 4.1 Instalação das dependências
```bash
pip install -r requirements.txt
```

### 4.2 Executar testes automatizados
```bash
python -m unittest discover -s xledger-motor/tests -p "test_*.py"
```

### 4.3 Executar Demonstração em CLI (Terminais e visualização ASCII dos 4 quadrantes)
```bash
python xledger-motor/main.py --demo
```

### 4.4 Iniciar Servidor FastAPI e Dashboard Single-Screen (SSE)
```bash
python xledger-motor/main.py --server --port 8000
```
Acesse no navegador: `http://localhost:8000`
- **Dashboard Viewport Lock**: 4 quadrantes operacionais sem rolagem vertical excessiva.
- **API REST**: `GET /api/dashboard`
- **Streaming SSE**: `GET /api/stream/metrics`
- **Upload de Extratos**: `POST /api/statements/upload` (envio de `.csv` ou `.ofx`)
