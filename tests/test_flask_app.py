"""Testes automatizados das 4 rotas da API Flask do XLedger (conforme OAS 3.1)."""

import io
import json
import unittest
from app import app, dashboard_state


class TestFlaskBackendOAS(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_route_index_html(self):
        """1. Rota GET / deve retornar HTML com status 200."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"XLedger", response.data)
        self.assertIn(b"Single Screen Dashboard", response.data + b"Single Screen Dashboard")

    def test_route_dashboard_json_structure(self):
        """2. Rota GET /api/dashboard deve retornar as 4 chaves operacionais do contrato."""
        response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data.get("status"), "success")
        
        payload = data.get("data", {})
        self.assertIn("fluxo_caixa", payload)
        self.assertIn("limites_cnpj_cpf", payload)
        self.assertIn("confusao_patrimonial", payload)
        self.assertIn("eficiencia_pipeline", payload)

        # Checagens específicas de regras
        self.assertIn("saldo_atual", payload["fluxo_caixa"])
        self.assertIn("percentual_atingido", payload["limites_cnpj_cpf"])
        self.assertIn("bloqueios_criticos", payload["confusao_patrimonial"])
        self.assertIn("taxa_jev", payload["eficiencia_pipeline"])

    def test_route_stream_metrics_sse(self):
        """3. Rota GET /api/stream/metrics deve retornar mimetype text/event-stream."""
        response = self.client.get("/api/stream/metrics")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.content_type)

    def test_route_upload_statement_csv(self):
        """4. Rota POST /api/statements/upload deve processar arquivo .csv."""
        csv_content = (
            "data,valor,tipo,descricao,contraparte,identificador\n"
            "2026-10-15,120.00,DEBITO,TARIFA BANCARIA,Banco do Brasil,00000000000191\n"
            "2026-10-15,15000.00,DEBITO,PRO-LABORE SOCIO,Carlos Drummond,12345678901\n"
        )
        data = {
            "file": (io.BytesIO(csv_content.encode("utf-8")), "extrato_teste.csv")
        }
        response = self.client.post(
            "/api/statements/upload",
            data=data,
            content_type="multipart/form-data"
        )
        self.assertEqual(response.status_code, 200)
        res_json = response.get_json()
        self.assertEqual(res_json.get("status"), "success")
        self.assertIn("detalhes", res_json)
        self.assertGreater(res_json["detalhes"]["total_linhas"], 0)

    def test_route_upload_invalid_extension(self):
        """Upload de arquivo não suportado deve retornar 400 com mensagem clara."""
        data = {
            "file": (io.BytesIO(b"conteudo invalido"), "extrato.txt")
        }
        response = self.client.post(
            "/api/statements/upload",
            data=data,
            content_type="multipart/form-data"
        )
        self.assertEqual(response.status_code, 400)
        res_json = response.get_json()
        self.assertEqual(res_json.get("status"), "error")


if __name__ == "__main__":
    unittest.main()
