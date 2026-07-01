# Orientações do projeto AERI

## Idioma e versionamento

- Responder e documentar o projeto em português.
- Escrever mensagens de commit em português.
- Não criar commit nem enviar alterações ao GitHub sem ordem expressa do usuário.
- Não versionar `__pycache__`, arquivos temporários ou artefatos intermediários.

## Análise de matrículas

- Preservar o comportamento já validado da análise de ônus e cancelamentos.
- Diferenciar CPF (11 dígitos) de CNPJ (14 dígitos) na apresentação.
- Separar cônjuges expressamente descritos como adquirentes, mantendo nome e documento próprios.
- Processar retificações posteriores de CPF, substituindo números incompletos do ato inicial.
- Reconhecer percentuais descritos como "parte correspondente a X%".
- Remover qualificadores como "herdeira filha" e "herdeiro filho" do nome apresentado.
- Tratar consolidação da propriedade fiduciária como transferência integral ao credor fiduciário indicado.
- Quando houver leilões negativos e extinção da dívida originária sem referência expressa ao registro, cancelar a alienação fiduciária ativa mais recente correspondente.
- Toda nova regra deve ser testada contra os exemplos anteriores para evitar regressões.

## Módulo INCRA

- Extrair do Relatório Rural em PDF o número do protocolo e o tipo do ato.
- Agrupar ocorrências repetidas da mesma combinação de protocolo e tipo de ato.
- Classificar os resultados em Comunicar, Revisar e Fora das hipóteses.
- Classificar georreferenciamento como hipótese de comunicação por alteração territorial ou desmembramento.
- Manter a possibilidade de copiar a lista e exportar CSV.
- O módulo Rotina - Intimação controla protocolo, credor, devedor, último andamento e conferências diárias.
- Preservar os estados visuais verde, amarelo, vermelho e cinza e a importação/exportação CSV.
- Persistir usuários, intimações e conferências no Postgres configurado no Vercel; não usar `localStorage` para dados operacionais.
- Manter o acesso protegido por sessão e nunca armazenar senhas em texto puro.

## Verificação

- Antes de concluir alterações no analisador, executar o caso novo e os casos de regressão disponíveis.
- Para mudanças visuais, verificar a interface no navegador.
- Para PDFs e documentos, renderizar e conferir visualmente antes da entrega.
