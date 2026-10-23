import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from werkzeug.security import generate_password_hash

from app import create_app
from database.db import inicializar_banco, obter_conexao


class BaseBarberFlowTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = Path(self.temp_dir.name) / "teste.db"

        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "teste-segredo",
                "WTF_CSRF_ENABLED": False,
                "RATELIMIT_ENABLED": False,
                "DATABASE_PATH": str(self.db_path),
            }
        )
        self.contexto = self.app.app_context()
        self.contexto.push()
        self.addCleanup(self.contexto.pop)

        inicializar_banco()
        self.client = self.app.test_client()
        self.admin_id = self.criar_admin()

    def criar_admin(self, usuario="admin", senha="senha-segura-123"):
        with obter_conexao() as conexao:
            cursor = conexao.execute(
                """
                INSERT INTO administradores (usuario, senha_hash)
                VALUES (?, ?)
                """,
                (
                    usuario,
                    generate_password_hash(
                        senha, method="pbkdf2:sha256:1000"
                    ),
                ),
            )
            return cursor.lastrowid

    def criar_servico(
        self,
        nome="Corte",
        preco_centavos=4500,
        duracao_minutos=30,
        ativo=1,
    ):
        with obter_conexao() as conexao:
            cursor = conexao.execute(
                """
                INSERT INTO servicos (
                    nome, descricao, preco_centavos,
                    duracao_minutos, ativo
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (nome, f"Descrição de {nome}", preco_centavos, duracao_minutos, ativo),
            )
            return cursor.lastrowid

    def criar_profissional(
        self,
        nome="João",
        servico_id=None,
        dias=(0, 1, 2, 3, 4, 5),
        turnos=None,
        ativo=1,
    ):
        turnos = turnos or [("09:00", "12:00"), ("13:00", "19:00")]
        with obter_conexao() as conexao:
            cursor = conexao.execute(
                """
                INSERT INTO profissionais (nome, apelido, bio, ativo)
                VALUES (?, ?, ?, ?)
                """,
                (nome, nome.split()[0], "Profissional de teste", ativo),
            )
            profissional_id = cursor.lastrowid

            if servico_id:
                conexao.execute(
                    """
                    INSERT INTO profissional_servicos (
                        profissional_id, servico_id
                    )
                    VALUES (?, ?)
                    """,
                    (profissional_id, servico_id),
                )

            for dia in dias:
                for inicio, fim in turnos:
                    conexao.execute(
                        """
                        INSERT INTO horarios_trabalho (
                            profissional_id, dia_semana,
                            hora_inicio, hora_fim
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (profissional_id, dia, inicio, fim),
                    )

            return profissional_id

    def criar_cliente_google(
        self,
        nome="Ana Cliente",
        email=None,
        telefone="11912345678",
        google_sub=None,
    ):
        with obter_conexao() as conexao:
            cursor = conexao.execute(
                """
                INSERT INTO clientes (
                    google_sub, email, nome, telefone,
                    origem, telefone_confirmado_em
                )
                VALUES (?, ?, ?, ?, 'google', ?)
                """,
                (
                    google_sub or f"google-{nome.lower().replace(' ', '-')}",
                    email or f"{nome.split()[0].lower()}@exemplo.com",
                    nome,
                    telefone,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if telefone
                    else None,
                ),
            )
            return cursor.lastrowid

    def criar_cliente_manual(self, nome="Cliente Manual", telefone="11987654321"):
        with obter_conexao() as conexao:
            cursor = conexao.execute(
                """
                INSERT INTO clientes (
                    nome, telefone, origem, telefone_confirmado_em
                )
                VALUES (?, ?, 'manual', ?)
                """,
                (
                    nome,
                    telefone,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            return cursor.lastrowid

    def inserir_agendamento(
        self,
        cliente_id,
        servico_id,
        profissional_id,
        data,
        hora_inicio="10:00",
        hora_fim="10:30",
        status="pendente",
        status_pagamento="nao_pago",
        token_hash=None,
        preco_centavos=4500,
        duracao_minutos=30,
    ):
        if isinstance(data, date):
            data = data.isoformat()

        with obter_conexao() as conexao:
            cursor = conexao.execute(
                """
                INSERT INTO agendamentos (
                    cliente_id, servico_id, profissional_id,
                    data, hora_inicio, hora_fim, preco_centavos,
                    duracao_minutos, status, status_pagamento, token_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cliente_id,
                    servico_id,
                    profissional_id,
                    data,
                    hora_inicio,
                    hora_fim,
                    preco_centavos,
                    duracao_minutos,
                    status,
                    status_pagamento,
                    token_hash or f"hash-{cliente_id}-{data}-{hora_inicio}",
                ),
            )
            return cursor.lastrowid

    def login_admin(self):
        with self.client.session_transaction() as sessao:
            sessao["administrador_id"] = self.admin_id
            sessao["administrador_usuario"] = "admin"
            sessao["admin_ultima_atividade"] = datetime.now().isoformat()

    def login_cliente(self, cliente_id):
        with self.client.session_transaction() as sessao:
            sessao["cliente_id"] = cliente_id

    def proxima_data_util(self, dias=1):
        data = date.today() + timedelta(days=dias)
        while data.weekday() > 5:
            data += timedelta(days=1)
        return data
