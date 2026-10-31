from datetime import datetime
from functools import wraps

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from database.db import obter_conexao
from extensions import limiter
from services import agenda
from services.validacao import (
    limpar_texto,
    normalizar_telefone,
    parse_hora,
    parse_preco_centavos,
)
from views.decorators import destino_seguro, mensagem_erro


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

DIAS_SEMANA = [
    "Segunda",
    "Terça",
    "Quarta",
    "Quinta",
    "Sexta",
    "Sábado",
    "Domingo",
]


def _limpar_admin():
    for chave in (
        "administrador_id",
        "administrador_usuario",
        "admin_ultima_atividade",
    ):
        session.pop(chave, None)


def login_required(funcao):
    @wraps(funcao)
    def verificar_login(*args, **kwargs):
        administrador_id = session.get("administrador_id")
        if not administrador_id:
            flash("Faça login para acessar o painel.", "erro")
            return redirect(
                url_for("admin.login", next=request.full_path)
            )

        ultima = session.get("admin_ultima_atividade")
        if ultima:
            try:
                ultima_dt = datetime.fromisoformat(ultima)
            except ValueError:
                ultima_dt = None
            if ultima_dt and (
                datetime.now() - ultima_dt
            ).total_seconds() > current_app.config["ADMIN_SESSAO_MINUTOS"] * 60:
                _limpar_admin()
                flash("Sua sessão expirou. Entre novamente.", "erro")
                return redirect(
                    url_for("admin.login", next=request.full_path)
                )

        with obter_conexao() as conexao:
            administrador = conexao.execute(
                """
                SELECT id, usuario
                FROM administradores
                WHERE id = ?
                """,
                (administrador_id,),
            ).fetchone()

        if not administrador:
            _limpar_admin()
            flash("Sessão inválida. Entre novamente.", "erro")
            return redirect(url_for("admin.login"))

        session["admin_ultima_atividade"] = datetime.now().isoformat()
        return funcao(*args, **kwargs)

    return verificar_login


@admin_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    if session.get("administrador_id"):
        return redirect(url_for("admin.painel"))

    erro = None

    if request.method == "POST":
        usuario = (request.form.get("usuario") or "").strip()
        senha = request.form.get("senha") or ""

        with obter_conexao() as conexao:
            administrador = conexao.execute(
                """
                SELECT id, usuario, senha_hash
                FROM administradores
                WHERE usuario = ?
                """,
                (usuario,),
            ).fetchone()

        if administrador and check_password_hash(
            administrador["senha_hash"], senha
        ):
            cliente_id = session.get("cliente_id")
            pos_cadastro = session.get("pos_cadastro_next")
            session.clear()

            if cliente_id:
                session["cliente_id"] = cliente_id
            if pos_cadastro:
                session["pos_cadastro_next"] = pos_cadastro

            session.permanent = True
            session["administrador_id"] = administrador["id"]
            session["administrador_usuario"] = administrador["usuario"]
            session["admin_ultima_atividade"] = datetime.now().isoformat()
            flash("Login realizado com sucesso.", "sucesso")

            proximo = destino_seguro(
                request.args.get("next"), url_for("admin.painel")
            )
            return redirect(proximo)

        erro = "Usuário ou senha inválidos."

    return render_template("admin/login.html", erro=erro)


@admin_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    _limpar_admin()
    flash("Você saiu do painel administrativo.", "sucesso")
    return redirect(url_for("admin.login"))


