from flask import Blueprint, render_template

from database.db import obter_conexao


public_bp = Blueprint("public", __name__)


@public_bp.route("/")
def inicio():
    with obter_conexao() as conexao:
        servicos = conexao.execute(
            """
            SELECT id, nome, descricao, preco_centavos, duracao_minutos
            FROM servicos
            WHERE ativo = 1
            ORDER BY nome COLLATE NOCASE
            LIMIT 6
            """
        ).fetchall()

        profissionais = conexao.execute(
            """
            SELECT id, nome, apelido, bio
            FROM profissionais
            WHERE ativo = 1
            ORDER BY nome COLLATE NOCASE
            LIMIT 4
            """
        ).fetchall()

    return render_template(
        "publico/index.html",
        servicos=servicos,
        profissionais=profissionais,
    )


@public_bp.route("/privacidade")
def privacidade():
    return render_template("publico/privacidade.html")


@public_bp.route("/politica-cancelamento")
def politica_cancelamento():
    return render_template("publico/politica_cancelamento.html")
