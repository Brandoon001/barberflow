from datetime import timedelta

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from database.db import obter_conexao
from extensions import limiter
from services import agenda
from services.validacao import normalizar_telefone
from views.decorators import cliente_atual, cliente_required


booking_bp = Blueprint("booking", __name__)


def _carregar_opcoes(servico_id=None):
    with obter_conexao() as conexao:
        servicos = conexao.execute(
            """
            SELECT id, nome, descricao, preco_centavos, duracao_minutos
            FROM servicos
            WHERE ativo = 1
            ORDER BY nome COLLATE NOCASE
            """
        ).fetchall()

        profissionais = []
        if servico_id:
            profissionais = conexao.execute(
                """
                SELECT p.id, p.nome, p.apelido, p.bio
                FROM profissionais p
                JOIN profissional_servicos ps ON ps.profissional_id = p.id
                WHERE p.ativo = 1 AND ps.servico_id = ?
                ORDER BY p.nome COLLATE NOCASE
                """,
                (servico_id,),
            ).fetchall()

    return servicos, profissionais


def _exigir_perfil_completo(cliente, proximo):
    if not cliente or not cliente["telefone"]:
        from flask import session

        session["pos_cadastro_next"] = proximo
        return redirect(url_for("auth.completar_cadastro"))
    return None


@booking_bp.route("/agendamento", methods=["GET", "POST"])
@limiter.limit("40 per minute")
@cliente_required
def agendar():
    cliente = cliente_atual()
    redirecionamento = _exigir_perfil_completo(
        cliente, url_for("booking.agendar")
    )
    if redirecionamento:
        return redirecionamento

    valores = request.form if request.method == "POST" else request.args
    servico_id = valores.get("servico_id", type=int)
    profissional_id = valores.get("profissional_id", type=int)
    data_escolhida = (valores.get("data") or "").strip()

    servicos, profissionais = _carregar_opcoes(servico_id)
    horarios = []
    erro_horarios = None

    if servico_id and profissional_id and data_escolhida:
        try:
            horarios = agenda.horarios_disponiveis(
                servico_id, profissional_id, data_escolhida
            )
        except ValueError as erro:
            erro_horarios = str(erro)

    if request.method == "POST":
        hora_inicio = (request.form.get("hora_inicio") or "").strip()
        observacoes = (request.form.get("observacoes") or "").strip()
        consentimento = request.form.get("consentimento")

        if not all(
            [servico_id, profissional_id, data_escolhida, hora_inicio]
        ):
            flash("Escolha serviço, profissional, data e horário.", "erro")
        elif not consentimento:
            flash(
                "Confirme que está ciente da política de cancelamento.",
                "erro",
            )
        else:
            try:
                agendamento_id, token = agenda.criar_agendamento(
                    cliente_id=cliente["id"],
                    servico_id=servico_id,
                    profissional_id=profissional_id,
                    data=data_escolhida,
                    hora_inicio=hora_inicio,
                    observacoes=observacoes,
                    consentimento_em=agenda.agora_local().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                )
            except ValueError as erro:
                flash(str(erro), "erro")
            else:
                flash(
                    "Agendamento realizado! Guarde o link de consulta.",
                    "sucesso",
                )
                return redirect(
                    url_for("booking.consulta", token=token)
                )

        try:
            horarios = agenda.horarios_disponiveis(
                servico_id, profissional_id, data_escolhida
            )
        except (ValueError, TypeError) as erro:
            erro_horarios = str(erro)

    agora = agenda.agora_local()
    return render_template(
        "publico/agendamento.html",
        cliente=cliente,
        servicos=servicos,
        profissionais=profissionais,
        horarios=horarios,
        erro_horarios=erro_horarios,
        servico_id=servico_id,
        profissional_id=profissional_id,
        data_escolhida=data_escolhida,
        hoje=agora.date().isoformat(),
        data_max=(
            agora.date()
            + timedelta(days=current_app.config["AGENDAMENTO_DIAS_FUTUROS"])
        ).isoformat(),
    )


@booking_bp.route("/minha-conta")
@cliente_required
def minha_conta():
    cliente = cliente_atual()
    redirecionamento = _exigir_perfil_completo(
        cliente, url_for("booking.minha_conta")
    )
    if redirecionamento:
        return redirecionamento

    agendamentos = agenda.listar_agendamentos_cliente(cliente["id"])
    agora = agenda.agora_local()
    itens = [
        {
            "agendamento": item,
            "pode_cancelar": agenda.pode_cancelar_pelo_cliente(item, agora),
        }
        for item in agendamentos
    ]

    return render_template(
        "publico/minha_conta.html",
        cliente=cliente,
        itens=itens,
        agora=agora,
    )


