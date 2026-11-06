import hashlib
import unittest

from database.db import inicializar_banco, obter_conexao
from tests.base import BaseBarberFlowTestCase
from views.decorators import destino_seguro


class PublicoSegurancaTestCase(BaseBarberFlowTestCase):
    def test_home_exibe_conteudo_ativo(self):
        self.criar_servico("Corte clássico")
        self.criar_servico("Serviço inativo", ativo=0)
        self.criar_profissional("Rafael")

        resposta = self.client.get("/")
        html = resposta.get_data(as_text=True)

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Corte clássico", html)
        self.assertNotIn("Serviço inativo", html)
        self.assertIn("Rafael", html)
        self.assertIn("Agendar horário", html)

    def test_home_exibe_mapa_quando_endereco_configurado(self):
        self.app.config["MARCA"]["endereco"] = (
            "Rua Augusta, 123 - São Paulo"
        )

        html = self.client.get("/").get_data(as_text=True)

        self.assertIn('id="localizacao"', html)
        self.assertIn("<iframe", html)
        self.assertIn("google.com/maps?q=", html)
        self.assertIn("output=embed", html)
        self.assertIn("Abrir no mapa", html)
        self.assertIn("Rua Augusta, 123", html)
        self.assertNotIn("mapa-placeholder", html)

    def test_home_exibe_placeholder_sem_endereco(self):
        self.app.config["MARCA"]["endereco"] = ""
        self.app.config["MAPA_EMBED_URL"] = ""
        self.app.config["MAPA_LINK"] = ""

        html = self.client.get("/").get_data(as_text=True)

        self.assertIn('id="localizacao"', html)
        self.assertIn("mapa-placeholder", html)
        self.assertIn("Endereço em breve", html)
        self.assertNotIn("<iframe", html)
        self.assertNotIn("google.com/maps", html)
        self.assertNotIn("Abrir no mapa", html)

    def test_home_exibe_mapa_customizado(self):
        self.app.config["MARCA"]["endereco"] = ""
        self.app.config["MAPA_EMBED_URL"] = (
            "https://www.openstreetmap.org/export/embed.html?bbox=1"
        )
        self.app.config["MAPA_LINK"] = "https://www.openstreetmap.org/"

        html = self.client.get("/").get_data(as_text=True)

        self.assertIn('id="localizacao"', html)
        self.assertIn("openstreetmap.org/export/embed.html", html)
        self.assertIn("Abrir no mapa", html)
        self.assertNotIn("mapa-placeholder", html)

    def test_paginas_publicas_e_status(self):
        for url in ("/", "/privacidade", "/politica-cancelamento", "/status"):
            resposta = self.client.get(url)
            self.assertEqual(resposta.status_code, 200, url)

        self.assertEqual(
            self.client.get("/status").get_json(),
            {"aplicacao": "ok", "banco": "ok"},
        )

    def test_inicializacao_do_banco_e_idempotente(self):
        inicializar_banco()
        inicializar_banco()

        with obter_conexao() as conexao:
            total = conexao.execute(
                "SELECT COUNT(*) AS total FROM schema_migrations"
            ).fetchone()["total"]

        self.assertGreaterEqual(total, 3)

    def test_cabecalhos_de_seguranca(self):
        resposta = self.client.get("/")

        self.assertEqual(
            resposta.headers["X-Content-Type-Options"], "nosniff"
        )
        self.assertEqual(resposta.headers["X-Frame-Options"], "DENY")
        csp = resposta.headers["Content-Security-Policy"]
        self.assertIn("default-src 'self'", csp)
        self.assertNotIn("accounts.google.com/gsi", csp)
        self.assertIn("https://www.google.com", csp)
        self.assertIn("https://maps.google.com", csp)
        self.assertIn("frame-ancestors 'none'", csp)

    def test_rotas_privadas_exigem_login(self):
        for url in ("/minha-conta", "/agendamento"):
            resposta = self.client.get(url)
            self.assertEqual(resposta.status_code, 302)
            self.assertIn("/auth/google", resposta.headers["Location"])

    def test_consulta_nao_permite_token_de_outro_cliente(self):
        servico_id = self.criar_servico()
        profissional_id = self.criar_profissional(servico_id=servico_id)
        cliente_a = self.criar_cliente_google("Ana", telefone="11911111111")
        cliente_b = self.criar_cliente_google("Bia", telefone="11922222222")
        token = "token-secreto"
        self.inserir_agendamento(
            cliente_a,
            servico_id,
            profissional_id,
            self.proxima_data_util(),
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
        )

        self.login_cliente(cliente_b)
        resposta = self.client.get(f"/agendamento/consulta/{token}")

        self.assertEqual(resposta.status_code, 404)

    def test_destino_seguro_bloqueia_redirecionamento_externo(self):
        self.assertEqual(destino_seguro("https://evil.test", "/ok"), "/ok")
        self.assertEqual(destino_seguro("//evil.test", "/ok"), "/ok")
        self.assertEqual(destino_seguro("/\\evil.test", "/ok"), "/ok")
        self.assertEqual(
            destino_seguro("/admin/agenda?data=2026-01-01", "/ok"),
            "/admin/agenda?data=2026-01-01",
        )

    def test_csrf_bloqueia_post_sem_token(self):
        self.app.config["WTF_CSRF_ENABLED"] = True

        resposta = self.client.post(
            "/admin/login",
            data={"usuario": "admin", "senha": "senha-segura-123"},
        )

        self.assertEqual(resposta.status_code, 400)


if __name__ == "__main__":
    unittest.main()
