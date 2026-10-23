import hashlib
import unittest
from datetime import date, datetime

from database.db import obter_conexao
from services import agenda
from tests.base import BaseBarberFlowTestCase


class AgendamentoTestCase(BaseBarberFlowTestCase):
    def test_fluxo_de_agendamento_e_token_hasheado(self):
        servico_id = self.criar_servico(duracao_minutos=30)
        profissional_id = self.criar_profissional(servico_id=servico_id)
        cliente_id = self.criar_cliente_google()
        self.login_cliente(cliente_id)
        data = self.proxima_data_util(2)

        resposta = self.client.get(
            "/agendamento",
            query_string={
                "servico_id": servico_id,
                "profissional_id": profissional_id,
                "data": data.isoformat(),
            },
        )
        html = resposta.get_data(as_text=True)

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("09:00", html)
        self.assertIn("Escolha o horário", html)

        resposta = self.client.post(
            "/agendamento",
            data={
                "servico_id": servico_id,
                "profissional_id": profissional_id,
                "data": data.isoformat(),
                "hora_inicio": "09:00",
                "observacoes": "Corte baixo",
            },
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/agendamento/consulta/", resposta.headers["Location"])
        token = resposta.headers["Location"].rsplit("/", 1)[-1]

        with obter_conexao() as conexao:
            agendamento = conexao.execute(
                "SELECT * FROM agendamentos"
            ).fetchone()

        self.assertIsNotNone(agendamento)
        self.assertEqual(agendamento["cliente_id"], cliente_id)
        self.assertEqual(agendamento["status"], "pendente")
        self.assertEqual(agendamento["status_pagamento"], "nao_pago")
        self.assertEqual(agendamento["hora_fim"], "09:30")
        self.assertNotEqual(agendamento["token_hash"], token)
        self.assertEqual(
            agendamento["token_hash"],
            hashlib.sha256(token.encode()).hexdigest(),
        )
        self.assertEqual(agendamento["observacoes"], "Corte baixo")

        consulta = self.client.get(resposta.headers["Location"])
        self.assertEqual(consulta.status_code, 200)
        self.assertIn("Corte", consulta.get_data(as_text=True))

    def test_horario_ocupado_nao_pode_ser_reservado_novamente(self):
        servico_id = self.criar_servico(duracao_minutos=30)
        profissional_id = self.criar_profissional(servico_id=servico_id)
        cliente_id = self.criar_cliente_google()
        self.login_cliente(cliente_id)
        data = self.proxima_data_util(2)
        dados = {
            "servico_id": servico_id,
            "profissional_id": profissional_id,
            "data": data.isoformat(),
            "hora_inicio": "09:00",
        }

        primeira = self.client.post("/agendamento", data=dados)
        segunda = self.client.post("/agendamento", data=dados)

        self.assertEqual(primeira.status_code, 302)
        self.assertEqual(segunda.status_code, 200)
        self.assertIn(
            "Esse horário não está mais disponível",
            segunda.get_data(as_text=True),
        )

        with obter_conexao() as conexao:
            total = conexao.execute(
                "SELECT COUNT(*) AS total FROM agendamentos"
            ).fetchone()["total"]

        self.assertEqual(total, 1)

    def test_disponibilidade_respeita_almoco_e_conflito(self):
        servico_id = self.criar_servico(duracao_minutos=60)
        profissional_id = self.criar_profissional(servico_id=servico_id)
        cliente_id = self.criar_cliente_google()
        data = date(2026, 1, 5)

        self.inserir_agendamento(
            cliente_id,
            servico_id,
            profissional_id,
            data,
            hora_inicio="10:00",
            hora_fim="11:00",
            duracao_minutos=60,
        )

        horarios = agenda.horarios_disponiveis(
            servico_id,
            profissional_id,
            data,
            agora=datetime(2026, 1, 5, 8, 0),
        )

        self.assertIn("09:00", horarios)
        self.assertNotIn("10:00", horarios)
        self.assertNotIn("12:00", horarios)
        self.assertIn("13:00", horarios)
        self.assertIn("18:00", horarios)
        self.assertNotIn("18:30", horarios)

    def test_cancelamento_pelo_cliente_gera_reembolso_pendente(self):
        servico_id = self.criar_servico()
        profissional_id = self.criar_profissional(servico_id=servico_id)
        cliente_id = self.criar_cliente_google()
        token = "token-cancelamento"
        agendamento_id = self.inserir_agendamento(
            cliente_id,
            servico_id,
            profissional_id,
            self.proxima_data_util(3),
            status="confirmado",
            status_pagamento="pago",
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
        )

        retorno = agenda.cancelar_pelo_cliente(
            token, cliente_id, motivo="Imprevisto"
        )

        self.assertEqual(retorno, (agendamento_id, True))

        with obter_conexao() as conexao:
            agendamento = conexao.execute(
                "SELECT * FROM agendamentos WHERE id = ?",
                (agendamento_id,),
            ).fetchone()

        self.assertEqual(agendamento["status"], "cancelado")
        self.assertEqual(agendamento["cancelado_por"], "cliente")
        self.assertEqual(agendamento["motivo_cancelamento"], "Imprevisto")
        self.assertEqual(
            agendamento["status_pagamento"], "reembolso_pendente"
        )
        self.assertIsNotNone(agendamento["reembolso_solicitado_em"])

    def test_cancelamento_apos_prazo_e_bloqueado(self):
        servico_id = self.criar_servico()
        profissional_id = self.criar_profissional(servico_id=servico_id)
        cliente_id = self.criar_cliente_google()
        agendamento_id = self.inserir_agendamento(
            cliente_id,
            servico_id,
            profissional_id,
            date(2026, 1, 5),
            hora_inicio="10:00",
            hora_fim="10:30",
            status="confirmado",
            token_hash=hashlib.sha256(b"token-prazo").hexdigest(),
        )

        with self.assertRaisesRegex(ValueError, "prazo de cancelamento"):
            agenda.cancelar_pelo_cliente(
                "token-prazo",
                cliente_id,
                agora=datetime(2026, 1, 5, 9, 40),
            )

        with obter_conexao() as conexao:
            status = conexao.execute(
                "SELECT status FROM agendamentos WHERE id = ?",
                (agendamento_id,),
            ).fetchone()["status"]

        self.assertEqual(status, "confirmado")

    def test_cancelamento_pela_conta_do_cliente(self):
        servico_id = self.criar_servico()
        profissional_id = self.criar_profissional(servico_id=servico_id)
        cliente_id = self.criar_cliente_google()
        agendamento_id = self.inserir_agendamento(
            cliente_id,
            servico_id,
            profissional_id,
            self.proxima_data_util(4),
            status="pendente",
        )
        self.login_cliente(cliente_id)

        resposta = self.client.post(
            f"/minha-conta/agendamento/{agendamento_id}/cancelar",
            data={"motivo": "Não poderei comparecer"},
            follow_redirects=True,
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Agendamento cancelado com sucesso.", resposta.get_data(as_text=True))

        with obter_conexao() as conexao:
            agendamento = conexao.execute(
                "SELECT status, motivo_cancelamento FROM agendamentos WHERE id = ?",
                (agendamento_id,),
            ).fetchone()

        self.assertEqual(agendamento["status"], "cancelado")
        self.assertEqual(
            agendamento["motivo_cancelamento"], "Não poderei comparecer"
        )

    def test_consulta_exige_cliente_do_agendamento(self):
        servico_id = self.criar_servico()
        profissional_id = self.criar_profissional(servico_id=servico_id)
        cliente_id = self.criar_cliente_google()
        token = "token-do-dono"
        self.inserir_agendamento(
            cliente_id,
            servico_id,
            profissional_id,
            self.proxima_data_util(3),
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
        )
        self.login_cliente(cliente_id)

        resposta = self.client.get(f"/agendamento/consulta/{token}")

        self.assertEqual(resposta.status_code, 200)


if __name__ == "__main__":
    unittest.main()