@admin_bp.route("/")
@login_required
def painel():
    hoje = datetime.now().strftime("%Y-%m-%d")

    with obter_conexao() as conexao:
        resumo = {
            "hoje": conexao.execute(
                """
                SELECT COUNT(*) AS total
                FROM agendamentos
                WHERE data = ? AND status IN ('pendente', 'confirmado')
                """,
                (hoje,),
            ).fetchone()["total"],
            "pendentes": conexao.execute(
                """
                SELECT COUNT(*) AS total
                FROM agendamentos
                WHERE status = 'pendente'
                """
            ).fetchone()["total"],
            "reembolsos": conexao.execute(
                """
                SELECT COUNT(*) AS total
                FROM agendamentos
                WHERE status_pagamento = 'reembolso_pendente'
                """
            ).fetchone()["total"],
            "servicos": conexao.execute(
                "SELECT COUNT(*) AS total FROM servicos WHERE ativo = 1"
            ).fetchone()["total"],
            "profissionais": conexao.execute(
                "SELECT COUNT(*) AS total FROM profissionais WHERE ativo = 1"
            ).fetchone()["total"],
            "clientes": conexao.execute(
                "SELECT COUNT(*) AS total FROM clientes WHERE ativo = 1"
            ).fetchone()["total"],
        }

        proximos = conexao.execute(
            """
            SELECT a.*, s.nome AS servico_nome,
                   p.nome AS profissional_nome, c.nome AS cliente_nome
            FROM agendamentos a
            JOIN servicos s ON s.id = a.servico_id
            JOIN profissionais p ON p.id = a.profissional_id
            JOIN clientes c ON c.id = a.cliente_id
            WHERE a.status IN ('pendente', 'confirmado')
              AND a.data >= ?
            ORDER BY a.data, a.hora_inicio
            LIMIT 6
            """,
            (hoje,),
        ).fetchall()

    return render_template(
        "admin/painel.html",
        resumo=resumo,
        proximos=proximos,
        hoje=hoje,
    )


def _dados_servico():
    nome = (request.form.get("nome") or "").strip()
    descricao = (request.form.get("descricao") or "").strip()
    preco = request.form.get("preco") or ""
    duracao = request.form.get("duracao") or ""

    if not nome:
        raise ValueError("O nome do serviço é obrigatório.")
    if len(nome) > 120:
        raise ValueError("O nome deve ter no máximo 120 caracteres.")
    if len(descricao) > 1000:
        raise ValueError("A descrição deve ter no máximo 1000 caracteres.")

    try:
        duracao_minutos = int(duracao)
    except ValueError as erro:
        raise ValueError("Duração inválida.") from erro

    if duracao_minutos <= 0:
        raise ValueError("A duração deve ser maior que zero.")
    if duracao_minutos > 600:
        raise ValueError("A duração deve ser de no máximo 600 minutos.")

    return {
        "nome": nome,
        "descricao": descricao,
        "preco_centavos": parse_preco_centavos(preco),
        "duracao_minutos": duracao_minutos,
    }


@admin_bp.route("/servicos", methods=["GET", "POST"])
@login_required
def servicos():
    if request.method == "POST":
        try:
            dados = _dados_servico()
            with obter_conexao() as conexao:
                conexao.execute(
                    """
                    INSERT INTO servicos (
                        nome, descricao, preco_centavos,
                        duracao_minutos, ativo
                    )
                    VALUES (?, ?, ?, ?, 1)
                    """,
                    (
                        dados["nome"],
                        dados["descricao"],
                        dados["preco_centavos"],
                        dados["duracao_minutos"],
                    ),
                )
        except ValueError as erro:
            flash(str(erro), "erro")
        else:
            flash("Serviço cadastrado com sucesso.", "sucesso")
            return redirect(url_for("admin.servicos"))

    with obter_conexao() as conexao:
        lista_servicos = conexao.execute(
            """
            SELECT id, nome, descricao, preco_centavos,
                   duracao_minutos, ativo
            FROM servicos
            ORDER BY nome COLLATE NOCASE
            """
        ).fetchall()

    return render_template("admin/servicos.html", servicos=lista_servicos)


@admin_bp.route("/servicos/<int:servico_id>/editar", methods=["GET", "POST"])
@login_required
def editar_servico(servico_id):
    with obter_conexao() as conexao:
        servico = conexao.execute(
            "SELECT * FROM servicos WHERE id = ?",
            (servico_id,),
        ).fetchone()

    if not servico:
        flash("Serviço não encontrado.", "erro")
        return redirect(url_for("admin.servicos"))

    if request.method == "POST":
        try:
            dados = _dados_servico()
            ativo = 1 if request.form.get("ativo") else 0
            with obter_conexao() as conexao:
                conexao.execute(
                    """
                    UPDATE servicos
                    SET nome = ?, descricao = ?, preco_centavos = ?,
                        duracao_minutos = ?, ativo = ?
                    WHERE id = ?
                    """,
                    (
                        dados["nome"],
                        dados["descricao"],
                        dados["preco_centavos"],
                        dados["duracao_minutos"],
                        ativo,
                        servico_id,
                    ),
                )
        except ValueError as erro:
            flash(str(erro), "erro")
        else:
            flash("Serviço atualizado com sucesso.", "sucesso")
            return redirect(url_for("admin.servicos"))

    return render_template("admin/servico_form.html", servico=servico)


