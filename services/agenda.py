import hashlib
import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import current_app, has_app_context

from database.db import obter_conexao
from services.validacao import (
    combinar_data_hora,
    limpar_texto,
    parse_data,
    parse_hora,
)


STATUS_ATIVOS = ("pendente", "confirmado")
STATUS_VALIDOS = ("pendente", "confirmado", "cancelado", "concluido")
PAGAMENTOS_VALIDOS = (
    "nao_pago",
    "pago",
    "reembolso_pendente",
    "reembolsado",
)


def agora_local():
    fuso = "America/Sao_Paulo"
    if has_app_context():
        fuso = current_app.config.get("TIMEZONE", fuso)
    return datetime.now(ZoneInfo(fuso)).replace(tzinfo=None)


def _hash_token(token):
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _minutos(hora_texto):
    hora = parse_hora(hora_texto)
    return hora.hour * 60 + hora.minute


def _texto_hora(minutos):
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def _carregar_servico(conexao, servico_id):
    return conexao.execute(
        """
        SELECT id, nome, descricao, preco_centavos, duracao_minutos, ativo
        FROM servicos
        WHERE id = ?
        """,
        (servico_id,),
    ).fetchone()


def _carregar_profissional(conexao, profissional_id):
    return conexao.execute(
        """
        SELECT id, nome, apelido, bio, ativo
        FROM profissionais
        WHERE id = ?
        """,
        (profissional_id,),
    ).fetchone()


def _profissional_atende(conexao, profissional_id, servico_id):
    return conexao.execute(
        """
        SELECT 1
        FROM profissional_servicos
        WHERE profissional_id = ? AND servico_id = ?
        """,
        (profissional_id, servico_id),
    ).fetchone() is not None


def _validar_data_agendamento(data, agora):
    dias_futuros = current_app.config["AGENDAMENTO_DIAS_FUTUROS"]
    if data < agora.date():
        raise ValueError("Não é possível agendar em uma data passada.")
    if (data - agora.date()).days > dias_futuros:
        raise ValueError(
            f"Agendamentos são permitidos com até {dias_futuros} dias de antecedência."
        )


def _horarios_disponiveis(conexao, servico, profissional, data, agora):
    _validar_data_agendamento(data, agora)

    jornadas = conexao.execute(
        """
        SELECT hora_inicio, hora_fim
        FROM horarios_trabalho
        WHERE profissional_id = ? AND dia_semana = ?
        ORDER BY hora_inicio
        """,
        (profissional["id"], data.weekday()),
    ).fetchall()

    if not jornadas:
        return []

    ocupados = conexao.execute(
        """
        SELECT hora_inicio, hora_fim
        FROM agendamentos
        WHERE profissional_id = ?
          AND data = ?
          AND status IN ('pendente', 'confirmado')
        """,
        (profissional["id"], data.isoformat()),
    ).fetchall()

    intervalos_ocupados = [
        (
            combinar_data_hora(data, item["hora_inicio"]),
            combinar_data_hora(data, item["hora_fim"]),
        )
        for item in ocupados
    ]

    intervalo = current_app.config["AGENDAMENTO_INTERVALO_MINUTOS"]
    duracao = servico["duracao_minutos"]
    disponiveis = []

    for jornada in jornadas:
        inicio_jornada = _minutos(jornada["hora_inicio"])
        fim_jornada = _minutos(jornada["hora_fim"])

        for inicio_minutos in range(inicio_jornada, fim_jornada, intervalo):
            if inicio_minutos + duracao > fim_jornada:
                continue

            inicio = combinar_data_hora(
                data, _texto_hora(inicio_minutos)
            )
            fim = inicio + timedelta(minutes=duracao)

            if inicio <= agora:
                continue

            conflito = any(
                inicio < ocupado_fim and fim > ocupado_inicio
                for ocupado_inicio, ocupado_fim in intervalos_ocupados
            )
            if not conflito:
                disponiveis.append(inicio.strftime("%H:%M"))

    return sorted(set(disponiveis))


