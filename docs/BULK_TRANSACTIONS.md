# Alteração de lançamentos em lote

`POST /api/v1/transactions/bulk` recebe até 100 itens (`id`, `updated_at`) e os campos opcionais `responsible_name` e `status`. Exige ao menos uma alteração, IDs únicos, responsável ativo e todos os lançamentos no espaço autenticado. A seleção da interface cobre somente a página atual e é limpa ao recarregar ou trocar filtros/página.

A operação trava cartões e lançamentos em ordem estável, verifica versões e vínculos protegidos antes de escrever, registra auditoria e confirma tudo na mesma transação. Qualquer erro impede o lote inteiro. Parcelas, movimentos de metas, pagamentos de fatura e composição de faturas já pagas continuam protegidos. Alterar situação de uma compra no crédito não liquida a fatura; o pagamento continua no fluxo de faturas. Alterar situação de movimentos bancários afeta o saldo calculado.

Validação: `tests/test_transaction_bulk.py` e testes de interface desktop/mobile `tests/transaction-bulk.test.mjs` no frontend, incluindo confirmação, conflito e recuperação da seleção.
