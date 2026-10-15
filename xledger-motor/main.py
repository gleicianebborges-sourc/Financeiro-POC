"""Ponto de entrada da aplicação XLedger com Injeção de Dependências (PicoClaw Container).

Inicializa a aplicação FastAPI para REST e streaming SSE e expõe modo CLI para auditoria local.
"""

import argparse
import asyncio
import os
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, Dict, List, Optional

import argparse
import asyncio
import os
import sys
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, Dict, List, Optional
from datetime import date

# Garante que o diretório do projeto esteja no sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import uvicorn
from fastapi import FastAPI, File, UploadFile, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse

from config.openrouter import openrouter_settings
from config.database import db_manager
from services.jev_client import JevOpenRouterClient
from services.rag_service import RAGService
from services.compliance_service import FiscalComplianceService, compliance_service
from services.classification_service import HybridClassificationPipelineService
from controllers.statement_controller import BankStatementController
from controllers.dashboard_controller import DashboardController
from views.dashboard_view import SinglePageDashboardPresenter
from views.components.quadrants import QuadrantCardsRenderer
from models.transaction import BankStatementTransaction


# =================== [CONTAINER DE INJEÇÃO PICOCLAW] ===================

class PicoClawContainer:
    """Contêiner leve de injeção de dependências desacoplado (IoC / DI)."""

    def __init__(self) -> None:
        self.jev_client = JevOpenRouterClient()
        self.rag_service = RAGService()
        self.compliance_service = compliance_service
        self.pipeline_service = HybridClassificationPipelineService(
            jev_client=self.jev_client,
            rag_service=self.rag_service,
            fiscal_compliance=self.compliance_service,
        )
        self.statement_controller = BankStatementController(
            pipeline_service=self.pipeline_service,
            compliance=self.compliance_service,
        )
        self.dashboard_presenter = SinglePageDashboardPresenter()
        self.dashboard_controller = DashboardController(
            statement_controller=self.statement_controller,
            presenter=self.dashboard_presenter,
        )


container = PicoClawContainer()


# =================== [FASTAPI APPLICATION SETUP] ===================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup de inicialização
    yield
    # Limpeza / Shutdown