def horarios_disponiveis(servico_id, profissional_id, data, agora=None):
    agora = agora or agora_local()
    data = parse_data(data) if isinstance(data, str) else data

    with obter_conexao() as conexao:
        servico = _carregar_servico(conexao, servico_id)
        profissional = _carregar_profissional(conexao, profissional_id)

        if not servico or not servico["ativo"]:
            raise ValueError("Serviço indisponível.")
        if not profissional or not profissional["ativo"]:
            raise ValueError("Profissional indisponível.")
        if not _profissional_atende(conexao, profissional_id, servico_id):
            raise ValueError("Este profissional não atende o serviço escolhido.")

        return _horarios_disponiveis(
            conexao, servico, profissional, data, agora
        )


def criar_agendamento(
    cliente_id,
    servico_id,
    profissional_id,
    data,
    hora_inicio,
    observacoes="",
    agora=None,
):
    agora = agora or agora_local()
    data = parse_data(data) if isinstance(data, str) else data
    hora_inicio = hora_inicio.strip()
    observacoes = limpar_texto(observacoes, 500)

    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)

    with obter_conexao(imediata=True) as conexao:
        cliente = conexao.execute(
            """
            SELECT id, nome, telefone, ativo
            FROM clientes
            WHERE id = ?
            """,
            (cliente_id,),
        ).fetchone()

        if not cliente or not cliente["ativo"]:
            raise ValueError("Cliente inválido.")
        if not cliente["telefone"]:
            raise ValueError("Complete seu WhatsApp antes de agendar.")

        servico = _carregar_servico(conexao, servico_id)
        profissional = _carregar_profissional(conexao, profissional_id)

        if not servico or not servico["ativo"]:
            raise ValueError("Serviço indisponível.")
        if not profissional or not profissional["ativo"]:
            raise ValueError("Profissional indisponível.")
        if not _profissional_atende(conexao, profissional_id, servico_id):
            raise ValueError("Este profissional não atende o serviço escolhido.")

        disponiveis = _horarios_disponiveis(
            conexao, servico, profissional, data, agora
        )
        if hora_inicio not in disponiveis:
            raise ValueError(
                "Esse horário não está mais disponível. Escolha outro."
            )

        hora_fim = (
            combinar_data_hora(data, hora_inicio)
            + timedelta(minutes=servico["duracao_minutos"])
        ).strftime("%H:%M")

        status = (
            "confirmado"
            if current_app.config["AGENDAMENTO_CONFIRMACAO_AUTOMATICA"]
            else "pendente"
        )

        try:
            cursor = conexao.execute(
                """
                INSERT INTO agendamentos (
                    cliente_id, servico_id, profissional_id,
                    data, hora_inicio, hora_fim,
                    preco_centavos, duracao_minutos, observacoes,
                    status, status_pagamento, token_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'nao_pago', ?)
                """,
                (
                    cliente_id,
                    servico_id,
                    profissional_id,
                    data.isoformat(),
                    hora_inicio,
                    hora_fim,
                    servico["preco_centavos"],
                    servico["duracao_minutos"],
                    observacoes or None,
                    status,
                    token_hash,
                ),
            )
        except Exception as erro:
            if "UNIQUE constraint failed" in str(erro):
                raise ValueError(
                    "Esse horário acabou de ser reservado. Escolha outro."
                ) from erro
            raise

        return cursor.lastrowid, token


def _buscar_por_token(conexao, token, cliente_id=None):
    sql = """
        SELECT a.*, s.nome AS servico_nome, p.nome AS profissional_nome,
               c.nome AS cliente_nome, c.telefone AS cliente_telefone,
               c.email AS cliente_email
        FROM agendamentos a
        JOIN servicos s ON s.id = a.servico_id
        JOIN profissionais p ON p.id = a.profissional_id
        JOIN clientes c ON c.id = a.cliente_id
        WHERE a.token_hash = ?
    """
    parametros = [_hash_token(token)]
    if cliente_id is not None:
        sql += " AND a.cliente_id = ?"
        parametros.append(cliente_id)

    return conexao.execute(sql, tuple(parametros)).fetchone()


def buscar_por_token(token, cliente_id=None, conexao=None):
    if conexao is not None:
        return _buscar_por_token(conexao, token, cliente_id)

    with obter_conexao() as propria_conexao:
        return _buscar_por_token(propria_conexao, token, cliente_id)


