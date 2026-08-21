# Arquitetura do AERI

## Visão geral

O AERI é dividido em quatro camadas principais:

- `backend/app/rotas`: endpoints HTTP organizados por domínio.
- `backend/app/servicos`: coordenação dos casos de uso, sem responsabilidade de interface.
- `backend/app`: regras registrais e infraestrutura compartilhada.
- `backend/static/js`: módulos da interface, sem JavaScript de negócio dentro do HTML.

O sistema possui atualmente seis módulos funcionais:

- **Ônus & Matrícula**: classificação dos atos e cálculo da cadeia dominial.
- **INCRA**: extração e classificação de protocolos do Relatório Rural.
- **Informar Custas**: extração dos pedidos de penhor e alienação de grãos do relatório PDF, organização por situação e separação entre filas em andamento e finalizada.
- **Rotina - Intimação**: controle de intimações, andamento interno, conferência diária e importação/exportação CSV.
- **Usuários e Acessos**: gestão administrativa de contas, perfis e consulta da auditoria de segurança.
- **Buscas e auditoria registral**: uma única leitura do texto alimenta o índice de titulares e valida ônus, cadeia dominial e dados do imóvel.

## Backend

### Rotas

- `rotas/autenticacao.py`: login, logout e consulta de sessão.
- `rotas/analisador.py`: entrada HTTP da análise de matrícula.
- `rotas/incra.py`: recebimento e classificação do Relatório Rural.
- `rotas/custas.py`: prévia segura do relatório, importação idempotente e movimentação dos pedidos de custas.
- `rotas/intimacoes.py`: operações da rotina diária de intimações.

As rotas devem traduzir HTTP para chamadas de serviço. Regras de negócio não devem ser implementadas diretamente nessa camada.

### Serviços e regras

- `servicos/analise_matricula.py`: orquestra o contrato versionado da análise.
- `servicos/auditoria_integrada.py`: resume a auditoria independente e controla a revisão complementar dos casos críticos.
- `servicos/fontes_juridicas.py`: extrai, segmenta e pesquisa a base normativa e executa automaticamente o agente jurídico com análise própria e citações validadas.
- `analise/onus.py`, `analise/cadeia.py` e `analise/imovel.py`: fachadas por domínio sobre as regras registrais validadas.
- `analise/contrato.py`: versão do motor, hash determinístico e metadados de privacidade.
- `analise/evidencias.py`: vincula o resultado à origem e a um trecho curto de evidência.
- `servicos/intimacoes.py`: valida e apresenta os dados de intimações.
- `regras.py`, `cancelamentos.py` e `proprietarios.py`: regras registrais puras.
- `incra.py`: extração e enquadramento dos protocolos rurais.
- `servicos/custas.py`: leitura do PDF e normalização de pedido, pessoa, documento, modalidade, produto e safra.

### Banco de dados

As alterações estruturais ficam em `backend/app/migrations` e são aplicadas em ordem alfabética. Cada arquivo aplicado é registrado em `migracoes_aeri`, impedindo repetição.

Novas mudanças de estrutura devem ser adicionadas em um novo arquivo SQL numerado. Migrações já publicadas não devem ser editadas.

As intimações são persistidas em `intimacoes_aeri`. O andamento informado pelo usuário é independente da conferência diária: uma conferência pode manter o andamento anterior ou registrar um novo andamento e sua data.

Cada mudança operacional também gera evento append-only em `eventos_intimacao_aeri`. A tabela preserva o tipo, autor, instante e campos afetados, inclusive quando a intimação é excluída, sem copiar credor, devedor ou conteúdo documental para o evento.

Conferências incorretas não criam regras automaticamente. Elas entram em `divergencias_analise_aeri` para revisão administrativa. O registro guarda apenas matrícula, versão/hash do resultado, partes indicadas, contagens e comentário; o texto integral não é persistido.

A auditoria registral integrada reaproveita o texto que já foi consultado para a indexação de titulares. O banco guarda somente hashes, vereditos, confianças, contagens e alertas estruturados. A revisão complementar é opcional, possui limite diário desativado por padrão e recebe documentos previamente mascarados.

A base jurídica usa `fontes_juridicas_aeri` e `trechos_juridicos_aeri`. Os documentos são divididos em trechos com página e hash de origem; a pesquisa textual ocorre no Postgres. `analises_juridicas_aeri` guarda apenas a análise estruturada, as referências e os hashes do resultado e da base. O texto integral da matrícula não é persistido. Uma análise anterior só é reutilizada quando matrícula, resultado determinístico e conjunto de fontes continuam exatamente iguais.

O módulo Informar Custas persiste sua fila em `custas_livro3_aeri`. O PDF é processado somente em memória, pedidos já existentes não são sobrescritos pela importação e cada alteração, finalização ou reabertura gera um evento em `eventos_custas_livro3_aeri`.

## Integrações externas

### Central ONRTDPJ — planejada

A integração automática com a Central ONRTDPJ ainda não está implementada. O desenho validado prevê:

- duas novas colunas visíveis na Rotina - Intimação: **Protocolo RTD** e **Andamento RTD**;
- vinculação manual do protocolo RTD à intimação quando o andamento interno for “Aguardando diligências do RTD”;
- consulta incremental da situação dos pedidos pela API oficial;
- atualização automática preferencialmente a cada hora;
- armazenamento do token somente em variável de ambiente da Vercel;
- persistência do resultado e do horário da última sincronização no Postgres;
- sincronização idempotente, com trava contra execuções simultâneas e registro de falhas sem exposição do token.

O detalhamento funcional, os requisitos de acesso já confirmados e as pendências a validar com a Central estão em [INTEGRACAO_ONRTDPJ.md](INTEGRACAO_ONRTDPJ.md).

## Interface

- `app.js`: inicialização da aplicação.
- `autenticacao.js`: sessão e login.
- `navegacao.js`: troca entre módulos.
- `analisador.js`: análise e apresentação da matrícula.
- `incra.js`: upload, filtros e exportação rural.
- `custas.js`: prévia da importação, planilha operacional, filtros, edição e movimentação entre filas.
- `intimacoes.js`: rotina diária, formulários e CSV.
- `api.js`: tratamento comum das respostas HTTP.
- `util.js`: funções compartilhadas de apresentação e download.

Eventos são registrados pelos módulos. Não devem ser adicionados atributos `onclick`, `oninput`, `onchange` ou `onsubmit` ao HTML.

Quando executado dentro de iframe, o modo incorporado oculta a navegação duplicada e ocupa a largura do hospedeiro. Ele não substitui a autenticação do AERI; SSO permanece fora desta versão.

## Contrato e regressão do analisador

O retorno inclui `meta`, `resultado_hash` e `evidencias`, sem alterar os campos legados. Campos aplicáveis que não foram encontrados aparecem em `imovel.campos_aplicaveis` como **NÃO CONSTA**. Endereço urbano não é aplicado a imóvel rural e cadastros rurais não são aplicados a urbano.

O corpus sintético em `tests/corpus_ouro/manifest.json` cobre comportamentos essenciais sem expor matrículas reais. `scripts/comparar_resultados_analise.py` compara duas saídas JSONL antes de uma publicação. A auditoria completa continua sendo uma rotina externa e retomável; não deve ser executada dentro de uma função Vercel.

## Convenções

- Responder e documentar em português.
- Manter regras registrais independentes de FastAPI, banco e HTML.
- Criar caso de regressão antes de alterar uma regra validada.
- Usar a API como única fronteira para dados operacionais do navegador.
- Nunca persistir dados operacionais em `localStorage`.
- Nunca enviar tokens de integrações externas ao navegador nem registrá-los em logs.
