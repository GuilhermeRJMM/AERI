# Integração do AERI com a Central ONRTDPJ

## Situação

Documento de planejamento validado em **03/07/2026**. A integração descrita aqui ainda não está implementada.

Objetivo: eliminar a consulta manual dos pedidos enviados ao RTD. O AERI deverá associar o protocolo da Central a uma intimação, consultar automaticamente a situação do pedido e apresentar o retorno na Rotina - Intimação.

## O que foi confirmado na documentação oficial

A Central mantém uma API documentada em Swagger, denominada **Central RTDPJ ONRTDPJ API**.

- A API é oferecida a **clientes pessoa jurídica** para integração com a Central.
- É necessário possuir acesso ao ambiente de produção da Central.
- Caso ainda não exista acesso, a orientação oficial é cadastrar uma pessoa jurídica e uma pessoa física antes de solicitar o token.
- O token deve ser solicitado pelo e-mail `atendimento@onrtdpj.org.br`, informando o CNPJ do cliente que fará a integração.
- A autenticação utiliza o cabeçalho HTTP `Authorization`.
- `GET /api/pedido/{protocolo}` retorna os detalhes e a situação de um pedido.
- `GET /api/pedido/atualizacoes/{data}` retorna pedidos alterados depois de uma data.
- A resposta oficial contém, entre outros, os campos `Protocolo`, `Situacao`, `SituacaoId` e `DataSituacao`.

Fontes oficiais:

