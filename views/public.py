from urllib.parse import quote_plus

from flask import Blueprint, current_app, render_template

from database.db import obter_conexao


public_bp = Blueprint("public", __name__)


def _mapa_da_barbearia():
    endereco = (current_app.config["MARCA"].get("endereco") or "").strip()
    embed_url = (current_app.config.get("MAPA_EMBED_URL") or "").strip()
    link = (current_app.config.get("MAPA_LINK") or "").strip()

    if endereco:
        if not embed_url:
            embed_url = (
                "https://www.google.com/maps?q="
                f"{quote_plus(endereco)}&output=embed"
            )
        if not link:
            link = (
                "https://www.google.com/maps/search/?api=1&query="
                f"{quote_plus(endereco)}"
            )

    return {
        "endereco": endereco,
        "embed_url": embed_url,
        "link": link,
    }


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
        mapa=_mapa_da_barbearia(),
    )


@public_bp.route("/privacidade")
def privacidade():
    return render_template("publico/privacidade.html")


@public_bp.route("/politica-cancelamento")
def politica_cancelamento():
    return render_template("publico/politica_cancelamento.html")