def buscar_por_id(agendamento_id, cliente_id=None):
    with obter_conexao() as conexao:
        sql = """
            SELECT a.*, s.nome AS servico_nome, p.nome AS profissional_nome,
                   c.nome AS cliente_nome, c.telefone AS cliente_telefone,
                   c.email AS cliente_email
            FROM agendamentos a
            JOIN servicos s ON s.id = a.servico_id
            JOIN profissionais p ON p.id = a.profissional_id
            JOIN clientes c ON c.id = a.cliente_id
            WHERE a.id = ?
        """
        parametros = [agendamento_id]
        if cliente_id is not None:
            sql += " AND a.cliente_id = ?"
            parametros.append(cliente_id)
        return conexao.execute(sql, tuple(parametros)).fetchone()


def listar_agendamentos_cliente(cliente_id):
    with obter_conexao() as conexao:
        return conexao.execute(
            """
            SELECT a.*, s.nome AS servico_nome, p.nome AS profissional_nome
            FROM agendamentos a
            JOIN servicos s ON s.id = a.servico_id
            JOIN profissionais p ON p.id = a.profissional_id
            WHERE a.cliente_id = ?
            ORDER BY a.data DESC, a.hora_inicio DESC
            """,
            (cliente_id,),
        ).fetchall()


def pode_cancelar_pelo_cliente(agendamento, agora=None):
    agora = agora or agora_local()
    if not agendamento:
        return False
    if agendamento["status"] not in STATUS_ATIVOS:
        return False

    inicio = combinar_data_hora(
        agendamento["data"], agendamento["hora_inicio"]
    )
    limite = inicio - timedelta(
        minutes=current_app.config["CANCELAMENTO_MINUTOS_ANTECEDENCIA"]
    )
    return agora <= limite


def _cancelar_cliente(conexao, agendamento, motivo, agora):
    if not agendamento:
        raise ValueError("Agendamento não encontrado.")

    if agendamento["status"] not in STATUS_ATIVOS:
        raise ValueError("Este agendamento não pode mais ser cancelado.")

    limite = combinar_data_hora(
        agendamento["data"], agendamento["hora_inicio"]
    ) - timedelta(
        minutes=current_app.config["CANCELAMENTO_MINUTOS_ANTECEDENCIA"]
    )

    if agora > limite:
        raise ValueError(
            "O prazo de cancelamento expirou. Fale com a barbearia."
        )

    reembolso_pendente = agendamento["status_pagamento"] == "pago"
    conexao.execute(
        """
        UPDATE agendamentos
        SET status = 'cancelado',
            cancelado_por = 'cliente',
            motivo_cancelamento = ?,
            status_pagamento = CASE
                WHEN status_pagamento = 'pago' THEN 'reembolso_pendente'
                ELSE status_pagamento
            END,
            reembolso_solicitado_em = CASE
                WHEN status_pagamento = 'pago' THEN ?
                ELSE reembolso_solicitado_em
            END,
            atualizado_em = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            limpar_texto(motivo, 300),
            agora.strftime("%Y-%m-%d %H:%M:%S") if reembolso_pendente else None,
            agendamento["id"],
        ),
    )
    return agendamento["id"], reembolso_pendente


def cancelar_pelo_cliente(
    token,
    cliente_id,
    motivo="Cancelamento solicitado pelo cliente",
    agora=None,
):
    agora = agora or agora_local()

    with obter_conexao(imediata=True) as conexao:
        agendamento = conexao.execute(
            """
            SELECT *
            FROM agendamentos
            WHERE token_hash = ? AND cliente_id = ?
            """,
            (_hash_token(token), cliente_id),
        ).fetchone()

        return _cancelar_cliente(conexao, agendamento, motivo, agora)


def cancelar_pelo_cliente_id(
    agendamento_id,
    cliente_id,
    motivo="Cancelamento solicitado pelo cliente",
    agora=None,
):
    agora = agora or agora_local()

    with obter_conexao(imediata=True) as conexao:
        agendamento = conexao.execute(
            """
            SELECT *
            FROM agendamentos
            WHERE id = ? AND cliente_id = ?
            """,
            (agendamento_id, cliente_id),
        ).fetchone()

        return _cancelar_cliente(conexao, agendamento, motivo, agora)


def listar_agenda(data, profissional_id=None, status=None):
    data = parse_data(data) if isinstance(data, str) else data
    sql = """
        SELECT a.*, s.nome AS servico_nome,
               p.nome AS profissional_nome,
               c.nome AS cliente_nome, c.telefone AS cliente_telefone,
               c.email AS cliente_email, c.origem AS cliente_origem
        FROM agendamentos a
        JOIN servicos s ON s.id = a.servico_id
        JOIN profissionais p ON p.id = a.profissional_id
        JOIN clientes c ON c.id = a.cliente_id
        WHERE a.data = ?
    """
    parametros = [data.isoformat()]

    if profissional_id:
        sql += " AND a.profissional_id = ?"
        parametros.append(profissional_id)
    if status:
        sql += " AND a.status = ?"
        parametros.append(status)

    sql += " ORDER BY a.hora_inicio, p.nome"

    with obter_conexao() as conexao:
        return conexao.execute(sql, tuple(parametros)).fetchall()


def cancelar_pelo_admin(agendamento_id, motivo, agora=None):
    agora = agora or agora_local()
    motivo = limpar_texto(motivo or "Cancelado pela barbearia", 300)

    with obter_conexao(imediata=True) as conexao:
        agendamento = conexao.execute(
            "SELECT * FROM agendamentos WHERE id = ?",
            (agendamento_id,),
        ).fetchone()

        if not agendamento:
            raise ValueError("Agendamento não encontrado.")
        if agendamento["status"] not in STATUS_ATIVOS:
            raise ValueError("Este agendamento não está ativo.")

        reembolso_pendente = agendamento["status_pagamento"] == "pago"
        conexao.execute(
            """
            UPDATE agendamentos
            SET status = 'cancelado',
                cancelado_por = 'admin',
                motivo_cancelamento = ?,
                status_pagamento = CASE
                    WHEN status_pagamento = 'pago' THEN 'reembolso_pendente'
                    ELSE status_pagamento
                END,
                reembolso_solicitado_em = CASE
                    WHEN status_pagamento = 'pago' THEN ?
                    ELSE reembolso_solicitado_em
                END,
                atualizado_em = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                motivo,
                agora.strftime("%Y-%m-%d %H:%M:%S") if reembolso_pendente else None,
                agendamento_id,
            ),
        )
        return reembolso_pendente


