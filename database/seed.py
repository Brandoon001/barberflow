from database.db import obter_conexao


SERVICOS_DEMO = [
    ("Corte clássico", "Corte na tesoura ou máquina com finalização.", 4500, 30),
    ("Barba completa", "Toalha quente, navalha e hidratação.", 3500, 30),
    ("Corte + barba", "Combo completo para sair renovado.", 7000, 60),
    ("Pezinho", "Acabamento rápido na nuca e laterais.", 1500, 15),
]

PROFISSIONAIS_DEMO = [
    ("Rafael Costa", "Rafael", "Especialista em cortes clássicos."),
    ("Diego Almeida", "Diego", "Barba, navalha e degradê."),
]

TURNOS_PADRAO = [
    (0, "09:00", "12:00"),
    (0, "13:00", "19:00"),
    (1, "09:00", "12:00"),
    (1, "13:00", "19:00"),
    (2, "09:00", "12:00"),
    (2, "13:00", "19:00"),
    (3, "09:00", "12:00"),
    (3, "13:00", "19:00"),
    (4, "09:00", "12:00"),
    (4, "13:00", "19:00"),
    (5, "09:00", "12:00"),
    (5, "13:00", "18:00"),
]


def criar_dados_demo():
    with obter_conexao(imediata=True) as conexao:
        ids_servicos = []
        for nome, descricao, preco, duracao in SERVICOS_DEMO:
            existente = conexao.execute(
                "SELECT id FROM servicos WHERE nome = ?",
                (nome,),
            ).fetchone()

            if existente:
                ids_servicos.append(existente["id"])
                continue

            cursor = conexao.execute(
                """
                INSERT INTO servicos (
                    nome, descricao, preco_centavos, duracao_minutos, ativo
                )
                VALUES (?, ?, ?, ?, 1)
                """,
                (nome, descricao, preco, duracao),
            )
            ids_servicos.append(cursor.lastrowid)

        for nome, apelido, bio in PROFISSIONAIS_DEMO:
            profissional = conexao.execute(
                "SELECT id FROM profissionais WHERE nome = ?",
                (nome,),
            ).fetchone()

            if profissional:
                profissional_id = profissional["id"]
            else:
                cursor = conexao.execute(
                    """
                    INSERT INTO profissionais (nome, apelido, bio, ativo)
                    VALUES (?, ?, ?, 1)
                    """,
                    (nome, apelido, bio),
                )
                profissional_id = cursor.lastrowid

            for servico_id in ids_servicos:
                conexao.execute(
                    """
                    INSERT OR IGNORE INTO profissional_servicos (
                        profissional_id, servico_id
                    )
                    VALUES (?, ?)
                    """,
                    (profissional_id, servico_id),
                )

            possui_horarios = conexao.execute(
                """
                SELECT 1 FROM horarios_trabalho
                WHERE profissional_id = ?
                LIMIT 1
                """,
                (profissional_id,),
            ).fetchone()

            if not possui_horarios:
                for dia, inicio, fim in TURNOS_PADRAO:
                    conexao.execute(
                        """
                        INSERT INTO horarios_trabalho (
                            profissional_id, dia_semana, hora_inicio, hora_fim
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (profissional_id, dia, inicio, fim),
                    )
