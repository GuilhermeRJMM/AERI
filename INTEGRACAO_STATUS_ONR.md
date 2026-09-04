# Integração do status do Ofício Eletrônico

O AERI recebe atualizações do `status.onr.org.br` e apresenta a situação do Ofício Eletrônico no cabeçalho.

## Configuração

1. Acesse `https://status.onr.org.br/subscribe/webhook`.
2. Informe `https://aeri-two.vercel.app/api/webhooks/onr` como endpoint.
3. Selecione apenas `Oficio Eletronico` e `API Oficio Eletrônico - Registro de Imoveis`.
4. Informe um e-mail institucional para alertas de falha de entrega.
5. Ao concluir, a página gera o segredo do webhook — 64 caracteres hexadecimais.
   Copie-o: é a única vez que ele aparece.
6. No Vercel, cadastre `ONR_WEBHOOK_SECRET` com esse valor, em Production.

O segredo é compartilhado: serve para o ONR assinar e para o AERI conferir. Se a
página oferecer um campo para você informar o seu, tanto faz qual dos dois lados
o gera — o que não pode é divergir. Antes, este documento mandava gerar o segredo
primeiro e colá-lo na página; a página passou a gerá-lo, e seguir a ordem antiga
deixava o webhook assinando com um segredo e o AERI conferindo com outro.

Ele só é lido onde o webhook chega, que é o Vercel. Não precisa entrar no `.env`
da serventia nem na máquina do executor.

O endpoint valida `x-instatus-webhook-signature` com HMAC-SHA256, ignora eventos repetidos e persiste o histórico no Postgres.
Enquanto o webhook não estiver configurado, e como contingência a cada cinco minutos, o AERI consulta a API pública `https://status.onr.org.br/v3/components.json`.

## Estados apresentados

- Verde: operacional.
- Amarelo: manutenção ou desempenho degradado.
- Vermelho: interrupção parcial ou total.
- Cinza: nenhum status recebido ou estado desconhecido.

O navegador consulta o estado armazenado pelo AERI a cada minuto. Não são armazenadas credenciais do Ofício Eletrônico.