- [Swagger da API Central ONRTDPJ](https://apicentral.rtdbrasil.org.br/swagger/ui/index)
- [Ambiente de produção da Central](https://www.rtdbrasil.org.br/autenticacao/login)
- [Site institucional e contatos do ONRTDPJ](https://onrtdpj.org.br/)

## Avaliação dos requisitos apresentados

### 1. Possuir cadastro ativo na Central ONRTDPJ

**Confirmado com ajuste.** A documentação exige acesso à Central em produção e orienta o cadastro de pessoa jurídica e pessoa física quando o cliente ainda não possui acesso. Ela não afirma que o solicitante precisa ser tabelião; descreve a integração como disponível a clientes pessoa jurídica.

Deve-se confirmar com o suporte se o CNPJ do Registro de Imóveis possui acesso aos mesmos pedidos que hoje são consultados manualmente e se todos os protocolos pretendidos pertencem a essa conta.

### 2. Solicitar acesso à API

**Confirmado parcialmente.** A solicitação do token por e-mail é oficial e deve informar o CNPJ do cliente integrador.

Nome do cartório, nome do responsável, e-mail de contato e objetivo da integração são informações úteis e recomendáveis na solicitação, mas não aparecem como campos obrigatórios na documentação pública consultada.

### 3. Solicitar o token de acesso

**Confirmado.** O token é necessário e deve ser enviado no cabeçalho `Authorization`.

O formato exato do valor — token puro ou prefixado — deve ser confirmado com o suporte no momento da liberação. O token não deverá ser enviado por mensagem comum ao desenvolvedor nem incluído no GitHub. A forma recomendada é cadastrá-lo diretamente como segredo de produção na Vercel, sob o nome `ONRTDPJ_API_TOKEN`.

### 4. Autorizar a integração

**Não confirmado como etapa separada.** A documentação pública não descreve um termo adicional de autorização. A emissão do token pode já representar a autorização técnica, mas isso deve ser perguntado à Central.

### 5. Disponibilizar informações técnicas

**Parcialmente confirmado.** São indispensáveis:

- token da API;
- confirmação da URL/base de produção autorizada;
- confirmação do formato do cabeçalho `Authorization`;
- confirmação de quais pedidos o token pode consultar.

Não foi localizado ambiente oficial de homologação na documentação pública. Também devem ser solicitados ao suporte:

- ambiente de homologação, caso exista;
- limite de requisições;
- formato e fuso horário aceitos pelo endpoint incremental;
- política de expiração e renovação do token;
- códigos de erro e comportamento em indisponibilidade;
- confirmação de que a consulta horária é permitida.

## Alterações previstas no AERI

### Interface

Adicionar à tabela da Rotina - Intimação:

1. **Protocolo RTD** — protocolo retornado ou informado a partir da Central.
2. **Andamento RTD** — valor mais recente de `Situacao` retornado pela API.

Ao registrar o andamento interno “Aguardando diligências do RTD”, o AERI deverá solicitar o protocolo RTD. A intimação continuará possuindo separadamente:

- andamento interno do Ofício Eletrônico;
- protocolo da Central RTD;
- andamento informado pela Central RTD.

### Banco de dados

Criar uma nova migração, sem alterar migrações já publicadas. Campos mínimos sugeridos em `intimacoes_aeri`:

- `protocolo_rtd VARCHAR(...)`;
- `andamento_rtd VARCHAR(...)`;
- `data_andamento_rtd TIMESTAMPTZ`;
- `rtd_consultado_em TIMESTAMPTZ`;
- `rtd_erro_sincronizacao TEXT`.

As duas primeiras colunas são exibidas ao usuário. As demais permitem auditoria, diagnóstico e repetição segura da sincronização.

### Sincronização

Fluxo recomendado:

1. Um agendador protegido chama um endpoint interno do AERI.
2. O endpoint adquire uma trava no Postgres para impedir duas sincronizações simultâneas.
3. O AERI consulta `GET /api/pedido/atualizacoes/{data}` usando a última data sincronizada com sucesso.
4. Para cada protocolo vinculado, atualiza `andamento_rtd` e `data_andamento_rtd`.
5. Registra o horário da consulta e avança o marcador incremental somente após sucesso.
6. Em falha, mantém o último andamento conhecido e registra uma mensagem técnica sem token ou dados sensíveis.

A operação deve ser idempotente: executar novamente o mesmo intervalo não pode duplicar dados nem apagar o último estado válido.

## Atualização de hora em hora e Vercel

O Cron da Vercel aceita agendamento horário (`0 * * * *`) somente nos planos **Pro** e **Enterprise**. No plano **Hobby**, trabalhos agendados podem executar no máximo uma vez por dia; uma expressão horária faz o deploy falhar.

Opções:

- **Vercel Pro:** usar Cron Job horário, protegido por `CRON_SECRET`.
- **Vercel Hobby:** usar um agendador externo confiável para chamar o endpoint protegido a cada hora.
- **Sem exigência horária:** executar diariamente no próprio plano Hobby.

Fontes oficiais da Vercel:

- [Limites e preços de Cron Jobs](https://vercel.com/docs/cron-jobs/usage-and-pricing)
- [Gerenciamento e proteção com CRON_SECRET](https://vercel.com/docs/cron-jobs/manage-cron-jobs)

## Segurança e proteção de dados

- Guardar `ONRTDPJ_API_TOKEN` e `CRON_SECRET` exclusivamente nas variáveis de ambiente da Vercel.
- Nunca incluir tokens em código, banco, CSV, HTML, JavaScript, logs ou GitHub.
- Fazer as consultas somente pelo backend; o navegador nunca acessará diretamente a Central.
- Aplicar tempo limite, retentativas controladas e mascaramento de erros.
- Restringir a edição do protocolo RTD a usuários autenticados.
- Manter histórico mínimo das mudanças de situação para rastreabilidade.
- Definir retenção e acesso aos dados conforme as responsabilidades do cartório e a LGPD.

## Texto sugerido para solicitar a liberação

> Assunto: Solicitação de token para integração com a API Central ONRTDPJ
>
> Solicitamos a liberação de acesso à API da Central ONRTDPJ para integração com o sistema interno AERI, destinado ao acompanhamento dos pedidos de notificação enviados ao RTD.
>
> CNPJ da instituição integradora: [CNPJ]
>
> Nome da serventia/instituição: [NOME]
>
> Responsável: [NOME E FUNÇÃO]
>
> E-mail e telefone: [CONTATO]
>
> Pedimos também a confirmação da URL de produção, formato do cabeçalho de autenticação, eventual ambiente de homologação, limites de requisição, escopo dos pedidos acessíveis e política de renovação do token.

## Critérios para iniciar a implementação

A implementação deve começar somente após receber:

- token válido cadastrado como segredo na Vercel;
- confirmação de que o token acessa os protocolos utilizados pelo cartório;
- resposta sobre homologação, limites e formato de autenticação;
- definição do agendador horário: Vercel Pro ou serviço externo;
- pelo menos um protocolo de teste sem dados sensíveis, ou autorizado para homologação.
