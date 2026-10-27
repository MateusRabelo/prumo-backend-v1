# Organização e contexto do frontend

## Problema corrigido

Sofia já possuía uma associação ADMIN à Família Mateus e outra OWNER à Família Sofia. A interface exibia apenas o espaço individual, sem um seletor utilizável. O selo de compartilhamento era exibido mesmo para famílias com uma única pessoa. Nenhuma associação precisava ser recriada.

## Fluxos atuais

- Seletor de espaço na navegação, com nome, quantidade de pessoas e indicação de compartilhamento.
- Página Família e acesso lista todos os espaços do usuário e os integrantes do espaço ativo. Indica a diferença entre responsável por lançamento e pessoa com acesso.
- Aviso nas outras páginas quando o usuário está no espaço individual e já participa de um compartilhado.
- Troca de contexto remonta a tela, fecha formulários de lançamento e cancela confirmações pendentes. O último espaço escolhido é lembrado por usuário. Cada aba mantém seu espaço em sessionStorage, usado também nas requisições; uma troca em outra aba não altera silenciosamente o cabeçalho X-Family-Id da atual.
- Convites geram link compartilhável, com opção de código manual. A interface informa que o usuário deve enviar o link; não afirma que um e-mail foi enviado.
- Convite aceito abre o espaço correspondente. O caminho do convite é preservado ao entrar ou cadastrar uma conta. Falhas permanecem no formulário, sem mudar o espaço atual.
- Papéis e contagem de integrantes são retornados em `/auth/my-families` e `/family/current`, sem alterações de schema do banco.

## Organização

- Dia a dia: visão geral, lançamentos, contas e cartões, parcelamentos.
- Planejamento: orçamentos, metas e relatórios.
- Seu espaço: família e acesso, preferências.
- Contas ficam exclusivamente em Contas e cartões; o cadastro duplicado foi retirado de Preferências.
- Preferências reúne categorias, responsáveis e formas de pagamento. O cadastro de responsáveis não concede acesso ao espaço.
- Botões administrativos são ocultos para membros. A autorização permanece no backend.
- Avisos e confirmações usam componentes da aplicação; ações financeiras globais foram retiradas das páginas administrativas.
- Layout, superfícies, tipografia, largura e estados de foco compartilham estilos; as páginas carregam sob demanda.

## Validação

Backend: executar pytest com TEST_DATABASE_URL dedicado, conforme SEGURANCA-E-EVOLUCAO.md. O teste `test_family_context.py` verifica dois espaços com papéis e contagens diferentes.

Frontend:

```sh
npm run build
# Com o Vite rodando em localhost:5174:
npm run test:ui
# Para outro endereço:
FRONTEND_TEST_URL=http://localhost:5175 npm run test:ui
```

O teste de interface usa Playwright e respostas HTTP simuladas. Verifica alternância, persistência após recarregar, ausência de mudança ao falhar um convite e navegação móvel sem overflow. Não cria nem altera dados reais.

Também foi realizada navegação de leitura pelas nove telas com o acesso de Sofia, incluindo troca para a família compartilhada e conferência de seus dois integrantes. Esta etapa não exige migração de banco. A sessão de teste foi separada da sessão do usuário.

Ainda não há envio automático de convites por e-mail nem notificações push. O convite precisa ser compartilhado por quem o cria. Os formulários financeiros existentes foram preservados; esta alteração reorganiza a estrutura comum e o fluxo de família, sem redesenhar cada formulário individual.
