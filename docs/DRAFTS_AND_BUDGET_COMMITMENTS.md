# Rascunhos de importação

A geração da prévia cria um rascunho privado para o usuário e espaço atuais, disponível por 30 dias. Até 10 rascunhos ativos são permitidos por pessoa em cada espaço. O arquivo original não é armazenado: são mantidas as linhas interpretadas, o contexto imutável e os campos de revisão.

GET/PUT/DELETE `/imports/drafts/{id}` exigem propriedade do usuário e vínculo ao espaço, inclusive para administradores. Membros do mesmo espaço não acessam rascunhos de outras pessoas. A tabela usa RLS e não concede acesso às roles públicas do Supabase.

As edições usam revisão otimista. Uma aba não sobrescreve silenciosamente mudanças de outra. Campos de dinheiro, data original, bloqueios e impressões digitais não podem ser enviados pelo endpoint de edição do rascunho. Ao retomar, o servidor renova a prévia assinada e verifica duplicidades e faturas protegidas. Na confirmação, as validações financeiras e a idempotência continuam obrigatórias. Importações concluídas deixam de aparecer na lista e não podem ser reabertas para alterar a seleção.

A interface salva automaticamente após as edições e fornece salvar/retomar/descartar explícitos. Uma cópia de emergência dos campos editáveis no navegador é vinculada a usuário, espaço e rascunho; não inclui arquivo original, valores bancários ou token da prévia. Essa cópia protege a última edição durante uma recarga ou falha de rede. Não é cache de respostas financeiras do service worker. A revisão deve ser conferida novamente após a retomada.

# Orçamento e classificações

Os orçamentos 50/30/20 e personalizados compartilham o mesmo conjunto de despesas:

- Compras no crédito comprometem o orçamento no mês da compra, inclusive pendentes/vencidas.
- Gastos diretos de conta e débito entram quando realizados.
- Parcelas entram individualmente no mês do vencimento, pendentes ou pagas.
- Transações geradas para reconhecer parcelas e pagamentos de fatura não são somadas novamente.

Necessidade, desejo, investimento/poupança e outro podem ser escolhidos na revisão, individualmente ou em lote. A escolha explícita é preservada nas regras aprendidas, planos e cobranças. Na ausência de escolha explícita, o plano usa a classificação da categoria. Outros gastos aparecem no total comprometido, separados das três faixas da regra.

Migração `c84f0a9d721e`: tabela de rascunhos e colunas opcionais de classificação, preservando dados anteriores. As mudanças de orçamento são cálculos de leitura; não alteram saldos ou transações existentes.
