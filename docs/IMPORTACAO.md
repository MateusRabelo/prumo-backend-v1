# Faturas e importação assistida

A área Faturas reúne os cartões de crédito e múltiplos por mês de vencimento. Permite abrir/cadastrar a fatura, incluir compras, editar e excluir compras à vista antes do primeiro pagamento, e pagar usando contas correntes, poupanças ou carteiras. Parcelamentos continuam no fluxo próprio. Faturas que receberam pagamento têm composição protegida.

A cobertura usa o saldo atual registrado no Prumo. Soma o dinheiro uma única vez, desconta pagamentos já realizados e exclui investimentos, contas-cartão e receitas futuras. A comparação considera somente as faturas do mês selecionado, sem reservar dinheiro para outras despesas. Não existe conexão automática com o saldo real dos bancos.

## Importar extrato

1. Escolher conta ou cartão e mês de referência.
2. Enviar PDF com texto selecionável, CSV ou OFX.
3. Conferir as linhas reconhecidas, selecionar as que serão importadas, corrigir os nomes e escolher categorias. Valores bancários sem sinal exigem classificação explícita como entrada ou saída.
4. Marcar a confirmação de conferência e salvar.

PDF: o leitor reconhece linhas com data, descrição e valor monetário. Layouts em colunas complexas, dados quebrados em várias linhas, imagens e PDFs protegidos podem não funcionar. O sistema retorna avisos ou recusa a leitura em vez de criar valores por adivinhação. Quando existem várias colunas monetárias, a primeira é exibida com aviso para conferência. Datas sem ano usam o mês de referência e a virada dezembro/janeiro; precisam de revisão. Não há garantia de extração integral de qualquer layout bancário.

CSV: cabeçalhos Data/Date, Descrição/Description/Histórico/Title e Valor/Amount; tipo de entrada/saída opcional. OFX usa DTPOSTED, TRNAMT, MEMO/NAME e FITID.

Limites: 4 MB, 30 páginas de PDF, 500 linhas por arquivo e 30 prévias por usuário/hora. O processamento de PDF ocorre em subprocesso com limite de memória e tempo. O arquivo original não é retido após o processamento. A prévia assinada expira após 30 minutos e é vinculada ao usuário, espaço e destino; os dados financeiros não são enviados a provedores de IA.

## Nomes e categorias aprendidos

Corrigir “R N Doces” para “Cantina faculdade” marca a opção de lembrar. A regra é salva somente na confirmação da importação e vale para o espaço familiar atual. A identificação normaliza letras, acentos, espaços e pontuação; não faz correspondência aproximada por fragmentos. Nome e categoria podem ser sugeridos em importações futuras. Categorias não definem automaticamente o sinal de uma movimentação ambígua.

As regras podem ser esquecidas na própria tela. Isso não altera lançamentos já salvos. Nenhum arquivo é automaticamente enviado a um modelo externo, nem existe dependência de chave ou assinatura de IA.

## Duplicidades e conciliação

O importador usa chaves estáveis por conta ou cartão e identificador bancário quando disponível. Reenviar o mesmo lote não duplica as transações. Para compras de cartão, trocar a conta de referência não muda a chave de deduplicação. Linhas parecidas com lançamentos manuais são apenas sinalizadas e vêm desmarcadas, pois compras iguais podem ser legítimas.

Pagamentos e créditos de cartão precisam dos fluxos de pagamento/estorno e não viram compras importadas. Possíveis parcelas vêm desmarcadas; quem já cadastrou o parcelamento deve manter essas linhas fora da importação. Transferências internas entre contas devem usar o fluxo de transferência, não receita/despesa. Importações em faturas com pagamento são recusadas, inclusive se o pagamento ocorrer entre prévia e confirmação.

A nova tabela import_merchant_rules é criada por Alembic, com RLS ativado e acesso público revogado. Todas as operações da API validam o espaço familiar. A confirmação é transacional: erros impedem a gravação do lote inteiro.

## Faturas Nubank

O leitor reconhece datas abreviadas como “30 SET”, o ano indicado no cabeçalho, sinais monetários Unicode e descrições quebradas em linhas. O número mascarado do cartão é removido do nome do estabelecimento. Somente as linhas de transações entram na prévia; totais de simulações, limites e próximas faturas não são confundidos com compras.

A prévia mostra o resumo do PDF e compara compras, créditos/estornos, pagamentos e total devido. Se as somas reconhecidas não fecharem, a confirmação é bloqueada no servidor. Pagamentos, créditos e saldo anterior não geram movimentações automaticamente: a interface exige ciência da conciliação separada. Uma compra com estorno integral do mesmo nome e valor, identificado sem ambiguidade no arquivo, vem desmarcada para não somar despesa cancelada.

As compras confirmadas são vinculadas explicitamente ao cartão e mês indicados na fatura. A atribuição prevalece sobre a data calculada pelo fechamento cadastrado, inclusive compras no dia limítrofe do ciclo. Antes de haver pagamento, continuam editáveis/excluíveis; após pagamento, a composição permanece protegida.

Regressões permanentes usam exemplos sintéticos do layout. Os PDFs reais podem ser verificados localmente com NUBANK_SAMPLE_DIR, mas nunca são versionados no Git.