@admin_bp.route("/servicos/<int:servico_id>/situacao", methods=["POST"])
@login_required
def situacao_servico(servico_id):
    with obter_conexao() as conexao:
        servico = conexao.execute(
            "SELECT ativo FROM servicos WHERE id = ?",
            (servico_id,),
        ).fetchone()
        if not servico:
            flash("Serviço não encontrado.", "erro")
            return redirect(url_for("admin.servicos"))

        conexao.execute(
            """
            UPDATE servicos
            SET ativo = ?
            WHERE id = ?
            """,
            (0 if servico["ativo"] else 1, servico_id),
        )

    flash("Situação do serviço atualizada.", "sucesso")
    return redirect(url_for("admin.servicos"))


def _lista_ids_servicos():
    ids = []
    for valor in request.form.getlist("servicos"):
        try:
            ids.append(int(valor))
        except ValueError:
            continue
    return ids


def _salvar_servicos_profissional(conexao, profissional_id, ids_servicos):
    conexao.execute(
        "DELETE FROM profissional_servicos WHERE profissional_id = ?",
        (profissional_id,),
    )
    for servico_id in sorted(set(ids_servicos)):
        conexao.execute(
            """
            INSERT INTO profissional_servicos (profissional_id, servico_id)
            VALUES (?, ?)
            """,
            (profissional_id, servico_id),
        )


def _dados_profissional():
    nome = (request.form.get("nome") or "").strip()
    apelido = (request.form.get("apelido") or "").strip()
    bio = (request.form.get("bio") or "").strip()

    if not nome:
        raise ValueError("O nome do profissional é obrigatório.")
    if len(nome) > 120:
        raise ValueError("O nome deve ter no máximo 120 caracteres.")
    if len(apelido) > 60:
        raise ValueError("O apelido deve ter no máximo 60 caracteres.")
    if len(bio) > 500:
        raise ValueError("A bio deve ter no máximo 500 caracteres.")

    return {"nome": nome, "apelido": apelido, "bio": bio}


@admin_bp.route("/profissionais", methods=["GET", "POST"])
@login_required
def profissionais():
    if request.method == "POST":
        try:
            dados = _dados_profissional()
            ids_servicos = _lista_ids_servicos()
            with obter_conexao(imediata=True) as conexao:
                cursor = conexao.execute(
                    """
                    INSERT INTO profissionais (nome, apelido, bio, ativo)
                    VALUES (?, ?, ?, 1)
                    """,
                    (dados["nome"], dados["apelido"], dados["bio"]),
                )
                _salvar_servicos_profissional(
                    conexao, cursor.lastrowid, ids_servicos
                )
        except ValueError as erro:
            flash(str(erro), "erro")
        else:
            flash("Profissional cadastrado com sucesso.", "sucesso")
            return redirect(url_for("admin.profissionais"))

    with obter_conexao() as conexao:
        lista_profissionais = conexao.execute(
            """
            SELECT p.*, COUNT(ps.servico_id) AS total_servicos
            FROM profissionais p
            LEFT JOIN profissional_servicos ps
                ON ps.profissional_id = p.id
            GROUP BY p.id
            ORDER BY p.nome COLLATE NOCASE
            """
        ).fetchall()
        lista_servicos = conexao.execute(
            "SELECT id, nome FROM servicos ORDER BY nome COLLATE NOCASE"
        ).fetchall()

    return render_template(
        "admin/profissionais.html",
        profissionais=lista_profissionais,
        servicos=lista_servicos,
    )


