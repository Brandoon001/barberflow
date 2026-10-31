# BarberFlow

MVP de agendamento para uma barbearia, com site público, login de clientes via
Google, confirmação de WhatsApp e painel administrativo.

## Recursos

- Agendamento online por serviço, profissional, data e horário.
- Login obrigatório do cliente com Google, com página dedicada em `/entrar`.
- WhatsApp obrigatório no primeiro acesso, com validação de formato.
- Consentimento de contato registrado com data e versão do termo.
- Cliente pode corrigir o WhatsApp depois em **Minha conta**.
- Consulta e cancelamento pelo cliente até 30 minutos antes do horário.
- Painel administrativo com login por usuário e senha.
- Gestão de serviços, profissionais, jornadas de trabalho e clientes.
- Cadastro manual de clientes e vínculo manual com contas Google.
- Agenda diária com confirmação, conclusão, cancelamento e pagamentos.
- Reembolso tratado manualmente pela barbearia.
- Identidade white-label por variáveis de ambiente.
- Cabeçalhos de segurança, CSRF e limitação de tentativas.

## Requisitos

- Python 3.11 ou superior.
- Conta no Google Cloud para OAuth (necessária apenas para login real).

## Instalação

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edite o `.env`, principalmente `SECRET_KEY` e as credenciais do Google.

## Banco e primeiro administrador

```bash
flask --app app init-db
flask --app app criar-admin
flask --app app seed-demo
```

`seed-demo` é opcional e cria serviços, profissionais e jornadas de exemplo.
O banco SQLite fica, por padrão, em `instance/barbearia.db`.

## Executar

```bash
flask --app app run --debug
```

Acesse `http://localhost:5000`. O painel fica em `/admin/login`.

## Login com Google

1. Crie um projeto no Google Cloud e configure a tela de consentimento OAuth.
2. Crie uma credencial do tipo **Aplicativo da Web**.
3. Adicione o URI de redirecionamento autorizado:
   - Desenvolvimento: `http://localhost:5000/auth/google/callback`
   - Produção: `https://SEU-DOMINIO/auth/google/callback`
4. Preencha no `.env`:

```env
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:5000/auth/google/callback
```

Sem essas credenciais, o site continua público, mas a página `/entrar`
informa que o login Google está indisponível. Em produção, a aplicação
recusa iniciar sem as credenciais.

## Regras de negócio

- Uma barbearia por instalação.
- Jornada padrão de demonstração: segunda a sábado, 09:00–12:00 e 13:00–19:00.
- Intervalos de agendamento configuráveis, com padrão de 30 minutos.
- Agendamentos permitidos com até 60 dias de antecedência.
- Confirmação inicial configurável: `pendente` ou `confirmado`.
- Cancelamento pelo cliente somente até 30 minutos antes do início.
- Após o prazo, o cliente deve falar com a barbearia; o administrador ainda
  pode cancelar pelo painel.
- Agendamento com pagamento `pago` cancelado gera `reembolso_pendente`.
- A barbearia conclui o reembolso manualmente e marca o status no painel.
- O vínculo entre cliente manual e conta Google é manual e transfere todos os
  agendamentos do cadastro manual.

## Variáveis principais

| Variável | Descrição |
| --- | --- |
| `SECRET_KEY` | Chave das sessões e do CSRF. Use um valor longo e aleatório. |
| `DATABASE_PATH` | Caminho do SQLite. Vazio usa `instance/barbearia.db`. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Credenciais OAuth. |
| `GOOGLE_REDIRECT_URI` | URL de callback registrada no Google. |
| `MARCA_NOME`, `MARCA_SLOGAN`, `MARCA_WHATSAPP` | Identidade da barbearia. |
| `AGENDAMENTO_INTERVALO_MINUTOS` | Granularidade dos horários. |
| `AGENDAMENTO_DIAS_FUTUROS` | Janela máxima de agendamento. |
| `CANCELAMENTO_MINUTOS_ANTECEDENCIA` | Prazo mínimo para cancelar. |
| `AGENDAMENTO_CONFIRMACAO_AUTOMATICA` | `true` cria agendamentos confirmados. |
| `ADMIN_SESSAO_MINUTOS` | Expiração da sessão administrativa. |
| `SESSION_COOKIE_SECURE` | Ative `true` em produção com HTTPS. |
| `TRUST_PROXY_HEADERS` | Use `true` atrás de Nginx com `X-Forwarded-*`. |
| `MAX_CONTENT_LENGTH` | Limite de tamanho das requisições, em bytes. |
| `CONSENTIMENTO_VERSAO` | Versão do termo registrada no cadastro. |

## Testes

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Os testes cobrem autenticação administrativa e de cliente, callback Google,
consentimento, edição de WhatsApp, CSRF, cabeçalhos de segurança, serviços,
clientes, vínculo manual, disponibilidade, agendamento, cancelamento e
reembolso.

## Estrutura

```text
app.py                    factory Flask, CLI, headers e contexto
config.py                 configuração por ambiente
extensions.py             CSRF, limiter e OAuth
database/                 conexão, migrações e seed
services/                 validação e regras de agenda
views/                    rotas públicas, de cliente e administrativas
templates/                páginas públicas, painel e erros
static/                   CSS e JavaScript sem dependências externas
tests/                    testes com unittest
```

## Produção

- Use `FLASK_ENV=production`.
- Defina `SECRET_KEY` forte, `SESSION_COOKIE_SECURE=true` e
  `TRUST_PROXY_HEADERS=true` atrás de Nginx.
- Configure `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` e um
  `GOOGLE_REDIRECT_URI` HTTPS público.
- Use `DATABASE_PATH` com caminho absoluto.
- Execute atrás de HTTPS com um servidor WSGI de produção.
- A aplicação recusa iniciar em produção se `SECRET_KEY`, OAuth, cookie seguro,
  callback HTTPS ou caminho do banco estiverem inseguros.
- O `RATELIMIT_STORAGE_URI` em memória funciona com um processo. Para múltiplos
  workers, configure um backend compartilhado.
- Faça backup do arquivo SQLite e do diretório `instance/`.
- Consulte [docs/operacao.md](docs/operacao.md) para o roteiro do dia a dia.

## Limitações deste MVP

- Não há cobrança online; pagamentos são registrados no painel.
- WhatsApp usa links `wa.me`, sem API de mensagens.
- OAuth real depende da configuração externa do Google Cloud.
- O sistema atende uma única barbearia por instalação.
