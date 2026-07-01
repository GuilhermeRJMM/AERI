# Arquitetura do AERI

## Visão geral

O AERI é dividido em quatro camadas principais:

- `backend/app/rotas`: endpoints HTTP organizados por domínio.
- `backend/app/servicos`: coordenação dos casos de uso, sem responsabilidade de interface.
- `backend/app`: regras registrais e infraestrutura compartilhada.
- `backend/static/js`: módulos da interface, sem JavaScript de negócio dentro do HTML.

## Backend

### Rotas

- `rotas/autenticacao.py`: login, logout e consulta de sessão.
- `rotas/analisador.py`: entrada HTTP da análise de matrícula.
- `rotas/incra.py`: recebimento e classificação do Relatório Rural.
- `rotas/intimacoes.py`: operações da rotina diária de intimações.

As rotas devem traduzir HTTP para chamadas de serviço. Regras de negócio não devem ser implementadas diretamente nessa camada.

### Serviços e regras

- `servicos/analise_matricula.py`: orquestra parser, classificação, cancelamentos e cadeia dominial.
- `servicos/intimacoes.py`: valida e apresenta os dados de intimações.
- `regras.py`, `cancelamentos.py` e `proprietarios.py`: regras registrais puras.
- `incra.py`: extração e enquadramento dos protocolos rurais.

### Banco de dados

As alterações estruturais ficam em `backend/app/migrations` e são aplicadas em ordem alfabética. Cada arquivo aplicado é registrado em `migracoes_aeri`, impedindo repetição.

Novas mudanças de estrutura devem ser adicionadas em um novo arquivo SQL numerado. Migrações já publicadas não devem ser editadas.

## Interface

- `app.js`: inicialização da aplicação.
- `autenticacao.js`: sessão e login.
- `navegacao.js`: troca entre módulos.
- `analisador.js`: análise e apresentação da matrícula.
- `incra.js`: upload, filtros e exportação rural.
- `intimacoes.js`: rotina diária, formulários e CSV.
- `api.js`: tratamento comum das respostas HTTP.
- `util.js`: funções compartilhadas de apresentação e download.

Eventos são registrados pelos módulos. Não devem ser adicionados atributos `onclick`, `oninput`, `onchange` ou `onsubmit` ao HTML.

## Convenções

- Responder e documentar em português.
- Manter regras registrais independentes de FastAPI, banco e HTML.
- Criar caso de regressão antes de alterar uma regra validada.
- Usar a API como única fronteira para dados operacionais do navegador.
- Nunca persistir dados operacionais em `localStorage`.