@booking_bp.route("/minha-conta/perfil", methods=["GET", "POST"])
@cliente_required
def editar_perfil():
    cliente = cliente_atual()

    if request.method == "POST":
        telefone = request.form.get("telefone", "")
        consentimento = request.form.get("consentimento")

        if not consentimento:
            flash(
                "Confirme que aceita ser contatado pela barbearia pelo WhatsApp.",
                "erro",
            )
        else:
            try:
                telefone_normalizado = normalizar_telefone(telefone)
            except ValueError as erro:
                flash(str(erro), "erro")
            else:
                agora = agenda.agora_local().strftime("%Y-%m-%d %H:%M:%S")
                with obter_conexao(imediata=True) as conexao:
                    conexao.execute(
                        """
                        UPDATE clientes
                        SET telefone = ?, telefone_confirmado_em = ?,
                            telefone_informado_em = ?, consentimento_em = ?,
                            consentimento_versao = ?,
                            atualizado_em = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (
                            telefone_normalizado,
                            agora,
                            agora,
                            agora,
                            current_app.config.get(
                                "CONSENTIMENTO_VERSAO", "2026-10"
                            ),
                            cliente["id"],
                        ),
                    )

                flash("WhatsApp atualizado com sucesso.", "sucesso")
                return redirect(url_for("booking.minha_conta"))

    return render_template("publico/perfil.html", cliente=cliente)


@booking_bp.route("/agendamento/consulta/<token>")
@cliente_required
def consulta(token):
    cliente = cliente_atual()
    redirecionamento = _exigir_perfil_completo(
        cliente, url_for("booking.consulta", token=token)
    )
    if redirecionamento:
        return redirecionamento

    agendamento = agenda.buscar_por_token(token, cliente_id=cliente["id"])
    if not agendamento:
        abort(404)

    agora = agenda.agora_local()
    return render_template(
        "publico/consulta.html",
        cliente=cliente,
        agendamento=agendamento,
        pode_cancelar=agenda.pode_cancelar_pelo_cliente(
            agendamento, agora
        ),
        cancelar_url=url_for("booking.cancelar", token=token),
        agora=agora,
    )


@booking_bp.route(
    "/agendamento/consulta/<token>/cancelar",
    methods=["POST"],
)
@limiter.limit("10 per minute")
@cliente_required
def cancelar(token):
    cliente = cliente_atual()
    motivo = (request.form.get("motivo") or "").strip()

    try:
        _id, reembolso_pendente = agenda.cancelar_pelo_cliente(
            token=token,
            cliente_id=cliente["id"],
            motivo=motivo or "Cancelamento solicitado pelo cliente",
        )
    except ValueError as erro:
        flash(str(erro), "erro")
    else:
        if reembolso_pendente:
            flash(
                "Agendamento cancelado. O reembolso ficou pendente e será "
                "tratado diretamente pela barbearia.",
                "sucesso",
            )
        else:
            flash("Agendamento cancelado com sucesso.", "sucesso")

    return redirect(url_for("booking.consulta", token=token))


@booking_bp.route(
    "/minha-conta/agendamento/<int:agendamento_id>",
)
@cliente_required
def detalhe_conta(agendamento_id):
    cliente = cliente_atual()
    agendamento = agenda.buscar_por_id(
        agendamento_id, cliente_id=cliente["id"]
    )
    if not agendamento:
        abort(404)

    agora = agenda.agora_local()
    return render_template(
        "publico/consulta.html",
        cliente=cliente,
        agendamento=agendamento,
        pode_cancelar=agenda.pode_cancelar_pelo_cliente(
            agendamento, agora
        ),
        cancelar_url=url_for(
            "booking.cancelar_conta", agendamento_id=agendamento_id
        ),
        agora=agora,
    )


@booking_bp.route(
    "/minha-conta/agendamento/<int:agendamento_id>/cancelar",
    methods=["POST"],
)
@limiter.limit("10 per minute")
@cliente_required
def cancelar_conta(agendamento_id):
    cliente = cliente_atual()
    motivo = (request.form.get("motivo") or "").strip()

    try:
        _id, reembolso_pendente = agenda.cancelar_pelo_cliente_id(
            agendamento_id=agendamento_id,
            cliente_id=cliente["id"],
            motivo=motivo or "Cancelamento solicitado pelo cliente",
        )
    except ValueError as erro:
        flash(str(erro), "erro")
    else:
        if reembolso_pendente:
            flash(
                "Agendamento cancelado. O reembolso ficou pendente e será "
                "tratado diretamente pela barbearia.",
                "sucesso",
            )
        else:
            flash("Agendamento cancelado com sucesso.", "sucesso")

    return redirect(
        url_for("booking.detalhe_conta", agendamento_id=agendamento_id)
    )
