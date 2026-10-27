# Assinaturas e faturas OFX

Assinaturas usam `recurrence_rules` com `is_subscription`, cartão opcional e próxima cobrança. Cadastro, edição, pausa/retomada e confirmação de cobrança pertencem ao espaço autenticado. O cartão deriva a conta vinculada. Cobranças de cartão entram na fatura; cobranças diretas movimentam a conta.

As próximas datas são previsões. Não há processo que debite contas ou fabrique compras futuras. Confirmar uma cobrança exige a data esperada do ciclo e serializa a regra, impedindo repetição por duplo clique. Valores anuais e semanais são convertidos apenas para o resumo mensal estimado.

A prévia sugere assinaturas a partir de serviços conhecidos, regras existentes e histórico mensal do mesmo estabelecimento e valor. Novas sugestões exigem confirmação e categoria; uma assinatura conhecida pode ser vinculada e atualizada com a cobrança observada. Uma cobrança manual já registrada é reconhecida para evitar duplicação na importação. O reconhecimento é local, sem envio do extrato a serviços de IA.

OFX de cartão com `CCSTMTRS` e `DTEND` informa o período de fechamento. Esse período ancora a fatura, inclusive para parcelas cuja data original é anterior ao ciclo. O dia de vencimento vem do cartão selecionado. Metadados ausentes não são inventados; o sistema mantém a leitura por datas do cartão. Pagamentos e créditos ficam separados e exigem ciência na revisão. O resumo do OFX não é tratado como uma reconciliação bancária completa quando faltam saldo anterior/total devido.

O limite da prévia assinada é de 800 mil caracteres, preservando os limites de 4 MB, 500 linhas, validade de 30 minutos e validação da assinatura e do contexto. O validador genérico de 10 mil caracteres não deve se sobrepor a esse limite. As mensagens de validação da interface não exibem o token nem os valores de entrada da exceção.

Migração `b73e9102c1d4` preserva as regras anteriores. Testes com OFX privado são opcionais e locais; documentos bancários não fazem parte do repositório.