def concluir_agendamento(agendamento_id):
    with obter_conexao(imediata=True) as conexao:
        agendamento = conexao.execute(
            "SELECT status FROM agendamentos WHERE id = ?",
            (agendamento_id,),
        ).fetchone()
        if not agendamento:
            raise ValueError("Agendamento não encontrado.")
        if agendamento["status"] != "confirmado":
            raise ValueError("Somente agendamentos confirmados podem ser concluídos.")

        conexao.execute(
            """
            UPDATE agendamentos
            SET status = 'concluido', atualizado_em = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (agendamento_id,),
        )


def confirmar_agendamento(agendamento_id):
    with obter_conexao(imediata=True) as conexao:
        agendamento = conexao.execute(
            "SELECT status FROM agendamentos WHERE id = ?",
            (agendamento_id,),
        ).fetchone()
        if not agendamento:
            raise ValueError("Agendamento não encontrado.")
        if agendamento["status"] != "pendente":
            raise ValueError("Somente agendamentos pendentes podem ser confirmados.")

        conexao.execute(
            """
            UPDATE agendamentos
            SET status = 'confirmado', atualizado_em = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (agendamento_id,),
        )


def atualizar_pagamento(agendamento_id, novo_status, observacao=""):
    if novo_status not in PAGAMENTOS_VALIDOS:
        raise ValueError("Status de pagamento inválido.")

    with obter_conexao(imediata=True) as conexao:
        agendamento = conexao.execute(
            "SELECT id FROM agendamentos WHERE id = ?",
            (agendamento_id,),
        ).fetchone()
        if not agendamento:
            raise ValueError("Agendamento não encontrado.")

        if novo_status == "reembolsado":
            conexao.execute(
                """
                UPDATE agendamentos
                SET status_pagamento = 'reembolsado',
                    reembolsado_em = CURRENT_TIMESTAMP,
                    reembolso_observacao = ?,
                    atualizado_em = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (limpar_texto(observacao, 500), agendamento_id),
            )
        else:
            conexao.execute(
                """
                UPDATE agendamentos
                SET status_pagamento = ?, atualizado_em = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (novo_status, agendamento_id),
            )
