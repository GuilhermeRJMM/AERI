# L3BOT → Informar Custas: certidão respondida

Atualização baseada no `L3BOT.zip` fornecido em 16/09/2026.

## Instalação

1. Publique primeiro a atualização do AERI. A migração
   `049_certidoes_respondidas_l3bot.sql` é aplicada pelo mecanismo já existente.
2. Encerre o L3BOT e guarde uma cópia da pasta atual. O ZIP original também permanece intacto.
3. Copie `l3bot.py` e `l3bot_aeri.py` deste pacote para a pasta onde está o
   `l3bot.py` utilizado pelo painel, substituindo somente esses arquivos.
   A pasta `tests` contém os testes atualizados e pode ser copiada junto.
4. Abra o L3BOT normalmente. Nenhuma biblioteca nova precisa ser instalada.

A integração usa a variável `AERI_CUSTAS_API_TOKEN`, quando definida na máquina.
Caso contrário, reutiliza a chave da instalação existente em
`automacoes/custas/tri7_custas/api_catalog.py` (`AERI_ACCESS_KEY`). Ela precisa
corresponder à chave já configurada no AERI. O pacote de atualização não contém
essa chave, arquivos de configuração privada nem os logs da instalação original.

Se a instalação recebeu mudanças depois do ZIP enviado, não substitua o arquivo
principal sem incorporar essas mudanças. O `l3bot.patch` versionado no AERI
permite revisar as alterações específicas.

## Funcionamento

O robô prepara um evento local antes de clicar em enviar. O evento só fica
liberado para a API depois de reconhecer `Anexo enviado com sucesso.`, aceitar
a finalização no SAEC e verificar que não há diálogos visíveis pendentes.
O intento de envio continua separado, para impedir a repetição da certidão
quando houver uma falha depois do clique.

A confirmação é gravada em `dados/checkpoints/respostas-aeri.sqlite3` e enviada
em uma thread separada. Falhas de rede, indisponibilidade do servidor e recusa
temporária da credencial mantêm o evento na fila, com novas tentativas entre
30 segundos e 5 minutos enquanto o robô estiver aberto. Ao reiniciar, ele
retoma a fila. Essa rotina nunca reenvia a certidão ao SAEC.

No AERI, o pedido existente recebe `status=RESPONDIDO`, `finalizado=true` e data
de finalização. O histórico registra L3BOT, identificador do evento e horário
informado pelo robô. Resultado da busca, registros encontrados, valores e
demais dados não são recalculados. A tela já se atualiza a cada 30 segundos
enquanto o módulo está aberto e visível, e ao retornar à aba do navegador.

Eventos repetidos devolvem o recibo original, inclusive depois de uma reabertura
manual. Um evento antigo que chega após a reabertura não finaliza o pedido.
Pedidos devolvidos, sem pagamento ou finalizados em outra situação exigem
conferência. Pedidos inexistentes no Informar Custas são ignorados, sem criação
automática. Se forem importados posteriormente, precisam de tratamento manual.

Se o robô for encerrado entre o envio e a comprovação de sucesso, o evento fica
como `PROVA_PENDENTE`. Ele não será considerado respondido automaticamente.
Confira o SAEC e, se apropriado, finalize manualmente no AERI.

Para consultar a fila sem alterar dados, execute na pasta do L3BOT:

```text
python l3bot_aeri.py
```

Estados: `PROVA_PENDENTE` (conferir envio), `PENDENTE` (aguardando API),
`CONFIRMADO` (recebido pelo AERI), `IGNORADO` (pedido ausente),
`REVISAR` (conflito ou evento recusado). Não apague o arquivo SQLite para
resolver falhas de conexão; ele contém as confirmações ainda não entregues.

## Contrato da API

```http
POST /api/integracoes/informar-custas/respondida
Authorization: Bearer <mesma credencial da integração de custas>
Content-Type: application/json
```

```json
{
  "eventoId": "fdb7e083-e467-4c05-9f9a-d873ce6fcd19",
  "pedido": "S26081052542D",
  "respondidoEm": "2026-09-16T15:00:00+00:00",
  "confirmacao": "ENVIO_E_FINALIZACAO_SAEC_CONFIRMADOS"
}
```

O identificador e a data são gerados uma vez e preservados nas novas tentativas.
O computador deve estar com o relógio correto; datas sem fuso ou mais de cinco
minutos no futuro são recusadas. A confirmação é a declaração autenticada do
robô baseada na tela da Tri7; não é uma consulta independente ao servidor SAEC.

```json
{
  "eventoId": "fdb7e083-e467-4c05-9f9a-d873ce6fcd19",
  "pedido": "S26081052542D",
  "situacao": "CONFIRMADO"
}
```

Situações: `CONFIRMADO`, `JA_RESPONDIDO`, `NAO_ENCONTRADO` e `CONFLITO`.
O cliente confere identificador, pedido e situação; HTTP 200 sozinho não basta.
Sem credencial válida: 401. Payload inválido: 422. Mesmo identificador com outro
pedido/data: 409. O endpoint `/confirmar` de custas informadas segue independente.

Os recibos são gravados atomicamente com a finalização. A chave primária do
evento trata entregas simultâneas; o bloqueio do pedido serializa suas alterações.
Não é necessário login de navegador ou CSRF neste endpoint autenticado por Bearer.

## Validação e primeira utilização

Os testes automatizados usam SQLite local, transporte simulado, diálogos
simulados e a API FastAPI sem banco de produção. Nenhuma certidão real foi emitida
durante a implementação. Após publicar e instalar, acompanhe um pedido existente:
conclua-o normalmente pelo L3BOT, aguarde a mensagem de confirmação do AERI e
confira a aba Finalizados e o histórico. Se não aparecer, consulte a fila local.

Para voltar ao comportamento anterior, restaure o `l3bot.py` do backup com o robô
fechado. Preserve a fila para conferência. A reversão do programa não desfaz
pedidos que já foram finalizados; esses podem ser reabertos no AERI.

SHA-256 do `l3bot.py` original fornecido:
`6519fe446bb34b6d33576fd95f3f3e87c7768fcfe82eb5d98abb23133b46191a`.
