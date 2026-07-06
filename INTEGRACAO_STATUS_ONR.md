# Integração do status do Ofício Eletrônico

O AERI recebe atualizações do `status.onr.org.br` e apresenta a situação do Ofício Eletrônico no cabeçalho.

## Configuração

1. Gere um segredo aleatório forte, sem reutilizar senhas do AERI.
2. No Vercel, cadastre `ONR_WEBHOOK_SECRET` com esse segredo.
3. Acesse `https://status.onr.org.br/subscribe/webhook`.
4. Informe `https://aeri-two.vercel.app/api/webhooks/onr` como endpoint.
5. Use o mesmo segredo no campo de segredo do webhook.
6. Selecione apenas `Oficio Eletronico` e `API Oficio Eletrônico - Registro de Imoveis`.
7. Informe um e-mail institucional para alertas de falha de entrega.

O endpoint valida `x-instatus-webhook-signature` com HMAC-SHA256, ignora eventos repetidos e persiste o histórico no Postgres.
Enquanto o webhook não estiver configurado, e como contingência a cada cinco minutos, o AERI consulta a API pública `https://status.onr.org.br/v3/components.json`.

## Estados apresentados

- Verde: operacional.
- Amarelo: manutenção ou desempenho degradado.
- Vermelho: interrupção parcial ou total.
- Cinza: nenhum status recebido ou estado desconhecido.

O navegador consulta o estado armazenado pelo AERI a cada minuto. Não são armazenadas credenciais do Ofício Eletrônico.