@admin_bp.route(
    "/profissionais/<int:profissional_id>/editar",
    methods=["GET", "POST"],
)
@login_required
def editar_profissional(profissional_id):
    with obter_conexao() as conexao:
        profissional = conexao.execute(
            "SELECT * FROM profissionais WHERE id = ?",
            (profissional_id,),
        ).fetchone()

    if not profissional:
        flash("Profissional não encontrado.", "erro")
        return redirect(url_for("admin.profissionais"))

    if request.method == "POST":
        try:
            dados = _dados_profissional()
            ids_servicos = _lista_ids_servicos()
            ativo = 1 if request.form.get("ativo") else 0
            with obter_conexao(imediata=True) as conexao:
                conexao.execute(
                    """
                    UPDATE profissionais
                    SET nome = ?, apelido = ?, bio = ?, ativo = ?,
                        atualizado_em = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        dados["nome"],
                        dados["apelido"],
                        dados["bio"],
                        ativo,
                        profissional_id,
                    ),
                )
                _salvar_servicos_profissional(
                    conexao, profissional_id, ids_servicos
                )
        except ValueError as erro:
            flash(str(erro), "erro")
        else:
            flash("Profissional atualizado com sucesso.", "sucesso")
            return redirect(url_for("admin.profissionais"))

    with obter_conexao() as conexao:
        profissional = conexao.execute(
            "SELECT * FROM profissionais WHERE id = ?",
            (profissional_id,),
        ).fetchone()
        lista_servicos = conexao.execute(
            "SELECT id, nome FROM servicos ORDER BY nome COLLATE NOCASE"
        ).fetchall()
        selecionados = {
            linha["servico_id"]
            for linha in conexao.execute(
                """
                SELECT servico_id
                FROM profissional_servicos
                WHERE profissional_id = ?
                """,
                (profissional_id,),
            ).fetchall()
        }

    return render_template(
        "admin/profissional_form.html",
        profissional=profissional,
        servicos=lista_servicos,
        selecionados=selecionados,
    )


@admin_bp.route(
    "/profissionais/<int:profissional_id>/situacao",
    methods=["POST"],
)
@login_required
def situacao_profissional(profissional_id):
    with obter_conexao() as conexao:
        profissional = conexao.execute(
            "SELECT ativo FROM profissionais WHERE id = ?",
            (profissional_id,),
        ).fetchone()
        if not profissional:
            flash("Profissional não encontrado.", "erro")
            return redirect(url_for("admin.profissionais"))

        conexao.execute(
            """
            UPDATE profissionais
            SET ativo = ?, atualizado_em = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (0 if profissional["ativo"] else 1, profissional_id),
        )

    flash("Situação do profissional atualizada.", "sucesso")
    return redirect(url_for("admin.profissionais"))


