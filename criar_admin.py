
import getpass

from werkzeug.security import generate_password_hash

from database.db import obter_conexao


def criar_admin():
    print("=== Criar administrador do BarberFlow ===")

    usuario = input("Nome de usuário: ").strip()

    if not usuario:
        print("O usuário não pode ficar vazio.")
        return

    senha = getpass.getpass("Digite a senha: ")
    confirmacao = getpass.getpass("Confirme a senha: ")

    if len(senha) < 12:
        print("Use uma senha com pelo menos 12 caracteres.")
        return

    if senha != confirmacao:
        print("As senhas não coincidem.")
        return

    senha_hash = generate_password_hash(senha)

    try:
        with obter_conexao() as conexao:
            conexao.execute(
                """
                INSERT INTO administradores (usuario, senha_hash)
                VALUES (?, ?)
                """,
                (usuario, senha_hash),
            )

        print("Administrador criado com sucesso!")

    except Exception as erro:
        if "UNIQUE constraint failed" in str(erro):
            print("Esse nome de usuário já está cadastrado.")
        else:
            raise


if __name__ == "__main__":
    criar_admin()
