import os
from datetime import datetime
from urllib.parse import quote

import click
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash

from config import Config, obter_config
from database.db import inicializar_banco, obter_conexao
from extensions import csrf, limiter, oauth
from services.validacao import (
    formatar_preco_centavos,
    formatar_telefone,
    telefone_whatsapp,
)


load_dotenv()


def _validar_configuracao_producao(app):
    if app.config.get("ENV") != "production":
        return

    erros = []
    secret_key = app.config.get("SECRET_KEY") or ""
    if len(secret_key) < 32 or secret_key.startswith(("dev-", "troque-")):
        erros.append(
            "SECRET_KEY deve ser longa, aleatória e diferente do valor de exemplo."
        )

    if not app.config.get("GOOGLE_CLIENT_ID") or not app.config.get(
        "GOOGLE_CLIENT_SECRET"
    ):
        erros.append(
            "GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET são obrigatórios."
        )

    redirect_uri = app.config.get("GOOGLE_REDIRECT_URI") or ""
    if (
        not redirect_uri.startswith("https://")
        or "localhost" in redirect_uri
        or "127.0.0.1" in redirect_uri
    ):
        erros.append(
            "GOOGLE_REDIRECT_URI deve ser uma URL HTTPS pública de produção."
        )

    if not app.config.get("SESSION_COOKIE_SECURE"):
        erros.append("SESSION_COOKIE_SECURE deve ser true em produção.")

    database_path = app.config.get("DATABASE_PATH") or ""
    if not os.path.isabs(database_path):
        erros.append("DATABASE_PATH deve ser um caminho absoluto em produção.")

    if erros:
        raise RuntimeError(
            "Configuração de produção inválida:\n- " + "\n- ".join(erros)
        )

    if app.config.get("RATELIMIT_STORAGE_URI") == "memory://":
        app.logger.warning(
            "RATELIMIT_STORAGE_URI está em memória. Use um único worker "
            "Gunicorn ou configure um backend compartilhado."
        )


