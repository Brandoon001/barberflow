import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import current_app, has_app_context


PASTA_PROJETO = Path(__file__).resolve().parent.parent
PASTA_INSTANCE = PASTA_PROJETO / "instance"
PASTA_MIGRACOES = Path(__file__).resolve().parent / "migrations"
CAMINHO_BANCO = PASTA_INSTANCE / "barbearia.db"


def caminho_banco():
    if has_app_context():
        return current_app.config["DATABASE_PATH"]
    return str(CAMINHO_BANCO)


@contextmanager
def obter_conexao(imediata=False):
    """Abre uma conexão, confirma/desfaz a transação e sempre a fecha."""
    conexao = sqlite3.connect(caminho_banco(), timeout=10)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    conexao.execute("PRAGMA busy_timeout = 5000")

    try:
        if imediata:
            conexao.execute("BEGIN IMMEDIATE")
        yield conexao
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()


def inicializar_banco(caminho=None):
    """Aplica, em ordem, as migrações SQL ainda não executadas."""
    caminho = caminho or caminho_banco()
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)

    conexao = sqlite3.connect(caminho, timeout=10)
    conexao.row_factory = sqlite3.Row
    try:
        conexao.execute("PRAGMA journal_mode = WAL")
        conexao.execute("PRAGMA foreign_keys = ON")
        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                nome TEXT PRIMARY KEY,
                aplicado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conexao.commit()

        aplicadas = {
            linha["nome"]
            for linha in conexao.execute(
                "SELECT nome FROM schema_migrations"
            ).fetchall()
        }

        for arquivo in sorted(PASTA_MIGRACOES.glob("*.sql")):
            if arquivo.name in aplicadas:
                continue

            conexao.executescript(arquivo.read_text(encoding="utf-8"))
            conexao.execute(
                "INSERT INTO schema_migrations (nome) VALUES (?)",
                (arquivo.name,),
            )
            conexao.commit()
    finally:
        conexao.close()
