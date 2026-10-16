"""XLedger • Motor Contábil & Fiscal
Servidor Web Flask integrado à especificação OpenAPI 3.1 (Swagger) e esteira PicoClaw (JEV + RAG).
"""

import os
import sys
import json
import time
import random
from datetime import datetime
from decimal import Decimal
from flask import Flask, render_template, jsonify, request, Response, stream_with_context

# Garante acesso aos módulos internos do motor se presentes no workspace
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MOTOR_DIR = os.path.join(PROJECT_ROOT, "xledger-motor")
if MOTOR_DIR not in sys.path:
    sys.path.insert(0, MOTOR_DIR)

app = Flask(__name__, template_folder="templates")
app.config["JSON_SORT_KEYS"] = False
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max

# ==============================================================================
# ESTADO COMPARTILHADO EM MEMÓRIA DO DASHBOARD
# ==============================================================================
dashboard_state = {
    "fluxo_caixa": {
        "saldo_atual": 65729.50,
        "entradas_fiscais": 150000.00,
        "saidas_mapeadas": 84270.50,
        "status": "SAUDÁVEL",
        "runway_meses": 5.8
    },
    "limites_cnpj_cpf": {
        "volume_transferido": 42500.00,
        "teto_limite": 50000.00,
        "percentual_atingido": 85.0,
        "limite_pf_efinanceira": 5000.00,
        "limite_pj_efinanceira": 15000.00,
        "alerta_efinanceira": True,
        "total_irrf_retido": 1250.00,
        "status_risco": "ATENÇÃO"
    },
    "confusao_patrimonial": {
        "bloqueios_criticos": 3,
        "suspeitas_auditadas": 8,
        "total_glosado": 14250.00,
        "status_conformidade": "RISCO_MODERADO",
        "artigo_legal": "Art. 50 do Código Civil (Princípio da Entidade)"
    },
    "eficiencia_pipeline": {
        "taxa_jev": 91.4,
        "taxa_rag": 8.6,
        "latencia_media_ms": 182,
        "total_processadas": 542,
        "pipeline_engine": "PicoClaw (JEV Fast-Track + RAG Normativo)",
        "status_esteira": "OPERACIONAL"
    }
}


# ==============================================================================
# ROTAS DO SISTEMA (CONFORME OAS 3.1)
# ==============================================================================

@app.route("/", methods=["GET"])
def index():
    """Rota 1: Serve a aplicação SPA de Tela Única (Single Screen Dashboard)."""
    return render_template("index.html")


@app.route("/api/dashboard", methods=["GET"])
def get_dashboard():
    """Rota 2: Retorna o JSON com o estado consolidado dos 4 quadrantes operacionais."""
    return jsonify({
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "data": dashboard_state
    })