@admin_bp.route(
    "/profissionais/<int:profissional_id>/horarios",
    methods=["GET", "POST"],
)
@login_required
def horarios_profissional(profissional_id):
    with obter_conexao() as conexao:
        profissional = conexao.execute(
            "SELECT * FROM profissionais WHERE id = ?",
            (profissional_id,),
        ).fetchone()

    if not profissional:
        flash("Profissional não encontrado.", "erro")
        return redirect(url_for("admin.profissionais"))

    if request.method == "POST":
        try:
            blocos = []
            for dia in range(7):
                for turno in range(2):
                    inicio = (
                        request.form.get(f"inicio_{dia}_{turno}") or ""
                    ).strip()
                    fim = (
                        request.form.get(f"fim_{dia}_{turno}") or ""
                    ).strip()

                    if not inicio and not fim:
                        continue
                    if not inicio or not fim:
                        raise ValueError(
                            "Preencha início e fim de cada turno."
                        )

                    hora_inicio = parse_hora(inicio)
                    hora_fim = parse_hora(fim)
                    if hora_inicio >= hora_fim:
                        raise ValueError(
                            "O início do turno deve ser antes do fim."
                        )

                    blocos.append(
                        (dia, hora_inicio.strftime("%H:%M"), hora_fim.strftime("%H:%M"))
                    )

            for dia in range(7):
                turnos_dia = sorted(
                    [bloco for bloco in blocos if bloco[0] == dia],
                    key=lambda item: item[1],
                )
                for anterior, atual in zip(turnos_dia, turnos_dia[1:]):
                    if atual[1] < anterior[2]:
                        raise ValueError(
                            "Existem turnos sobrepostos no mesmo dia."
                        )

            with obter_conexao(imediata=True) as conexao:
                conexao.execute(
                    """
                    DELETE FROM horarios_trabalho
                    WHERE profissional_id = ?
                    """,
                    (profissional_id,),
                )
                for dia, inicio, fim in blocos:
                    conexao.execute(
                        """
                        INSERT INTO horarios_trabalho (
                            profissional_id, dia_semana, hora_inicio, hora_fim
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (profissional_id, dia, inicio, fim),
                    )
        except ValueError as erro:
            flash(str(erro), "erro")
        else:
            flash("Horários atualizados com sucesso.", "sucesso")
            return redirect(
                url_for(
                    "admin.horarios_profissional",
                    profissional_id=profissional_id,
                )
            )

    with obter_conexao() as conexao:
        registros = conexao.execute(
            """
            SELECT dia_semana, hora_inicio, hora_fim
            FROM horarios_trabalho
            WHERE profissional_id = ?
            ORDER BY dia_semana, hora_inicio
            """,
            (profissional_id,),
        ).fetchall()

    horarios_por_dia = {dia: [] for dia in range(7)}
    for registro in registros:
        horarios_por_dia[registro["dia_semana"]].append(registro)

    return render_template(
        "admin/horarios.html",
        profissional=profissional,
        dias=DIAS_SEMANA,
        horarios_por_dia=horarios_por_dia,
    )


@admin_bp.route("/clientes", methods=["GET"])
@login_required
def clientes():
    busca = (request.args.get("q") or "").strip()
    sql = """
        SELECT c.*,
               (SELECT COUNT(*) FROM agendamentos a
                WHERE a.cliente_id = c.id) AS total_agendamentos,
               (SELECT COUNT(*) FROM clientes m
                WHERE m.origem = 'manual'
                  AND m.ativo = 1
                  AND c.origem = 'google'
                  AND m.telefone IS NOT NULL
                  AND m.telefone = c.telefone) AS manuais_com_mesmo_telefone
        FROM clientes c
        WHERE 1 = 1
    """
    parametros = []

    if busca:
        sql += """
            AND (
                c.nome LIKE ? OR c.telefone LIKE ? OR c.email LIKE ?
            )
        """
        termo = f"%{busca}%"
        parametros.extend([termo, termo, termo])

    sql += " ORDER BY c.nome COLLATE NOCASE"

    with obter_conexao() as conexao:
        lista_clientes = conexao.execute(sql, tuple(parametros)).fetchall()

    return render_template(
        "admin/clientes.html",
        clientes=lista_clientes,
        busca=busca,
    )


@admin_bp.route("/clientes/novo", methods=["GET", "POST"])
@login_required
def novo_cliente():
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        telefone = request.form.get("telefone") or ""

        try:
            if not nome:
                raise ValueError("O nome do cliente é obrigatório.")
            if len(nome) > 160:
                raise ValueError("O nome deve ter no máximo 160 caracteres.")
            telefone = normalizar_telefone(telefone)

            with obter_conexao(imediata=True) as conexao:
                existente = conexao.execute(
                    "SELECT id FROM clientes WHERE telefone = ? AND ativo = 1",
                    (telefone,),
                ).fetchone()
                if existente:
                    raise ValueError(
                        "Já existe um cliente ativo com esse WhatsApp. "
                        "Use o vínculo de cadastros."
                    )

                agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                conexao.execute(
                    """
                    INSERT INTO clientes (
                        nome, telefone, origem, telefone_confirmado_em,
                        telefone_informado_em
                    )
                    VALUES (?, ?, 'manual', ?, ?)
                    """,
                    (nome, telefone, agora, agora),
                )
        except ValueError as erro:
            flash(str(erro), "erro")
        else:
            flash("Cliente cadastrado com sucesso.", "sucesso")
            return redirect(url_for("admin.clientes"))

    return render_template("admin/cliente_form.html", cliente=None)


@admin_bp.route(
    "/clientes/<int:cliente_id>/editar",
    methods=["GET", "POST"],
)
@login_required
def editar_cliente(cliente_id):
    with obter_conexao() as conexao:
        cliente = conexao.execute(
            "SELECT * FROM clientes WHERE id = ?",
            (cliente_id,),
        ).fetchone()

    if not cliente:
        flash("Cliente não encontrado.", "erro")
        return redirect(url_for("admin.clientes"))

    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        telefone = request.form.get("telefone") or ""
        ativo = 1 if request.form.get("ativo") else 0

        try:
            if not nome:
                raise ValueError("O nome do cliente é obrigatório.")
            if len(nome) > 160:
                raise ValueError("O nome deve ter no máximo 160 caracteres.")
            telefone = normalizar_telefone(telefone)

            with obter_conexao(imediata=True) as conexao:
                existente = conexao.execute(
                    """
                    SELECT id FROM clientes
                    WHERE telefone = ? AND ativo = 1 AND id <> ?
                    """,
                    (telefone, cliente_id),
                ).fetchone()
                if existente:
                    raise ValueError(
                        "Já existe outro cliente ativo com esse WhatsApp."
                    )

                agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                conexao.execute(
                    """
                    UPDATE clientes
                    SET nome = ?, telefone = ?, ativo = ?,
                        telefone_informado_em = CASE
                            WHEN telefone IS NOT ? THEN ?
                            ELSE telefone_informado_em
                        END,
                        atualizado_em = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (nome, telefone, ativo, telefone, agora, cliente_id),
                )
        except ValueError as erro:
            flash(str(erro), "erro")
        else:
            flash("Cliente atualizado com sucesso.", "sucesso")
            return redirect(url_for("admin.clientes"))

    with obter_conexao() as conexao:
        cliente = conexao.execute(
            "SELECT * FROM clientes WHERE id = ?",
            (cliente_id,),
        ).fetchone()

    return render_template("admin/cliente_form.html", cliente=cliente)


