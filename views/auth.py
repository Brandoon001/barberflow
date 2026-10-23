from datetime import datetime

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
from database.db import obter_conexao
from extensions import limiter, oauth
from services.validacao import normalizar_telefone
from views.decorators import cliente_atual, cliente_required, destino_seguro


auth_bp = Blueprint("auth", __name__)


def _limpar_dados_cliente():
    for chave in (
        "cliente_id",
        "oauth_next",
        "pos_cadastro_next",
    ):
        session.pop(chave, None)


def _preservar_admin_e_renovar_sessao():
    admin_id = session.get("administrador_id")
    admin_usuario = session.get("administrador_usuario")
    admin_atividade = session.get("admin_ultima_atividade")

    session.clear()

    if admin_id:
        session["administrador_id"] = admin_id
        session["administrador_usuario"] = admin_usuario
        session["admin_ultima_atividade"] = admin_atividade


def _google_configurado():
    return bool(
        current_app.config.get("GOOGLE_CLIENT_ID")
        and current_app.config.get("GOOGLE_CLIENT_SECRET")
    )


@auth_bp.route("/auth/google")
@limiter.limit("20 per minute")
def login_google():
    if session.get("cliente_id") and cliente_atual():
        return redirect(url_for("booking.minha_conta"))

    if not _google_configurado():
        flash(
            "O login com Google ainda não está configurado. "
            "Defina GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET.",
            "erro",
        )
        return redirect(url_for("public.inicio"))

    session["oauth_next"] = destino_seguro(
        request.args.get("next"), url_for("booking.minha_conta")
    )
    redirect_uri = current_app.config.get("GOOGLE_REDIRECT_URI") or url_for(
        "auth.google_callback", _external=True
    )
    return oauth.google.authorize_redirect(
        redirect_uri,
        prompt="select_account",
    )


@auth_bp.route("/auth/google/callback")
def google_callback():
    if not _google_configurado():
        flash("Login com Google indisponível.", "erro")
        return redirect(url_for("public.inicio"))

    try:
        token = oauth.google.authorize_access_token()
        perfil = token.get("userinfo") or oauth.google.userinfo(token=token)
    except Exception:
        current_app.logger.exception("Falha ao concluir login Google")
        flash("Não foi possível entrar com o Google. Tente novamente.", "erro")
        return redirect(url_for("public.inicio"))

    google_sub = (perfil or {}).get("sub")
    email = (perfil or {}).get("email")
    nome = (perfil or {}).get("name") or (email or "").split("@")[0]
    avatar_url = (perfil or {}).get("picture")
    email_verificado = (perfil or {}).get("email_verified", True)

    if not google_sub or not email or not email_verificado:
        flash("Não foi possível validar sua conta Google.", "erro")
        return redirect(url_for("public.inicio"))

    with obter_conexao(imediata=True) as conexao:
        cliente = conexao.execute(
            "SELECT * FROM clientes WHERE google_sub = ?",
            (google_sub,),
        ).fetchone()

        if cliente and not cliente["ativo"]:
            flash("Esta conta está desativada. Fale com a barbearia.", "erro")
            return redirect(url_for("public.inicio"))

        if cliente:
            conexao.execute(
                """
                UPDATE clientes
                SET nome = ?, email = ?, avatar_url = ?,
                    atualizado_em = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (nome.strip()[:160], email.strip()[:254], avatar_url, cliente["id"]),
            )
            cliente_id = cliente["id"]
        else:
            cursor = conexao.execute(
                """
                INSERT INTO clientes (
                    google_sub, email, nome, avatar_url, origem
                )
                VALUES (?, ?, ?, ?, 'google')
                """,
                (
                    google_sub,
                    email.strip()[:254],
                    nome.strip()[:160],
                    avatar_url,
                ),
            )
            cliente_id = cursor.lastrowid

    proximo = session.get("oauth_next") or url_for("booking.minha_conta")
    proximo = destino_seguro(proximo, url_for("booking.minha_conta"))

    _preservar_admin_e_renovar_sessao()
    session.permanent = True
    session["cliente_id"] = cliente_id

    cliente = cliente_atual()
    if not cliente or not cliente["telefone"]:
        session["pos_cadastro_next"] = proximo
        return redirect(url_for("auth.completar_cadastro"))

    flash(f"Bem-vindo, {cliente['nome'].split()[0]}!", "sucesso")
    return redirect(proximo)


@auth_bp.route("/auth/logout", methods=["POST"])
def logout():
    _limpar_dados_cliente()
    flash("Você saiu da sua conta.", "sucesso")
    return redirect(url_for("public.inicio"))


@auth_bp.route("/cliente/completar-cadastro", methods=["GET", "POST"])
@cliente_required
def completar_cadastro():
    cliente = cliente_atual()

    if request.method == "POST":
        telefone = request.form.get("telefone", "")
        consentimento = request.form.get("consentimento")

        if not consentimento:
            flash(
                "Confirme que aceita ser contatado pela barbearia pelo WhatsApp.",
                "erro",
            )
            return render_template(
                "publico/completar_cadastro.html", cliente=cliente
            )

        try:
            telefone_normalizado = normalizar_telefone(telefone)
        except ValueError as erro:
            flash(str(erro), "erro")
            return render_template(
                "publico/completar_cadastro.html", cliente=cliente
            )

        with obter_conexao() as conexao:
            conexao.execute(
                """
                UPDATE clientes
                SET telefone = ?, telefone_confirmado_em = ?,
                    atualizado_em = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    telefone_normalizado,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    cliente["id"],
                ),
            )

        proximo = session.pop("pos_cadastro_next", None) or url_for(
            "booking.minha_conta"
        )
        flash("WhatsApp confirmado com sucesso.", "sucesso")
        return redirect(destino_seguro(proximo, url_for("booking.minha_conta")))

    return render_template("publico/completar_cadastro.html", cliente=cliente)
