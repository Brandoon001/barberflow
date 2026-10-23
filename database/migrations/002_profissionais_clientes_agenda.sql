CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    google_sub TEXT UNIQUE,
    email TEXT,
    nome TEXT NOT NULL,
    telefone TEXT,
    avatar_url TEXT,
    origem TEXT NOT NULL DEFAULT 'manual'
        CHECK (origem IN ('google', 'manual')),
    telefone_confirmado_em TEXT,
    cliente_principal_id INTEGER REFERENCES clientes(id),
    ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_clientes_telefone ON clientes(telefone);
CREATE INDEX IF NOT EXISTS idx_clientes_email ON clientes(email);

CREATE TABLE IF NOT EXISTS profissionais (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    apelido TEXT,
    bio TEXT,
    ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS profissional_servicos (
    profissional_id INTEGER NOT NULL
        REFERENCES profissionais(id) ON DELETE CASCADE,
    servico_id INTEGER NOT NULL
        REFERENCES servicos(id) ON DELETE CASCADE,
    PRIMARY KEY (profissional_id, servico_id)
);

CREATE TABLE IF NOT EXISTS horarios_trabalho (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profissional_id INTEGER NOT NULL
        REFERENCES profissionais(id) ON DELETE CASCADE,
    dia_semana INTEGER NOT NULL CHECK (dia_semana BETWEEN 0 AND 6),
    hora_inicio TEXT NOT NULL
        CHECK (hora_inicio GLOB '[0-2][0-9]:[0-5][0-9]'),
    hora_fim TEXT NOT NULL
        CHECK (hora_fim GLOB '[0-2][0-9]:[0-5][0-9]'),
    CHECK (hora_inicio < hora_fim),
    UNIQUE (profissional_id, dia_semana, hora_inicio)
);

CREATE INDEX IF NOT EXISTS idx_horarios_profissional
    ON horarios_trabalho(profissional_id, dia_semana);

CREATE TABLE IF NOT EXISTS agendamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL REFERENCES clientes(id),
    servico_id INTEGER NOT NULL REFERENCES servicos(id),
    profissional_id INTEGER NOT NULL REFERENCES profissionais(id),
    data TEXT NOT NULL,
    hora_inicio TEXT NOT NULL,
    hora_fim TEXT NOT NULL,
    preco_centavos INTEGER NOT NULL CHECK (preco_centavos >= 0),
    duracao_minutos INTEGER NOT NULL CHECK (duracao_minutos > 0),
    status TEXT NOT NULL DEFAULT 'pendente'
        CHECK (status IN ('pendente', 'confirmado', 'cancelado', 'concluido')),
    status_pagamento TEXT NOT NULL DEFAULT 'nao_pago'
        CHECK (status_pagamento IN (
            'nao_pago', 'pago', 'reembolso_pendente', 'reembolsado'
        )),
    token_hash TEXT NOT NULL UNIQUE,
    cancelado_por TEXT CHECK (
        cancelado_por IS NULL OR cancelado_por IN ('cliente', 'admin')
    ),
    motivo_cancelamento TEXT,
    reembolso_solicitado_em TEXT,
    reembolsado_em TEXT,
    reembolso_observacao TEXT,
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (hora_inicio < hora_fim)
);

CREATE INDEX IF NOT EXISTS idx_agendamentos_profissional_data
    ON agendamentos(profissional_id, data);
CREATE INDEX IF NOT EXISTS idx_agendamentos_cliente
    ON agendamentos(cliente_id, data);
CREATE INDEX IF NOT EXISTS idx_agendamentos_status
    ON agendamentos(status, data);
CREATE UNIQUE INDEX IF NOT EXISTS idx_agendamentos_slot_ativo
    ON agendamentos(profissional_id, data, hora_inicio)
    WHERE status IN ('pendente', 'confirmado');