@admin_bp.route(
    "/clientes/<int:cliente_id>/vincular",
    methods=["GET", "POST"],
)
@login_required
def vincular_cliente(cliente_id):
    with obter_conexao() as conexao:
        cliente = conexao.execute(
            "SELECT * FROM clientes WHERE id = ?",
            (cliente_id,),
        ).fetchone()

    if not cliente:
        flash("Cliente não encontrado.", "erro")
        return redirect(url_for("admin.clientes"))

    if cliente["origem"] != "manual":
        flash("Somente cadastros manuais podem ser vinculados.", "erro")
        return redirect(url_for("admin.clientes"))

    if request.method == "POST":
        try:
            principal_id = int(request.form.get("principal_id") or 0)
        except ValueError:
            flash("Selecione uma conta Google válida.", "erro")
        else:
            with obter_conexao(imediata=True) as conexao:
                principal = conexao.execute(
                    """
                    SELECT id, nome, origem, ativo
                    FROM clientes
                    WHERE id = ?
                    """,
                    (principal_id,),
                ).fetchone()

                if (
                    not principal
                    or not principal["ativo"]
                    or principal["origem"] != "google"
                ):
                    flash("Selecione uma conta Google válida.", "erro")
                elif principal_id == cliente_id:
                    flash("Escolha uma conta diferente.", "erro")
                else:
                    conexao.execute(
                        """
                        UPDATE agendamentos
                        SET cliente_id = ?
                        WHERE cliente_id = ?
                        """,
                        (principal_id, cliente_id),
                    )
                    conexao.execute(
                        """
                        UPDATE clientes
                        SET cliente_principal_id = ?, ativo = 0,
                            atualizado_em = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (principal_id, cliente_id),
                    )
                    flash(
                        "Cadastros vinculados e agendamentos transferidos.",
                        "sucesso",
                    )
                    return redirect(
                        url_for(
                            "admin.editar_cliente",
                            cliente_id=principal_id,
                        )
                    )

    with obter_conexao() as conexao:
        candidatos = conexao.execute(
            """
            SELECT id, nome, email, telefone
            FROM clientes
            WHERE origem = 'google' AND ativo = 1 AND id <> ?
            ORDER BY nome COLLATE NOCASE
            """,
            (cliente_id,),
        ).fetchall()

    return render_template(
        "admin/cliente_vincular.html",
        cliente=cliente,
        candidatos=candidatos,
    )


def _voltar_agenda():
    return destino_seguro(
        request.form.get("voltar"),
        url_for("admin.agenda_admin", data=datetime.now().strftime("%Y-%m-%d")),
    )


@admin_bp.route("/agenda")
@login_required
def agenda_admin():
    data_texto = (request.args.get("data") or "").strip()
    try:
        data = datetime.strptime(data_texto, "%Y-%m-%d").date()
    except ValueError:
        data = datetime.now().date()

    profissional_id = request.args.get("profissional_id", type=int)
    status = (request.args.get("status") or "").strip()
    if status not in agenda.STATUS_VALIDOS:
        status = None

    with obter_conexao() as conexao:
        profissionais = conexao.execute(
            """
            SELECT id, nome
            FROM profissionais
            ORDER BY nome COLLATE NOCASE
            """
        ).fetchall()

    itens = agenda.listar_agenda(data, profissional_id, status)

    return render_template(
        "admin/agenda.html",
        itens=itens,
        data=data,
        profissionais=profissionais,
        profissional_id=profissional_id,
        status=status,
        hoje=datetime.now().date(),
    )


@admin_bp.route("/agenda/<int:agendamento_id>/confirmar", methods=["POST"])
@login_required
def confirmar_agendamento(agendamento_id):
    try:
        agenda.confirmar_agendamento(agendamento_id)
    except ValueError as erro:
        flash(str(erro), "erro")
    else:
        flash("Agendamento confirmado.", "sucesso")
    return redirect(_voltar_agenda())


@admin_bp.route("/agenda/<int:agendamento_id>/concluir", methods=["POST"])
@login_required
def concluir_agendamento(agendamento_id):
    try:
        agenda.concluir_agendamento(agendamento_id)
    except ValueError as erro:
        flash(str(erro), "erro")
    else:
        flash("Agendamento concluído.", "sucesso")
    return redirect(_voltar_agenda())


@admin_bp.route("/agenda/<int:agendamento_id>/cancelar", methods=["POST"])
@login_required
def cancelar_agendamento(agendamento_id):
    motivo = (request.form.get("motivo") or "").strip()
    try:
        reembolso = agenda.cancelar_pelo_admin(
            agendamento_id,
            motivo or "Cancelado pela barbearia",
        )
    except ValueError as erro:
        flash(str(erro), "erro")
    else:
        if reembolso:
            flash(
                "Agendamento cancelado. Reembolso marcado como pendente.",
                "sucesso",
            )
        else:
            flash("Agendamento cancelado.", "sucesso")
    return redirect(_voltar_agenda())


@admin_bp.route("/agenda/<int:agendamento_id>/pagamento", methods=["POST"])
@login_required
def pagamento_agendamento(agendamento_id):
    novo_status = (request.form.get("status_pagamento") or "").strip()
    observacao = (request.form.get("observacao") or "").strip()

    try:
        agenda.atualizar_pagamento(
            agendamento_id, novo_status, observacao
        )
    except ValueError as erro:
        flash(mensagem_erro(erro), "erro")
    else:
        flash("Pagamento atualizado.", "sucesso")
    return redirect(_voltar_agenda())


@admin_bp.route("/agenda/<int:agendamento_id>/reembolso", methods=["POST"])
@login_required
def reembolso_agendamento(agendamento_id):
    observacao = (request.form.get("observacao") or "").strip()

    try:
        agenda.atualizar_pagamento(
            agendamento_id, "reembolsado", observacao
        )
    except ValueError as erro:
        flash(mensagem_erro(erro), "erro")
    else:
        flash("Reembolso registrado como concluído.", "sucesso")
    return redirect(_voltar_agenda())
