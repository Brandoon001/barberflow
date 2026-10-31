# Operação da barbearia

## Rotina diária

1. Abra `/admin/agenda` e confira a data.
2. Use os filtros de profissional e status quando necessário.
3. Confirme os agendamentos pendentes.
4. Ao finalizar um atendimento, use **Concluir**.
5. Registre o pagamento pelo menu **Pagamento** do agendamento.
6. Acompanhe os reembolsos pendentes no painel inicial ou na agenda.

## Login do cliente

O cliente acessa `/entrar` e escolhe **Entrar com Google**. No primeiro acesso,
o sistema pede o WhatsApp com DDD e o consentimento para contato. A data e a
versão do termo ficam registradas no cadastro.

Depois do cadastro, o cliente pode corrigir o WhatsApp em **Minha conta →
Editar WhatsApp**. A correção também registra um novo consentimento.

## Cadastro manual de cliente

Use **Clientes → Novo cliente manual** quando a pessoa ainda não tem conta
Google. São necessários apenas nome e WhatsApp.

O cadastro manual não tem login. Para que o cliente passe a acessar a conta
pelo Google:

1. O cliente deve entrar pela primeira vez com Google no site.
2. No painel, abra o cadastro manual e clique em **Vincular a conta Google**.
3. Escolha a conta correta.
4. Confirme o vínculo.

O cadastro manual é desativado e todos os agendamentos são transferidos para a
conta Google escolhida. O vínculo nunca é feito automaticamente pelo telefone.

## Cancelamentos

- O cliente pode cancelar pelo site até 30 minutos antes do horário.
- Depois desse prazo, a página orienta o cliente a falar com a barbearia.
- O administrador pode cancelar a qualquer momento pelo painel.
- Ao cancelar um agendamento pago, o status do pagamento passa para
  **Reembolso pendente**.

## Reembolsos

1. Faça a devolução manualmente pelo meio combinado com o cliente.
2. Na agenda, abra o menu **Reembolso** do agendamento.
3. Registre uma observação, por exemplo: `Devolvido via Pix`.
4. Clique em **Marcar como reembolsado**.

O sistema não processa pagamentos nem devoluções financeiras.

## Jornadas de trabalho

Em **Profissionais → Horários**, cada dia tem dois turnos:

- Turno 1: manhã.
- Turno 2: tarde.

Deixe os dois campos de um turno vazios para não atender naquele período. Para
um intervalo de almoço, use os turnos para separar os períodos, por exemplo
`09:00–12:00` e `13:00–19:00`. Turnos sobrepostos são recusados.

## Backup

Com a aplicação parada ou em baixo movimento, copie:

- o arquivo indicado em `DATABASE_PATH` (padrão `instance/barbearia.db`);
- o diretório `instance/`;
- o arquivo `.env` em local seguro.

Teste a restauração periodicamente em um ambiente separado.

## Problemas comuns

### Aplicação não inicia em produção

A inicialização é bloqueada quando:

- `SECRET_KEY` está vazia, curta ou com valor de exemplo;
- `GOOGLE_CLIENT_ID` ou `GOOGLE_CLIENT_SECRET` estiverem vazios;
- `GOOGLE_REDIRECT_URI` não é HTTPS público;
- `SESSION_COOKIE_SECURE` não está `true`;
- `DATABASE_PATH` não é absoluto.

Corrija o `.env` e reinicie o serviço.

### Login Google indisponível

Verifique `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` e se o URI de callback no
Google Cloud é exatamente o mesmo de `GOOGLE_REDIRECT_URI`.

A conta Google precisa ter e-mail verificado. Contas desativadas no painel
também não conseguem entrar.

### Cliente não consegue agendar

Confirme se:

- o cliente concluiu o cadastro do WhatsApp;
- existe ao menos um serviço ativo;
- o profissional está ativo, atende ao serviço e possui jornada no dia;
- a data está dentro da janela de agendamento;
- o horário ainda está livre.

### Sessão administrativa expirou

Por padrão, a sessão expira após 60 minutos sem atividade. Entre novamente em
`/admin/login`. O tempo pode ser ajustado em `ADMIN_SESSAO_MINUTOS`.

### Erro de CSRF

Recarregue a página e envie o formulário novamente. Formulários enviados com a
página antiga podem ser recusados após a sessão expirar.
