# Contas, cartões e importação

- `payment_mode=ACCOUNT` movimenta a conta. `DEBIT` movimenta a conta vinculada ao cartão quando a despesa está realizada. `CREDIT` compõe a fatura e só movimenta caixa no pagamento da fatura.
- Cartão múltiplo exige distinguir crédito/débito. Cartões legados sem conta são vinculados no primeiro uso, mediante conta válida explícita ou única conta disponível. Contas divergentes são rejeitadas. O formulário de cartões exige uma conta.
- Compras novas no crédito recebem a fatura do ciclo calculado. Compras adicionadas dentro de uma fatura mantêm o mês explicitamente escolhido. A resposta informa o mês de destino.
- Parcelamentos de cartão são listados na fatura pelo mês de vencimento. A primeira data é calculada pelo ciclo quando omitida; datas explícitas continuam respeitadas. Pagamento é feito pela fatura, sem duplicar caixa.
- Na importação, final de cartão único reconhecido no PDF pode selecionar um cartão do mesmo espaço. Divergência conhecida é bloqueada. Pagamentos/créditos ficam no resumo e não geram despesas nem débitos automáticos.
- A opção de acompanhar parcela reconhecida procura um plano pelo cartão, nome, quantidade, número e valor. Correspondência ambígua é bloqueada. Na ausência de plano, acompanha apenas a parcela observada e futuras, com valores futuros estimados e aviso na prévia; não fabrica histórico pago. Categoria é obrigatória para plano novo.
- `statement_import_links` registra a origem das parcelas sem criar transações fictícias. Chave única protege reimportações. Faturas com pagamento são protegidas, inclusive ao realinhar parcelas futuras.
- Responsáveis de membros seguem seus apelidos. `Conjunto` é ativado somente com mais de um membro. Rótulos históricos de lançamentos não são reescritos e responsáveis manuais são preservados.

Migração: `e41bd230aa17`. Preencher modalidade de movimentos legados não exclui lançamentos. Faça backup antes de aplicar.

`f0ac36e32b81` distingue a atribuição por data da escolha explícita de fatura. Ao alterar a data/cartão/modalidade de uma compra atribuída por data, o destino é recalculado; escolhas explícitas do usuário ou do PDF permanecem preservadas. Faturas já pagas continuam protegidas.

## Pagamento já realizado fora do Prumo

`POST /cards/{card_id}/invoices/{year}/{month}/external-payment` exige administrador, senha da conta conectada, data não futura e o total esperado para detectar alterações concorrentes. Confirma o restante da fatura sem criar saída bancária. Parcelas são reconhecidas e o limite é liberado; faturas vazias podem ser encerradas sem inventar o valor histórico pago. Confirmações são auditadas sem senha, com limite de tentativas por usuário.

`POST .../external-payment/reverse` exige novamente a senha e desfaz a conciliação sem alterar caixa. Pagamentos bancários anteriores são preservados. A confirmação externa deve ser desfeita antes de estornar um pagamento bancário. Enquanto confirmada, a composição da fatura fica protegida, inclusive quando o total é zero.

A tela distingue mês do vencimento e intervalo de compras. Uma fatura vazia não é considerada vencida apenas por sua data, nem presumida paga.
