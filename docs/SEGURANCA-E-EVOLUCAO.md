# Segurança e evolução do MSFinanças

## Alterações implementadas

- Validação centralizada de referências por família, incluindo atualizações, contas de destino, cartões, responsáveis e formas de pagamento. Triggers PostgreSQL também impedem vínculos entre famílias nos relacionamentos principais.
- Convites com token armazenado por hash, aceite exclusivo pelo e-mail destinatário, listagem administrativa sem token e revogação. O token original aparece apenas na resposta de criação.
- Contas, categorias, responsáveis, cartões e orçamentos: alterações restritas a OWNER/ADMIN. Membros continuam podendo consultar informações e registrar movimentações compartilhadas.
- Senhas novas em Argon2; hashes bcrypt existentes continuam sendo aceitos. Novas senhas exigem 10–128 caracteres. Espaços de senhas são preservados.
- JWT com versão por usuário, validade padrão de uma hora e revogação em troca de senha, recuperação e logout. Logout encerra todas as sessões do usuário. Tokens antigos deixam de ser aceitos.
- Limitação de autenticação compartilhada no PostgreSQL: 20 requisições/minuto por IP e rota de login, 5 para cadastro/recuperação/confirmação. Em proxy, configurar a origem confiável no Uvicorn; a aplicação não interpreta cabeçalhos enviados diretamente pelo cliente.
- Recuperação por SMTP com STARTTLS e token de uso único com validade de 30 minutos. Sem configuração SMTP, responde 503 em vez de simular envio. Rotas públicas do frontend: `/recover-password` e `/reset-password?token=...`.
- Pagamento parcial mantém parcelas pendentes e libera somente o limite equivalente ao valor pago. O restante é liquidado no pagamento integral. Compras diretas usam o ciclo de fechamento; parcelas pertencem ao mês de vencimento, sem sobreposição.
- Pagamentos de cartão serializados por bloqueio no banco. Unicidade de fatura por cartão/competência. Cabeçalho opcional `Idempotency-Key` (UUID), utilizado pelo frontend, evita repetir o lançamento. A mesma chave com outro corpo retorna 409.
- Composição de fatura congelada após o primeiro pagamento. Alterações do ciclo de cartão com histórico são bloqueadas para não reinterpretar compras antigas.
- Movimentações geradas por faturas, parcelas e metas não podem ser editadas/excluídas/duplicadas diretamente. Estornos preservam registros e auditoria.
- Estornos administrativos disponíveis na API:
  - `POST /api/v1/cards/{card_id}/invoices/{year}/{month}/payments/{payment_id}/reverse`
  - `POST /api/v1/installments/installments/{installment_id}/reverse`
  - `POST /api/v1/goals/{goal_id}/contributions/{contribution_id}/reverse`
- Contribuições estornadas permanecem no histórico com `is_reversed=true`; não afetam o acumulado. Metas com histórico não podem ser apagadas. Ajuste de meta não movimenta conta; retiradas não podem exceder seu saldo.
- Transferências exigem destino diferente da origem. Valores monetários têm precisão e escala limitadas; atualizações rejeitam nulos em campos obrigatórios e textos excedentes.
- Orçamentos, resumo de transações e série mensal excluem liquidações de fatura para evitar dupla contagem. Na quitação da fatura, parcelas geram reconhecimento de despesa sem segundo débito bancário.
- Saldo inicial considera transações a partir de `initial_balance_date`, inclusive. O saldo informado representa o início desse dia.
- Auditoria transacional de configurações, orçamentos e convites; pagamentos e estornos explícitos. Atualização de transação registra seus campos anteriores e posteriores.
- CSV neutraliza fórmulas e limita exportação a 10.000 registros. Totais de transações são agregados no banco. Consulta de orçamento não grava mais registros.
- Compose exige segredos explícitos, publica PostgreSQL somente em localhost; `.dockerignore` exclui segredos do build.
- Testes usam schema exclusivo e migrações reais em banco dedicado com sufixo `_test`; não apagam mais o schema público.

## Atualização do ambiente

