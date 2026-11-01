# Parcelamentos semanais

O cadastro aceita `frequency: MONTHLY | WEEKLY`, com padrão mensal para compatibilidade. Em acordos semanais, `first_due_date` fixa o dia da semana e as demais parcelas vencem a cada sete dias, sem ajuste por virada de mês. O total continua dividido com distribuição exata dos centavos.

A interface permite escolher o dia, ajustar a primeira data e visualizar os três primeiros vencimentos. Alterar o dia avança para a próxima ocorrência a partir da primeira data, incluindo essa própria data. Selecionar Semanal remove a escolha automática de cartão; a conta segue disponível, e o cartão pode ser escolhido explicitamente. As regras de liquidação por fatura permanecem para qualquer plano vinculado a cartão.

O calendário e os orçamentos continuam usando as datas reais de cada parcela. Pagar uma parcela bancária gera sua despesa somente uma vez. Planos importados de faturas permanecem mensais e não são confundidos com acordos semanais na identificação automática.

Migração e0637ca952b1: adiciona frequência com padrão MONTHLY e restrição aos dois valores aceitos. Não recria nem muda o vencimento de parcelas existentes.

Validação: tests/test_weekly_installments.py (segundas-feiras, virada de mês, centavos, pagamento único, padrão mensal e frequência inválida) e teste de interface weekly-installments.test.mjs.
