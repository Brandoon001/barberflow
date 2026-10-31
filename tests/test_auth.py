import unittest
from unittest.mock import patch

from app import create_app
from config import obter_config
from database.db import obter_conexao
from extensions import oauth
from tests.base import BaseBarberFlowTestCase


class AuthTestCase(BaseBarberFlowTestCase):
    def _configurar_google(self):
        self.app.config.update(
            {
                "GOOGLE_CLIENT_ID": "cliente-teste",
                "GOOGLE_CLIENT_SECRET": "segredo-teste",
                "GOOGLE_REDIRECT_URI": (
                    "http://localhost:5000/auth/google/callback"
                ),
            }
        )

    def _perfil_google(
        self,
        sub="google-novo",
        email="novo@exemplo.com",
        nome="Novo Cliente",
        email_verified=True,
    ):
        return {
            "sub": sub,
            "email": email,
            "email_verified": email_verified,
            "name": nome,
            "picture": "https://exemplo.com/avatar.png",
        }

    def _callback(self, perfil):
        with patch.object(
            oauth.google,
            "authorize_access_token",
            return_value={"userinfo": perfil},
        ):
            return self.client.get("/auth/google/callback")

    def test_pagina_entrar_exibe_login_google(self):
        self._configurar_google()

        resposta = self.client.get("/entrar?next=/agendamento")
        html = resposta.get_data(as_text=True)

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Entrar com Google", html)
        self.assertIn("/auth/google", html)

    def test_pagina_entrar_sem_configuracao_avisa_indisponivel(self):
        self.app.config.update(
            {"GOOGLE_CLIENT_ID": "", "GOOGLE_CLIENT_SECRET": ""}
        )

        resposta = self.client.get("/entrar")
        html = resposta.get_data(as_text=True)

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("temporariamente indisponível", html)

    def test_callback_cria_cliente_e_pede_whatsapp(self):
        self._configurar_google()
        perfil = self._perfil_google()

        resposta = self._callback(perfil)

        self.assertEqual(resposta.status_code, 302)
        self.assertIn(
            "/cliente/completar-cadastro", resposta.headers["Location"]
        )

        with obter_conexao() as conexao:
            cliente = conexao.execute(
                "SELECT * FROM clientes WHERE google_sub = ?",
                (perfil["sub"],),
            ).fetchone()

        self.assertIsNotNone(cliente)
        self.assertEqual(cliente["email"], perfil["email"])
        self.assertEqual(cliente["nome"], perfil["name"])
        self.assertEqual(cliente["origem"], "google")
        self.assertIsNone(cliente["telefone"])

        with self.client.session_transaction() as sessao:
            self.assertEqual(sessao["cliente_id"], cliente["id"])

    def test_callback_atualiza_cliente_existente(self):
        self._configurar_google()
        cliente_id = self.criar_cliente_google(
            nome="Ana Antiga",
            email="ana@exemplo.com",
            google_sub="google-ana",
        )
        perfil = self._perfil_google(
            sub="google-ana",
            email="ana@exemplo.com",
            nome="Ana Atualizada",
        )

        resposta = self._callback(perfil)

        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/minha-conta", resposta.headers["Location"])

        with obter_conexao() as conexao:
            cliente = conexao.execute(
                "SELECT * FROM clientes WHERE id = ?",
                (cliente_id,),
            ).fetchone()

        self.assertEqual(cliente["nome"], "Ana Atualizada")

    def test_callback_recusa_email_nao_verificado(self):
        self._configurar_google()
        perfil = self._perfil_google(email_verified=False)

        resposta = self._callback(perfil)

        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/entrar", resposta.headers["Location"])

        with obter_conexao() as conexao:
            total = conexao.execute(
                "SELECT COUNT(*) AS total FROM clientes"
            ).fetchone()["total"]

        self.assertEqual(total, 0)

    def test_callback_recusa_conta_desativada(self):
        self._configurar_google()
        cliente_id = self.criar_cliente_google(google_sub="google-off")
        with obter_conexao() as conexao:
            conexao.execute(
                "UPDATE clientes SET ativo = 0 WHERE id = ?",
                (cliente_id,),
            )

        resposta = self._callback(
            self._perfil_google(sub="google-off")
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/entrar", resposta.headers["Location"])

        with self.client.session_transaction() as sessao:
            self.assertNotIn("cliente_id", sessao)

    def test_completar_cadastro_persiste_consentimento(self):
        cliente_id = self.criar_cliente_google(
            telefone=None,
            google_sub="google-sem-telefone",
        )
        self.login_cliente(cliente_id)

        resposta = self.client.post(
            "/cliente/completar-cadastro",
            data={
                "telefone": "(11) 98888-7777",
                "consentimento": "1",
            },
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/minha-conta", resposta.headers["Location"])

        with obter_conexao() as conexao:
            cliente = conexao.execute(
                "SELECT * FROM clientes WHERE id = ?",
                (cliente_id,),
            ).fetchone()

        self.assertEqual(cliente["telefone"], "11988887777")
        self.assertIsNotNone(cliente["telefone_informado_em"])
        self.assertIsNotNone(cliente["consentimento_em"])
        self.assertEqual(cliente["consentimento_versao"], "2026-10")

    def test_cliente_pode_corrigir_whatsapp(self):
        cliente_id = self.criar_cliente_google(telefone="11911111111")
        self.login_cliente(cliente_id)

        resposta = self.client.post(
            "/minha-conta/perfil",
            data={
                "telefone": "(11) 97777-6666",
                "consentimento": "1",
            },
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/minha-conta", resposta.headers["Location"])

        with obter_conexao() as conexao:
            cliente = conexao.execute(
                "SELECT * FROM clientes WHERE id = ?",
                (cliente_id,),
            ).fetchone()

        self.assertEqual(cliente["telefone"], "11977776666")
        self.assertIsNotNone(cliente["consentimento_em"])

    def test_logout_do_cliente_preserva_admin(self):
        cliente_id = self.criar_cliente_google()
        self.login_cliente(cliente_id)
        self.login_admin()

        resposta = self.client.post("/auth/logout")

        self.assertEqual(resposta.status_code, 302)
        with self.client.session_transaction() as sessao:
            self.assertNotIn("cliente_id", sessao)
            self.assertEqual(sessao["administrador_id"], self.admin_id)

    def test_producao_falha_rapidamente_com_configuracao_insegura(self):
        with self.assertRaises(RuntimeError) as contexto:
            create_app(
                {
                    "ENV": "production",
                    "SECRET_KEY": "dev-apenas-nao-use-em-producao",
                    "DATABASE_PATH": str(self.db_path),
                    "SESSION_COOKIE_SECURE": False,
                    "GOOGLE_CLIENT_ID": "",
                    "GOOGLE_CLIENT_SECRET": "",
                    "GOOGLE_REDIRECT_URI": (
                        "http://localhost:5000/auth/google/callback"
                    ),
                }
            )

        mensagem = str(contexto.exception)
        self.assertIn("SECRET_KEY", mensagem)
        self.assertIn("GOOGLE_CLIENT_ID", mensagem)
        self.assertIn("GOOGLE_REDIRECT_URI", mensagem)
        self.assertIn("SESSION_COOKIE_SECURE", mensagem)

    def test_ambiente_invalido_nao_cai_em_desenvolvimento(self):
        with self.assertRaises(ValueError):
            obter_config("prod")


if __name__ == "__main__":
    unittest.main()