1. Fazer backup do banco existente e testar a restauração. A migração não reconcilia automaticamente registros financeiros já inconsistentes.
2. Configurar `SECRET_KEY` aleatória (pelo menos 32 caracteres), `POSTGRES_PASSWORD`, `DATABASE_URL` e `CORS_ORIGINS`. Exemplo de geração: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Produção recusa a chave antiga ou configuração ausente.
3. Executar `poetry run alembic upgrade head` no ambiente de destino antes de servir a nova aplicação. A migração `84b921ad1800` foi validada em PostgreSQL temporário; não foi aplicada ao banco da aplicação durante este trabalho.
4. Reiniciar backend e publicar o frontend correspondente. Usuários precisam entrar novamente. Convites pendentes anteriores são revogados por segurança e devem ser recriados.
5. Para recuperação, configurar `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, `SMTP_USER`, `SMTP_PASSWORD` e `PASSWORD_RESET_URL=https://seu-frontend/reset-password`. O SMTP precisa suportar STARTTLS. O envio real depende das credenciais do ambiente; testes substituem o transporte por captura local.

A migração interrompe a atualização se encontrar duplicidade de faturas, transferências inválidas, valores incompatíveis com as restrições ou referências cruzadas entre famílias. Investigar os registros e reconciliar a situação antes de tentar novamente; não apagar movimentações indiscriminadamente. Pagamentos parciais antigos podem ter parcelas marcadas indevidamente como pagas e exigem conferência: a migração não consegue inferir a intenção desses lançamentos.

Sem SECRET_KEY configurada em desenvolvimento, uma chave temporária é gerada por processo: reiniciar invalida sessões. Configure uma chave estável para desenvolvimento com vários workers.

## Validação

Executar, em um PostgreSQL descartável:

```sh
TEST_DATABASE_URL=postgresql://usuario:senha@localhost:5432/msfinancas_test poetry run pytest -q
```

O banco deve existir, terminar em `_test` e ser diferente de `DATABASE_URL`. O usuário precisa criar/remover schemas. A suíte cria e remove apenas o schema aleatório que lhe pertence.

No frontend: `npm run build`.

## Próximas funcionalidades sugeridas

| Prioridade | Funcionalidade | Benefício e critério de entrega |
|---|---|---|
| 1 | Central de vencimentos | Mostrar contas, parcelas e faturas dos próximos 7/30 dias, sem duplicar parcelas de cartão com a própria fatura. Alertas configuráveis por pessoa. |
| 1 | Interface de estorno e histórico de pagamentos | Consumir os endpoints de estorno, mostrar cada pagamento parcial, autor, data e motivo, com permissão administrativa. Atualmente os estornos estão disponíveis na API. |
| 1 | Conciliação financeira | Importar CSV/OFX com prévia, detecção de duplicados e vínculo com lançamentos existentes; nenhuma importação deve duplicar automaticamente despesas. |
| 1 | Verificação de e-mail e gestão de membros | Confirmar propriedade do e-mail antes de compartilhar informações; permitir remover membros e administrar papéis sem perder o último proprietário. Atualmente a correspondência do e-mail é validada, mas não há confirmação de propriedade. |
| 2 | Despesas recorrentes | Assinaturas e contas mensais com prévia dos próximos lançamentos, pausa e edição desta ocorrência ou das futuras. O motor de datas já oferece uma base. |
| 2 | Previsão de caixa | Projetar saldo em 30/60/90 dias, distinguindo disponível, comprometido e previsto. Evitar que limite de cartão seja tratado como saldo. |
| 2 | Metas com aportes planejados | Calcular aporte mensal necessário até a data alvo e permitir reserva entre contas sem distorcer receitas e despesas. |
| 2 | Sessões por dispositivo e renovação | Mostrar dispositivos, revogar individualmente e renovar sessões com refresh token rotativo. Hoje a revogação é global e o acesso expira em uma hora. |
| 3 | Fechamento mensal | Travar mês conciliado, produzir demonstrativo e exigir reabertura auditada para alterações posteriores. |
| 3 | Pesquisa e paginação completas | Paginar parcelamentos, contribuições e demais coleções; retirar N+1 e medir consultas com famílias grandes. A correção atual otimiza os totais de transações e limita exportações, mas não resolve toda a escalabilidade. |
| 3 | Observabilidade | Identificador de requisição, métricas de latência, falhas de autenticação e alertas de inconsistência, sem registrar senhas ou tokens. |

As propostas não são funcionalidades implementadas neste lote, exceto as correções e endpoints descritos acima. Testes de produção, transporte SMTP real, reconciliação do histórico e configuração do proxy dependem do ambiente de destino.
