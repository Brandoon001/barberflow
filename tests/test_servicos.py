import unittest

from database.db import obter_conexao
from tests.base import BaseBarberFlowTestCase


class ServicosAdminTestCase(BaseBarberFlowTestCase):
    def setUp(self):
        super().setUp()
        self.login_admin()

    def test_listagem_vazia(self):
        resposta = self.client.get("/admin/servicos")
        html = resposta.get_data(as_text=True)

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Nenhum serviço cadastrado", html)

    def test_cadastro_e_listagem_de_servico(self):
        resposta = self.client.post(
            "/admin/servicos",
            data={"nome": "Corte", "preco": "45,00", "duracao": "30"},
            follow_redirects=True,
        )
        html = resposta.get_data(as_text=True)

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Serviço cadastrado com sucesso.", html)
        self.assertIn("Corte", html)
        self.assertIn("R$ 45,00", html)
        self.assertIn("30 min", html)

        with obter_conexao() as conexao:
            servico = conexao.execute(
                "SELECT * FROM servicos WHERE nome = 'Corte'"
            ).fetchone()

        self.assertIsNotNone(servico)
        self.assertEqual(servico["preco_centavos"], 4500)
        self.assertEqual(servico["duracao_minutos"], 30)
        self.assertEqual(servico["ativo"], 1)

    def test_preco_invalido_nao_cadastra(self):
        resposta = self.client.post(
            "/admin/servicos",
            data={"nome": "Corte", "preco": "abc", "duracao": "30"},
        )
        html = resposta.get_data(as_text=True)

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Preço inválido.", html)

        with obter_conexao() as conexao:
            total = conexao.execute(
                "SELECT COUNT(*) AS total FROM servicos"
            ).fetchone()["total"]

        self.assertEqual(total, 0)

    def test_edicao_e_alternancia_de_situacao(self):
        servico_id = self.criar_servico("Corte", ativo=1)

        resposta = self.client.post(
            f"/admin/servicos/{servico_id}/editar",
            data={
                "nome": "Corte premium",
                "preco": "60,00",
                "duracao": "40",
                "ativo": "1",
            },
            follow_redirects=True,
        )
        html = resposta.get_data(as_text=True)

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Serviço atualizado com sucesso.", html)

        with obter_conexao() as conexao:
            servico = conexao.execute(
                "SELECT * FROM servicos WHERE id = ?", (servico_id,)
            ).fetchone()

        self.assertEqual(servico["nome"], "Corte premium")
        self.assertEqual(servico["preco_centavos"], 6000)
        self.assertEqual(servico["duracao_minutos"], 40)

        self.client.post(
            f"/admin/servicos/{servico_id}/situacao", follow_redirects=True
        )

        with obter_conexao() as conexao:
            servico = conexao.execute(
                "SELECT ativo FROM servicos WHERE id = ?", (servico_id,)
            ).fetchone()

        self.assertEqual(servico["ativo"], 0)


if __name__ == "__main__":
    unittest.main()
