# Destino final e referência da fatura

A escolha inicial de conta/cartão permanece. A interface apresenta um diálogo obrigatório ao concluir a revisão, permitindo confirmar ou corrigir conta, cartão e mês de referência. O destino final é enviado em `ImportConfirm.destination`; a API verifica espaço, conta vinculada, tipo de cartão, final reconhecido no documento, linhas bloqueadas, duplicidades e pagamentos antes de gravar. O arquivo, datas, valores e fingerprints continuam vinculados à prévia assinada. Nenhum lançamento é criado ao abrir ou cancelar o diálogo.

OFX com CCSTMTRS é reconhecido como fatura mesmo quando a escolha inicial foi conta bancária. Pagamentos e créditos permanecem informativos e não podem virar compras. Parcelas são reconhecidas pela descrição original; ao confirmar um cartão, podem criar acompanhamento sem recriar parcelas anteriores à observada. O final não libera linhas bloqueadas na prévia.

`credit_cards.billing_month_offset` distingue referência por vencimento (0, padrão preservado) de referência pelo mês anterior ao vencimento (-1). A convenção solicitada para o Nubank Mateus é -1: compras de 05/10 a 04/11 têm referência outubro e vencimento bancário em novembro. Datas de fechamento e vencimento não são antecipadas para coincidir com o rótulo. Alterações dessa convenção em cartões com histórico exigem reconciliação dos vínculos existentes; não são uma simples edição do nome do mês.

`installments.invoice_id` fixa a fatura da parcela observada e das futuras estimadas. Listagem e liquidação usam o vínculo explícito; registros antigos sem vínculo continuam seguindo o vencimento do ciclo. A parcela observada aparece uma única vez na fatura, e sua despesa é reconhecida ao pagar pelo fluxo da fatura.

A correção dos dados importados mantém as transações originais convertidas como excluídas logicamente, registra auditoria e cria links de deduplicação para a identidade do arquivo no cartão correto. Não representa pagamentos anteriores inexistentes nem altera receitas/transferências preservadas.

Validação: testes de destino final, referências nas bordas do fechamento, parcelas futuras, pagamento da parcela na fatura correta, bloqueio de fatura paga e regressão completa. A migração d952ab310f68 adiciona somente campos/vínculos; a reparação dos dados é uma operação separada e transacional, com backup anterior.
