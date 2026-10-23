from functools import wraps
from urllib.parse import urlparse

from flask import flash, redirect, request, session, url_for

from database.db import obter_conexao


def cliente_atual():
    cliente_id = session.get("cliente_id")
    if not cliente_id:
        return None

    with obter_conexao() as conexao:
        cliente = conexao.execute(
            """
            SELECT id, google_sub, email, nome, telefone, avatar_url,
                   origem, telefone_confirmado_em
            FROM clientes
            WHERE id = ? AND ativo = 1
            """,
            (cliente_id,),
        ).fetchone()

    if not cliente:
        session.pop("cliente_id", None)
    return cliente


def cliente_required(funcao):
    @wraps(funcao)
    def verificar_cliente(*args, **kwargs):
        cliente = cliente_atual()
        if not cliente:
            destino = request.full_path if request.method == "GET" else request.path
            return redirect(url_for("auth.login_google", next=destino))
        return funcao(*args, **kwargs)

    return verificar_cliente


def destino_seguro(valor, padrao):
    if not valor:
        return padrao

    if "\\" in valor or any(ord(caractere) < 32 for caractere in valor):
        return padrao

    partes = urlparse(valor)
    if partes.scheme or partes.netloc:
        return padrao
    if not valor.startswith("/") or valor.startswith("//"):
        return padrao
    return valor


def mensagem_erro(erro, padrao="Não foi possível concluir a operação."):
    texto = str(erro).strip()
    return texto or padrao


def redirecionar_com_erro(endpoint, erro, **kwargs):
    flash(mensagem_erro(erro), "erro")
    return redirect(url_for(endpoint, **kwargs))
