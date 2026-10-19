
from flask import Flask
import os
import secrets

from database.db import obter_conexao
from views.public import public_bp
from views.booking import booking_bp
from views.admin import admin_bp


app = Flask(__name__)

app.config["SECRET_KEY"] = (
    os.environ.get("FLASK_SECRET_KEY")
    or secrets.token_hex(32)
)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


def inicializar_banco():
    with obter_conexao() as conexao:
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS barbearias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                ativo INTEGER NOT NULL DEFAULT 1
            )
        """)

        conexao.execute("""
            CREATE TABLE IF NOT EXISTS administradores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT NOT NULL UNIQUE,
                senha_hash TEXT NOT NULL
            )
        """)


app.register_blueprint(public_bp)
app.register_blueprint(booking_bp)
app.register_blueprint(admin_bp)


@app.route("/status")
def status():
    with obter_conexao() as conexao:
        resultado = conexao.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = ? AND name = ?
            """,
            ("table", "barbearias")
        ).fetchone()

    if resultado:
        return {"aplicacao": "ok", "banco": "ok"}

    return {
        "aplicacao": "ok",
        "banco": "tabela nao encontrada"
    }, 500


if __name__ == "__main__":
    inicializar_banco()
    app.run(debug=True)
