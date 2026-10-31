ALTER TABLE clientes ADD COLUMN telefone_informado_em TEXT;
ALTER TABLE clientes ADD COLUMN consentimento_em TEXT;
ALTER TABLE clientes ADD COLUMN consentimento_versao TEXT;

UPDATE clientes
SET telefone_informado_em = telefone_confirmado_em
WHERE telefone_informado_em IS NULL
  AND telefone_confirmado_em IS NOT NULL;

ALTER TABLE agendamentos ADD COLUMN consentimento_em TEXT;