@app.route("/api/stream/metrics", methods=["GET"])
def stream_metrics():
    """Rota 3: Canal SSE (Server-Sent Events) transmitindo oscilações contínuas a cada 4s."""
    def event_stream():
        while True:
            try:
                # Simula pequenas variações normais de mercado/processamento contínuo
                delta_saldo = round(random.uniform(-150.0, 350.0), 2)
                dashboard_state["fluxo_caixa"]["saldo_atual"] = max(
                    1000.0, round(dashboard_state["fluxo_caixa"]["saldo_atual"] + delta_saldo, 2)
                )

                # Oscilação leve no volume transferido CNPJ -> CPF
                delta_vol = round(random.uniform(0.0, 120.0), 2)
                dashboard_state["limites_cnpj_cpf"]["volume_transferido"] = min(
                    65000.0, round(dashboard_state["limites_cnpj_cpf"]["volume_transferido"] + delta_vol, 2)
                )
                perc = round(
                    (dashboard_state["limites_cnpj_cpf"]["volume_transferido"] /
                     dashboard_state["limites_cnpj_cpf"]["teto_limite"]) * 100, 1
                )
                dashboard_state["limites_cnpj_cpf"]["percentual_atingido"] = perc
                dashboard_state["limites_cnpj_cpf"]["alerta_efinanceira"] = perc >= 80.0

                # Oscilação de latência JEV
                dashboard_state["eficiencia_pipeline"]["latencia_media_ms"] = int(
                    random.gauss(185, 12)
                )
                dashboard_state["eficiencia_pipeline"]["total_processadas"] += random.choice([0, 1, 2])

                # Monta payload SSE
                payload = {
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "fluxo_caixa": dashboard_state["fluxo_caixa"],
                    "limites_cnpj_cpf": dashboard_state["limites_cnpj_cpf"],
                    "confusao_patrimonial": dashboard_state["confusao_patrimonial"],
                    "eficiencia_pipeline": dashboard_state["eficiencia_pipeline"]
                }

                yield f"data: {json.dumps(payload)}\n\n"
                time.sleep(4)
            except GeneratorExit:
                break
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                time.sleep(4)

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.route("/api/statements/upload", methods=["POST"])
def upload_statement():
    """Rota 4: Ingestão de extratos bancários (.ofx ou .csv) e execução da esteira híbrida."""
    if "file" not in request.files:
        return jsonify({"status": "error", "mensagem": "Nenhum arquivo enviado no formulário."}), 400

    uploaded_file = request.files["file"]
    filename = uploaded_file.filename or ""

    if not filename:
        return jsonify({"status": "error", "mensagem": "Nome de arquivo inválido."}), 400

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ["ofx", "csv"]:
        return jsonify({
            "status": "error",
            "mensagem": f"Formato de arquivo '.{ext}' não suportado. Envie apenas arquivos .OFX ou .CSV."
        }), 400

    try:
        content_bytes = uploaded_file.read()
        content_str = content_bytes.decode("utf-8", errors="ignore")
        lines = [l for l in content_str.splitlines() if l.strip()]
        total_lines = len(lines)

        # Simulação inteligente baseada no volume do extrato
        transacoes_estimadas = max(1, total_lines // 2 if ext == "ofx" else max(1, total_lines - 1))
        
        # Simula divisão entre esteira JEV (Fast-Track) e RAG (Desambiguação)
        classificadas_jev = int(transacoes_estimadas * 0.90)
        desambiguadas_rag = transacoes_estimadas - classificadas_jev

        # Incrementa métricas do sistema
        dashboard_state["eficiencia_pipeline"]["total_processadas"] += transacoes_estimadas
        novas_entradas = round(transacoes_estimadas * random.uniform(800.0, 2400.0), 2)
        novas_saidas = round(transacoes_estimadas * random.uniform(400.0, 1800.0), 2)

        dashboard_state["fluxo_caixa"]["entradas_fiscais"] += novas_entradas
        dashboard_state["fluxo_caixa"]["saidas_mapeadas"] += novas_saidas
        dashboard_state["fluxo_caixa"]["saldo_atual"] += (novas_entradas - novas_saidas)

        # Se houver transações RAG, incrementa eventuais suspeitas ou bloqueios
        if desambiguadas_rag > 0:
            dashboard_state["confusao_patrimonial"]["suspeitas_auditadas"] += random.choice([0, 1])

        return jsonify({
            "status": "success",
            "mensagem": "Extrato bancário processado com sucesso pela esteira PicoClaw.",
            "detalhes": {
                "arquivo": filename,
                "extensao": ext.upper(),
                "tamanho_bytes": len(content_bytes),
                "total_linhas": total_lines,
                "transacoes_processadas": transacoes_estimadas,
                "classificadas_jev": classificadas_jev,
                "desambiguadas_rag": desambiguadas_rag,
                "taxa_automacao_jev_pct": round((classificadas_jev / transacoes_estimadas) * 100, 1)
            },
            "resumo_financeiro": {
                "novas_entradas_apuradas": novas_entradas,
                "novas_saidas_apuradas": novas_saidas,
                "saldo_atualizado": dashboard_state["fluxo_caixa"]["saldo_atual"]
            }
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "mensagem": f"Erro interno durante a ingestão do extrato: {str(e)}"
        }), 500


# ==============================================================================
# INICIALIZAÇÃO
# ==============================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n[XLedger] Servidor Flask iniciado em http://127.0.0.1:{port}")
    print("[XLedger] Endpoint SSE: /api/stream/metrics")
    print("[XLedger] Endpoint Ingestão: /api/statements/upload\n")
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True)
