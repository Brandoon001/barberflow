CREATE TABLE IF NOT EXISTS barbearias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    ativo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS administradores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS servicos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    descricao TEXT,
    preco_centavos INTEGER NOT NULL CHECK (preco_centavos >= 0),
    duracao_minutos INTEGER NOT NULL CHECK (duracao_minutos > 0),
    ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1))
);
