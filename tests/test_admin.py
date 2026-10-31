import unittest

from database.db import obter_conexao
from tests.base import BaseBarberFlowTestCase


class AdminTestCase(BaseBarberFlowTestCase):
    def test_login_protege_painel(self):
        resposta = self.client.get("/admin/")

        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/admin/login", resposta.headers["Location"])

    def test_login_com_senha_incorreta(self):
        resposta = self.client.post(
            "/admin/login",
            data={"usuario": "admin", "senha": "senha-errada"},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertIn(
            "Usuário ou senha inválidos.", resposta.get_data(as_text=True)
        )

    def test_login_com_sucesso(self):
        resposta = self.client.post(
            "/admin/login",
            data={"usuario": "admin", "senha": "senha-segura-123"},
            follow_redirects=True,
        )
        html = resposta.get_data(as_text=True)

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Login realizado com sucesso.", html)
        self.assertIn("Visão geral", html)

    def test_cadastro_manual_e_telefone_duplicado(self):
        self.login_admin()
        resposta = self.client.post(
            "/admin/clientes/novo",
            data={"nome": "Cliente Manual", "telefone": "(11) 98765-4321"},
            follow_redirects=True,
        )
        html = resposta.get_data(as_text=True)

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Cliente cadastrado com sucesso.", html)
        self.assertIn("(11) 98765-4321", html)

        duplicado = self.client.post(
            "/admin/clientes/novo",
            data={"nome": "Outro Cliente", "telefone": "11987654321"},
            follow_redirects=True,
        )

        self.assertIn(
            "Já existe um cliente ativo com esse WhatsApp.",
            duplicado.get_data(as_text=True),
        )

        with obter_conexao() as conexao:
            total = conexao.execute(
                "SELECT COUNT(*) AS total FROM clientes"
            ).fetchone()["total"]

        self.assertEqual(total, 1)

    def test_edicao_de_cliente_atualiza_whatsapp(self):
        cliente_id = self.criar_cliente_manual(telefone="11911111111")
        self.login_admin()

        resposta = self.client.post(
            f"/admin/clientes/{cliente_id}/editar",
            data={
                "nome": "Cliente Atualizado",
                "telefone": "(11) 92222-2222",
                "ativo": "1",
            },
            follow_redirects=True,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertIn(
            "Cliente atualizado com sucesso.", resposta.get_data(as_text=True)
        )

        with obter_conexao() as conexao:
            cliente = conexao.execute(
                "SELECT * FROM clientes WHERE id = ?",
                (cliente_id,),
            ).fetchone()

        self.assertEqual(cliente["nome"], "Cliente Atualizado")
        self.assertEqual(cliente["telefone"], "11922222222")
        self.assertIsNotNone(cliente["telefone_informado_em"])

    def test_clientes_mostra_alerta_de_manual_com_mesmo_whatsapp(self):
        telefone = "11955554444"
        self.criar_cliente_manual(
            nome="Cliente Manual", telefone=telefone
        )
        self.criar_cliente_google(
            nome="Cliente Google", telefone=telefone
        )
        self.login_admin()

        resposta = self.client.get("/admin/clientes")
        html = resposta.get_data(as_text=True)

        self.assertEqual(resposta.status_code, 200)
        self.assertIn(
            "Existe cadastro manual com este WhatsApp", html
        )
        self.assertIn("avalie vincular", html)

    def test_vinculo_manual_transfere_agendamentos(self):
        manual_id = self.criar_cliente_manual()
        google_id = self.criar_cliente_google("Ana Google")
        servico_id = self.criar_servico()
        profissional_id = self.criar_profissional(servico_id=servico_id)
        agendamento_id = self.inserir_agendamento(
            manual_id,
            servico_id,
            profissional_id,
            self.proxima_data_util(3),
        )
        self.login_admin()

        resposta = self.client.post(
            f"/admin/clientes/{manual_id}/vincular",
            data={"principal_id": str(google_id)},
            follow_redirects=True,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertIn(
            "Cadastros vinculados e agendamentos transferidos.",
            resposta.get_data(as_text=True),
        )

        with obter_conexao() as conexao:
            manual = conexao.execute(
                "SELECT * FROM clientes WHERE id = ?", (manual_id,)
            ).fetchone()
            agendamento = conexao.execute(
                "SELECT cliente_id FROM agendamentos WHERE id = ?",
                (agendamento_id,),
            ).fetchone()

        self.assertEqual(manual["ativo"], 0)
        self.assertEqual(manual["cliente_principal_id"], google_id)
        self.assertEqual(agendamento["cliente_id"], google_id)

    def test_confirmar_e_concluir_agendamento(self):
        cliente_id = self.criar_cliente_google()
        servico_id = self.criar_servico()
        profissional_id = self.criar_profissional(servico_id=servico_id)
        agendamento_id = self.inserir_agendamento(
            cliente_id,
            servico_id,
            profissional_id,
            self.proxima_data_util(2),
            status="pendente",
        )
        self.login_admin()

        self.client.post(
            f"/admin/agenda/{agendamento_id}/confirmar",
            data={"voltar": "/admin/agenda"},
            follow_redirects=True,
        )

        with obter_conexao() as conexao:
            status = conexao.execute(
                "SELECT status FROM agendamentos WHERE id = ?",
                (agendamento_id,),
            ).fetchone()["status"]

        self.assertEqual(status, "confirmado")

        self.client.post(
            f"/admin/agenda/{agendamento_id}/concluir",
            data={"voltar": "/admin/agenda"},
            follow_redirects=True,
        )

        with obter_conexao() as conexao:
            status = conexao.execute(
                "SELECT status FROM agendamentos WHERE id = ?",
                (agendamento_id,),
            ).fetchone()["status"]

        self.assertEqual(status, "concluido")

    def test_cancelamento_e_reembolso_pelo_admin(self):
        cliente_id = self.criar_cliente_google()
        servico_id = self.criar_servico()
        profissional_id = self.criar_profissional(servico_id=servico_id)
        agendamento_id = self.inserir_agendamento(
            cliente_id,
            servico_id,
            profissional_id,
            self.proxima_data_util(3),
            status="confirmado",
            status_pagamento="pago",
        )
        self.login_admin()

        self.client.post(
            f"/admin/agenda/{agendamento_id}/cancelar",
            data={"voltar": "/admin/agenda", "motivo": "Loja fechada"},
            follow_redirects=True,
        )

        with obter_conexao() as conexao:
            agendamento = conexao.execute(
                "SELECT * FROM agendamentos WHERE id = ?",
                (agendamento_id,),
            ).fetchone()

        self.assertEqual(agendamento["status"], "cancelado")
        self.assertEqual(agendamento["cancelado_por"], "admin")
        self.assertEqual(agendamento["motivo_cancelamento"], "Loja fechada")
        self.assertEqual(
            agendamento["status_pagamento"], "reembolso_pendente"
        )

        self.client.post(
            f"/admin/agenda/{agendamento_id}/reembolso",
            data={"voltar": "/admin/agenda", "observacao": "Devolvido via Pix"},
            follow_redirects=True,
        )

        with obter_conexao() as conexao:
            agendamento = conexao.execute(
                "SELECT * FROM agendamentos WHERE id = ?",
                (agendamento_id,),
            ).fetchone()

        self.assertEqual(agendamento["status_pagamento"], "reembolsado")
        self.assertEqual(agendamento["reembolso_observacao"], "Devolvido via Pix")
        self.assertIsNotNone(agendamento["reembolsado_em"])

    def test_horario_invalido_nao_altera_jornada(self):
        servico_id = self.criar_servico()
        profissional_id = self.criar_profissional(servico_id=servico_id)
        self.login_admin()

        resposta = self.client.post(
            f"/admin/profissionais/{profissional_id}/horarios",
            data={
                "inicio_0_0": "10:00",
                "fim_0_0": "09:00",
            },
            follow_redirects=True,
        )

        self.assertIn(
            "O início do turno deve ser antes do fim.",
            resposta.get_data(as_text=True),
        )

        with obter_conexao() as conexao:
            total = conexao.execute(
                """
                SELECT COUNT(*) AS total
                FROM horarios_trabalho
                WHERE profissional_id = ?
                """,
                (profissional_id,),
            ).fetchone()["total"]

        self.assertEqual(total, 12)


if __name__ == "__main__":
    unittest.main()
