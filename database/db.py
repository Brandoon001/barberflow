
from pathlib import Path
import sqlite3

PASTA_PROJETO = Path(__file__).resolve().parent.parent
PASTA_INSTANCE = PASTA_PROJETO / "instance"
PASTA_INSTANCE.mkdir(parents=True, exist_ok=True)

CAMINHO_BANCO = PASTA_INSTANCE / "barbearia.db"


def obter_conexao():
    conexao = sqlite3.connect(CAMINHO_BANCO)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    return conexao