def create_app(config_object=None):
    app = Flask(__name__, instance_relative_config=True)

    if config_object is None:
        app.config.from_object(obter_config())
    elif isinstance(config_object, dict):
        app.config.from_object(obter_config())
        app.config.update(config_object)
    else:
        app.config.from_object(config_object)

    app.config["MARCA"] = dict(app.config.get("MARCA", Config.MARCA))
    _validar_configuracao_producao(app)

    if app.config.get("TRUST_PROXY_HEADERS"):
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=1,
            x_proto=1,
            x_host=1,
            x_port=1,
        )

    os.makedirs(app.instance_path, exist_ok=True)
    pasta_banco = os.path.dirname(app.config["DATABASE_PATH"])
    if pasta_banco:
        os.makedirs(pasta_banco, exist_ok=True)

    csrf.init_app(app)
    limiter.init_app(app)
    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=app.config.get("GOOGLE_CLIENT_ID"),
        client_secret=app.config.get("GOOGLE_CLIENT_SECRET"),
        server_metadata_url=app.config.get("GOOGLE_DISCOVERY_URL"),
        client_kwargs={"scope": "openid email profile"},
    )

    from views.admin import admin_bp
    from views.auth import auth_bp
    from views.booking import booking_bp
    from views.public import public_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(booking_bp)
    app.register_blueprint(admin_bp)

    @app.template_filter("urlencode")
    def filtrar_urlencode(valor):
        return quote(str(valor or ""), safe="")

    @app.context_processor
    def injetar_contexto():
        cliente = None
        administrador = None

        try:
            if session.get("cliente_id"):
                with obter_conexao() as conexao:
                    cliente = conexao.execute(
                        """
                        SELECT id, nome, email, telefone, avatar_url, origem
                        FROM clientes
                        WHERE id = ? AND ativo = 1
                        """,
                        (session["cliente_id"],),
                    ).fetchone()

            if session.get("administrador_id"):
                with obter_conexao() as conexao:
                    administrador = conexao.execute(
                        """
                        SELECT id, usuario
                        FROM administradores
                        WHERE id = ?
                        """,
                        (session["administrador_id"],),
                    ).fetchone()
        except Exception:
            cliente = None
            administrador = None

        return {
            "marca": app.config["MARCA"],
            "tema": app.config.get("TEMA", "urbano"),
            "ano_atual": datetime.now().year,
            "cliente_atual": cliente,
            "administrador_atual": administrador,
            "formatar_preco": formatar_preco_centavos,
            "formatar_telefone": formatar_telefone,
            "telefone_whatsapp": telefone_whatsapp,
            "rotulos_status": {
                "pendente": "Pendente",
                "confirmado": "Confirmado",
                "cancelado": "Cancelado",
                "concluido": "Concluído",
            },
            "rotulos_pagamento": {
                "nao_pago": "Não pago",
                "pago": "Pago",
                "reembolso_pendente": "Reembolso pendente",
                "reembolsado": "Reembolsado",
            },
        }

    @app.after_request
    def aplicar_seguranca(resposta):
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        resposta.headers["X-Frame-Options"] = "DENY"
        resposta.headers["Referrer-Policy"] = (
            "no-referrer"
            if request.endpoint == "booking.consulta"
            else "strict-origin-when-cross-origin"
        )
        resposta.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        resposta.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self'; "
            "script-src 'self'; "
            "font-src 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "object-src 'none'"
        )

        if app.config.get("SESSION_COOKIE_SECURE"):
            resposta.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        if request.endpoint and (
            request.endpoint.startswith("admin.")
            or request.endpoint.startswith("booking.minha_conta")
            or request.endpoint.startswith("auth.")
        ):
            resposta.headers["Cache-Control"] = "no-store"

        return resposta

    @app.errorhandler(403)
    def erro_403(_erro):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def erro_404(_erro):
        return render_template("errors/404.html"), 404

    @app.errorhandler(429)
    def erro_429(_erro):
        return render_template("errors/429.html"), 429

    @app.errorhandler(500)
    def erro_500(_erro):
        return render_template("errors/500.html"), 500

    @app.cli.command("init-db")
    def comando_init_db():
        """Cria o banco e aplica todas as migrações pendentes."""
        inicializar_banco()
        click.echo("Banco inicializado com sucesso.")

    @app.cli.command("criar-admin")
    @click.option("--usuario", prompt="Nome de usuário")
    @click.option(
        "--senha",
        prompt="Senha (mínimo 12 caracteres)",
        hide_input=True,
        confirmation_prompt=True,
    )
    def comando_criar_admin(usuario, senha):
        """Cria um administrador com senha protegida por hash."""
        usuario = (usuario or "").strip()
        if not usuario:
            raise click.ClickException("O usuário não pode ficar vazio.")
        if len(senha) < 12:
            raise click.ClickException("Use uma senha com pelo menos 12 caracteres.")

        try:
            with obter_conexao() as conexao:
                conexao.execute(
                    """
                    INSERT INTO administradores (usuario, senha_hash)
                    VALUES (?, ?)
                    """,
                    (usuario, generate_password_hash(senha)),
                )
        except Exception as erro:
            if "UNIQUE constraint failed" in str(erro):
                raise click.ClickException(
                    "Esse nome de usuário já está cadastrado."
                ) from erro
            raise

        click.echo("Administrador criado com sucesso.")

    @app.cli.command("seed-demo")
    def comando_seed_demo():
        """Insere serviços, profissionais e horários para apresentação."""
        from database.seed import criar_dados_demo

        criar_dados_demo()
        click.echo("Dados de demonstração criados/atualizados.")

    @app.route("/status")
    def status():
        with obter_conexao() as conexao:
            resultado = conexao.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name = 'schema_migrations'
                """
            ).fetchone()

        if resultado:
            return jsonify({"aplicacao": "ok", "banco": "ok"})
        return jsonify({"aplicacao": "ok", "banco": "nao inicializado"}), 500

    return app


app = create_app()


if __name__ == "__main__":
    with app.app_context():
        inicializar_banco()
    app.run(debug=app.config.get("ENV") == "development")
