# Consulta assistida ao Ofício Eletrônico

## Revisão solicitada: consulta direta

A versão de importação de arquivos foi rejeitada pelo responsável. Substituir
o caminho principal por botão no Analisador, fila no backend e conector local
pareado. O conector faz apenas conexões HTTPS de saída para a origem fixada;
não abrir servidor localhost/CORS nem enviar cookie do Ofício ao backend.
Pareamento único de 5 minutos, token de 30 dias revogável e limitado ao usuário
e serventia. Guardar a credencial local com DPAPI do Windows, nunca em claro.
Um trabalho expira em 5 minutos, só é entregue ao conector pareado e só aceita
um resultado completo; preservar a tabela externa separada. O trabalhador
mantém uma conexão Chrome por execução, sem navegação ou abertura de INs.
Usar o total histórico anterior como piso, permitindo novos pedidos sem
digitação diária do total. Na primeira configuração exigir piso histórico
explicitamente informado em OFICIO_TOTAL_HISTORICO_MINIMO.

Etapas: testes de entrada/autenticação e posse do trabalho; fila/pairing;
conector persistente sem arquivos de captura; botão/polling/erros/logout na
mesa; testes sintéticos ponta a ponta e documentação da ativação única.
Não publicar nem acessar banco de produção nesta etapa.

## Objetivo e limites

Conector local de consulta usando o transporte Chrome MCP fixado pelo
reverse-api-engineer 0.15.0. Sem agente autônomo, HAR, cookies exportados,
mensagens, anexos, pagamentos ou alterações no Ofício. Não é API oficial ONR.
O operador prepara a listagem completa no portal; o conector lê essa listagem
e sua paginação na mesma conexão. A permissão do Chrome continua obrigatória.

Primeira entrega: arquivo JSON minimizado, importado pela sessão normal do
Analisador. Isso evita abrir um serviço local acessível por sites e evita
criar outra credencial de acesso ao banco. Não há sincronização em segundo
plano, nem promessa de captura de notificações/mensagens.

## Arquitetura

- `scripts/oficio/`: coletor JavaScript determinístico e CLI Python isolada.
- `backend/app/servicos/oficio_consultas.py`: contrato estrito de captura.
- `backend/app/rotas/oficio_consultas.py`: importação com permissão/CSRF,
  leitura com permissão, auditoria mínima, isolamento pelo cartório configurado.
- Migração 067: somente a captura mais recente por cartório, independente
  dos cadastros, conferências, fases e vínculos RTD já existentes.
- Mesa de conferência: importar captura e ver status externo por IN, com
  data da consulta e aviso explícito de que status externo não é tarefa interna.

Variável obrigatória `OFICIO_CARTORIO_ID`; não presumir Morrinhos em outra
instalação. Importação não cria/exclui INs nem registra conferência. Capturas
incompletas, antigas, de outro cartório ou com duplicidade são recusadas.
Capturas anteriores não podem substituir uma mais recente (controle atômico).

## Plano de execução

1. Testar contrato: formato, campos permitidos, datas, cartório, contagens,
   páginas, duplicidades e ausência de dados pessoais extras.
2. Implementar contrato, persistência e rotas protegidas. Testar sem banco real.
3. Extrair coletor limpo dos testes já realizados; testar paginação com HTML
   sintético, mudança de total, filtros ativos, host e cartório errados.
4. Integrar painel branco à mesa, sem automatizar confirmação ou sobrescrever
   andamentos. Testar no navegador com respostas simuladas.
5. Documentar operação, limites e instalação isolada. Não fazer deploy.

## Critérios de aceite

Somente seis campos da listagem, captura completa validada, mesma serventia,
sessão/CSRF/permissões preservadas, nenhuma mutação nas tabelas operacionais,
falha de consulta visível (não disfarçada de ausência de IN), sem logs de
conteúdo do portal. Testes não consultam banco ou Ofício de produção.
