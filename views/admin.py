
from functools import wraps

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    current_app,
)
from werkzeug.security import check_password_hash

from database.db import obter_conexao

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def login_required(funcao):
    @wraps(funcao)
    def verificar_login(*args, **kwargs):
        if "administrador_id" not in session:
            return redirect(url_for("admin.login"))

        return funcao(*args, **kwargs)

    return verificar_login


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if "administrador_id" in session:
        return redirect(url_for("admin.painel"))

    erro = None

    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "")

        with obter_conexao() as conexao:
            administrador = conexao.execute(
                """
                SELECT id, usuario, senha_hash
                FROM administradores
                WHERE usuario = ?
                """,
                (usuario,),
            ).fetchone()

        if (
            administrador
            and check_password_hash(
                administrador["senha_hash"], senha
            )
        ):
            session.clear()
            session["administrador_id"] = administrador["id"]
            session["administrador_usuario"] = administrador["usuario"]

            return redirect(url_for("admin.painel"))

        erro = "Usuário ou senha inválidos."

    return render_template("admin_login.html", erro=erro)


@admin_bp.route("/")
@login_required
def painel():
    return render_template("admin.html")


@admin_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    return redirect(url_for("admin.login"))