app = FastAPI(
    title="XLedger • Motor Contábil & Fiscal",
    description="Motor discriminativo JEV + RAG para esteira híbrida de extratos bancários e compliance e-Financeira",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def serve_single_screen_dashboard():
    """Entrega a tela única sem rolagem vertical (Viewport Lock) do Dashboard dos 4 quadrantes."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(current_dir, "views", "components", "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>XLedger Dashboard Ativo</h1>")


@app.get("/api/dashboard", response_model=Dict[str, Any])
async def get_dashboard_metrics():
    """Retorna os dados dos 4 quadrantes operacionais para consumo pelo frontend."""
    return container.dashboard_controller.get_dashboard_state()


@app.get("/api/stream/metrics")
async def stream_dashboard_metrics():
    """Canal Server-Sent Events (SSE) para atualização contínua do dashboard."""
    return StreamingResponse(
        container.dashboard_controller.stream_metrics(interval_seconds=2.0),
        media_type="text/event-stream"
    )


@app.post("/api/statements/upload")
async def upload_statement(file: UploadFile = File(...)):
    """Recebe arquivos de extrato bancário (OFX ou CSV) e roda a esteira híbrida."""
    content_bytes = await file.read()
    content_str = content_bytes.decode("utf-8", errors="ignore")
    
    filename = (file.filename or "").lower()
    if filename.endswith(".ofx"):
        outputs, processed = await container.statement_controller.ingest_ofx(content_str)
    else:
        outputs, processed = await container.statement_controller.ingest_csv(content_str)

    return {
        "status": "success",
        "total_processadas": len(processed),
        "quadrantes": container.dashboard_controller.get_dashboard_state()
    }


# =================== [AMOSTRA DEMONSTRATIVA E CLI] ===================

def generate_sample_transactions() -> List[BankStatementTransaction]:
    """Gera transações ilustrativas simulando fluxo bancário real de empresa."""
    hoje = date.today()
    return [
        # 1. Rotina operacional JEV (Score alto, dedutível, Rota Determinística)
        BankStatementTransaction(
            entity_id="TX-001",
            data=hoje,
            valor=Decimal("120.00"),
            tipo="DEBITO",
            descricao_bruta="TARIFA BANCARIA MENSAL CONTA PJ",
            documento="DEB001",
            canal="TARIFAS",
            identificador_contraparte="00000000000191",
            nome_contraparte="Banco do Brasil S.A."
        ),
        # 2. Rotina combustível / posto JEV
        BankStatementTransaction(
            entity_id="TX-002",
            data=hoje,
            valor=Decimal("350.50"),
            tipo="DEBITO",
            descricao_bruta="POSTO SHELL COMBUSTIVEL FROTA PJ",
            documento="DEB002",
            canal="CARTAO_DEBITO",
            identificador_contraparte="12345678000195",
            nome_contraparte="Posto Shell Central"
        ),
        # 3. Pró-Labore Sócio CPF (Desvio compulsório para RAG, INSS 11% + IRRF)
        BankStatementTransaction(
            entity_id="TX-003",
            data=hoje,
            valor=Decimal("15000.00"),
            tipo="DEBITO",
            descricao_bruta="PRO-LABORE SOCIO ADMINISTRADOR CARLOS DRUMMOND",
            documento="TED003",
            canal="TED",
            identificador_contraparte="12345678901",
            nome_contraparte="Carlos Drummond"
        ),
        # 4. Distribuição de Lucros Sócio CPF com excedente a 50k (Retenção 10% IRRF + e-Financeira)
        BankStatementTransaction(
            entity_id="TX-004",
            data=hoje,
            valor=Decimal("65000.00"),
            tipo="DEBITO",
            descricao_bruta="DISTRIBUICAO DE LUCROS EXERCICIO 2026",
            documento="PIX004",
            canal="PIX",
            identificador_contraparte="98765432100",
            nome_contraparte="Mariana Rios"
        ),
        # 5. Confusão Patrimonial detectada (Despesa pessoal via PJ -> Bloqueio, Adiantamento, Indedutível)
        BankStatementTransaction(
            entity_id="TX-005",
            data=hoje,
            valor=Decimal("3800.00"),
            tipo="DEBITO",
            descricao_bruta="PAGTO MENSALIDADE COLEGIO SANTO AGOSTINHO FILHO SOCIO",
            documento="BOL005",
            canal="BOLETO",
            identificador_contraparte="12345678901",
            nome_contraparte="Colégio Santo Agostinho"
        ),
        # 6. Receita Operacional (Entrada)
        BankStatementTransaction(
            entity_id="TX-006",
            data=hoje,
            valor=Decimal("150000.00"),
            tipo="CREDITO",
            descricao_bruta="RECEBIMENTO NF-E 4092 PRESTACAO SERVICOS TI",
            documento="TED006",
            canal="TED",
            identificador_contraparte="99888777000166",
            nome_contraparte="Tech Global Solutions Ltda"
        )
    ]


async def run_cli_demo() -> None:
    """Executa demonstração em tempo de execução via terminal com visualização em 4 quadrantes."""
    print("\n[XLedger] Inicializando Motor Contábil e Fiscal...")
    samples = generate_sample_transactions()
    
    print(f"[XLedger] Ingerindo {len(samples)} lançamentos bancários...")
    outputs, processed = await container.statement_controller.ingest_transactions_batch(samples)
    
    print(f"\n[XLedger] Processamento concluído! ({len(processed)} transações classificadas e auditadas)")
    dashboard_payload = container.dashboard_controller.get_dashboard_state()
    
    rendered_view = QuadrantCardsRenderer.render_cli(dashboard_payload)
    print(rendered_view)


def main() -> None:
    """Ponto de entrada principal."""
    parser = argparse.ArgumentParser(description="XLedger Motor Contábil & Fiscal")
    parser.add_argument("--demo", action="store_true", help="Executa demonstração local em CLI")
    parser.add_argument("--server", action="store_true", help="Inicia o servidor FastAPI/SSE")
    parser.add_argument("--port", type=int, default=8000, help="Porta HTTP do servidor")
    args = parser.parse_args()

    if args.server:
        uvicorn.run("main:app", host="0.0.0.0", port=args.port, reload=True)
    else:
        asyncio.run(run_cli_demo())


if __name__ == "__main__":
    main()
