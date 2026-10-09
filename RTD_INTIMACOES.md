# Diligências RTD nas intimações

Integração de cliente ONRTDPJ para consulta de andamentos e, quando solicitado manualmente, cadastro de uma nova notificação. Não paga boletos nem altera o andamento interno do AERI.

## Operação

- A tarefa Windows **AERI RTD** consulta mudanças a cada 5 minutos, independentemente do navegador e do executor operacional.
- A máquina precisa estar ligada, conectada à rede e com a sessão do usuário iniciada. O painel informa atraso após 10 minutos sem concluir uma consulta.
- Na rotina, o cartão **Central RTD** mostra quantos pedidos têm atualizações ainda não conferidas, o estado da fila e o horário do último sucesso. **Ver atualizações** reúne os pedidos novos de todas as fases e os ordena primeiro.
- A tabela identifica separadamente a **Situação AERI**, o **Andamento interno do AERI** e o **Andamento da Central RTD**. A atualização externa não muda automaticamente a fase ou a conferência interna.
- Em **Detalhes**, “O que mudou” compara os dados da consulta mais recente com a anterior. O histórico mostra as mudanças campo a campo; **Marcar atualização como conferida** limpa o destaque somente para o usuário atual e para a versão que ele viu.
- Na primeira execução é percorrido o histórico paginado. Os PDFs são processados em lotes de dois, numa fila persistida no Postgres. Fechar a tela não interrompe o trabalho.
- Vínculo por IN exato extraído do PDF. Um IN pode ter várias diligências. Ausência, ambiguidade ou conflito ficam visíveis na revisão, sem escolher uma correspondência aproximada.
- Destinatários são identificados no vocativo do ofício. Somente lacunas explícitas de importação são preenchidas; nomes editados pela equipe não são sobrescritos. A origem automática fica registrada no banco e na auditoria.
- Orçamento, situação, resultado/data da diligência e histórico RTD ficam separados do andamento, fase e finanças internos.
- Novidades aparecem primeiro na lista; o botão **Marcar atualização como conferida** vale apenas para o usuário e a versão exibida. Uma alteração concorrente permanece destacada.
- Documentos protegidos, digitalizados sem texto, grandes ou sem IN identificável ficam pendentes de revisão. Esta integração não executa OCR.

## Enviar uma notificação pelo AERI

- Em **Detalhes** de uma intimação da fase inicial, **Preparar notificação** abre o fluxo baseado na rotina gravada no RTDPJ: escolher a serventia, conferir remetente e destinatários, selecionar documentos e revisar antes do envio.
- O formulário pesquisa os cartórios disponíveis na Central por estado e cidade; o servidor valida novamente a seleção antes do envio.
- O botão **Abrir pasta deste IN** aciona o aplicativo local de pastas. O operador ainda precisa selecionar o arquivo no navegador; por segurança, a página não pode anexar arquivos da unidade `T:` silenciosamente.
- Para o destinatário, cada endereço é uma entrada separada em `Notificados`. Se a mesma pessoa tiver dois endereços, **Adicionar outro endereço à mesma pessoa** repete nome e CPF/CNPJ e deixa o endereço vazio para conferência. Pessoas diferentes são incluídas separadamente. A opção de entrega fica marcada e o servidor rejeita envio a terceiros, conforme o procedimento informado.
- O credor vem preenchido com o nome já registrado na intimação; confirme o CNPJ nos documentos. O AERI monta a frase “Recebido em nome de: …, inscrita no CNPJ: …”.
- Conforme o procedimento deste cartório, o envio usa somente `Documentos RTD.pdf`, sem requerimento extra. Antes do envio, confirma que o documento principal reúne, na ordem, o ofício contra-fé, recibo do protocolo RGI, ofício do credor com etiqueta eletrônica e planilha de projeção, e que esse PDF foi assinado digitalmente depois da combinação. O AERI não valida criptograficamente a assinatura.
- A Central recebe o PDF por `POST /api/arquivo` e os dados por `POST /api/notificacao`. O arquivo pode ter até 4,3 MB, abaixo do limite de requisição da hospedagem.
- O envio só acontece ao clicar em **Enviar notificação** depois de marcar as confirmações. Se a resposta da Central ficar incerta, o AERI marca para conferência; não se deve reenviar às cegas.
- Os campos e formatos enviados seguem o [Swagger oficial da Central RTDPJ](https://apicentral.rtdbrasil.org.br/swagger/ui/index).
- O manual do cliente informa que o token é gerado na Central ONRTDPJ em **Serviços > Integração** e enviado no cabeçalho `Authorization: Bearer`. O trecho do manual que mostra `POST /api/pedido` trata especificamente do envio de pedido de registro; o formulário de notificação usa o endpoint separado `POST /api/notificacao`, conforme a operação de cadastro de notificação no Swagger.
- O manual também lista homologação (`apicentral.fpsti.com.br`) e produção (`apicentral.rtdbrasil.org.br`). `AERI_RTD_NOTIFICACAO_AMBIENTE` seleciona o ambiente somente para o formulário de envio; a sincronização dos pedidos existentes continua em produção. Por segurança, o envio usa homologação se a variável não estiver definida; produção exige configuração explícita. Envios de homologação ficam identificados e não entram na fila de produção.
- O protocolo retornado é vinculado à intimação selecionada e entra na fila de acompanhamento já existente. Nenhum andamento interno do AERI é alterado.
- O AERI registra o estado e o protocolo, mas não guarda cópia dos endereços, documentos pessoais ou do PDF enviado. A Central é responsável pela guarda da solicitação.
- O anexo deve ser PDF. O AERI limita o arquivo a **4,3 MB**, respeitando o limite de requisição da hospedagem Vercel.
- A credencial nunca vai ao navegador. Para usar o formulário publicado, `AERI_RTD_TOKEN` precisa estar disponível como variável secreta no ambiente do backend web, além do executor local. A Central precisa autorizar operações de escrita para essa chave; leitura funcionando, por si só, não confirma essa permissão.
- Se a conexão cair depois que o AERI enviar a solicitação, o estado será **Verificar na Central antes de reenviar**. O sistema não tenta repetir a criação automaticamente, para evitar pedidos duplicados.
- Esta alteração foi validada sem credencial e sem enviar pedidos à Central. Antes do uso real, é necessário confirmar com a Central que a chave tem permissão de escrita e publicar a versão; cada envio continuará dependendo de conferência e confirmação humanas.

## Configuração local

1. Na Central ONRTDPJ, abrir **Serviços > Integração** e gerar/copiar o token do ambiente correspondente. Para produção, executar `python scripts/sincronizar_rtd.py --configurar`; para homologação, `python scripts/sincronizar_rtd.py --configurar --ambiente homologacao --passos 0`. O JWT é informado pela entrada oculta e salvo em `.env.rtd.local`, ignorado pelo Git.
2. Com o banco já configurado no `.env`, executar `python scripts/sincronizar_rtd.py --migrar-rtd --passos 1`.
3. Executar `powershell -ExecutionPolicy Bypass -File scripts/instalar_rtd.ps1`.
4. Após mudar o código: `powershell -ExecutionPolicy Bypass -File scripts/instalar_rtd.ps1 -Reiniciar`.

Estado: `Get-ScheduledTask -TaskName 'AERI RTD'`. Log local: `.tmp/rtd.log`. Para pausar, `Stop-ScheduledTask -TaskName 'AERI RTD'`; para retomar, `Start-ScheduledTask -TaskName 'AERI RTD'`.

Para somente acompanhar os dados sincronizados localmente, nenhuma chave RTD precisa ficar na Vercel: o backend web lê o resultado do Postgres. Para testar o formulário publicado, configure o token de homologação como segredo `AERI_RTD_TOKEN_HOMOLOGACAO`; o ambiente de notificação já usa homologação por padrão. Só depois de validar o teste e obter autorização operacional, configure o token de produção como segredo `AERI_RTD_TOKEN` e mude `AERI_RTD_NOTIFICACAO_AMBIENTE=producao`. A documentação pública não confirma se todo token tem permissão de escrita em `POST /api/notificacao`; valide em homologação antes do primeiro envio de produção. Não coloque a chave no código nem no navegador.

## Proteções e recuperação

HTTPS restrito ao host da API, sem seguir redirects com credencial; timeout e limites de tamanho/páginas; mensagens sem JWT ou URLs privadas. PDFs são lidos em memória. Apenas os identificadores, destinatários extraídos e dados operacionais necessários ficam no banco.

Trava transacional evita duas sincronizações simultâneas. Cursor só avança após persistir a página inteira; sobreposição de um dia e hashes evitam perder ou duplicar eventos. Erros de consulta preservam estado/cursor e retomam automaticamente. Falhas de um documento não param os demais.

As rotas do painel exigem `ver_intimacoes`; operações de leitura de avisos exigem sessão e CSRF. A auditoria não grava o conteúdo dos PDFs. Não são exibidos links privados de download.

## Reconciliação autorizada em 01/10/2026

O relatório XLS contém 244 pedidos. A seleção de **41 em tratativa**, confirmada pelo responsável, mantém `Desistência` não concluída e exclui `Desistência Concluída`, arquivados, `Registro / Averbação` e `Entrega das importâncias recebidas`.

Foram incluídos 10, preservados integralmente 31 e enviados à lixeira 3, com histórico e restauração disponíveis. Os novos não receberam valores financeiros presumidos. O nome do devedor é completado pelos documentos RTD quando houver correspondência verificável.

O script `scripts/importar_intimacoes_relatorio.py` faz prévia por padrão. `--aplicar` exige total esperado, lista explícita dos protocolos a enviar à lixeira e administrador responsável. A transação valida o conjunto final e a preservação dos existentes antes do commit. Precisa de `xlrd` para ler o formato XLS antigo.

## Testes

`python -m unittest tests.test_rtd_intimacoes tests.test_intimacoes` e `node tests/test_rtd_intimacoes.mjs`.

O teste opcional `tests.test_rtd_banco` usa tabelas temporárias em uma conexão **direta**, nunca no pool transacional. Habilitar `AERI_TEST_RTD_DB=1` somente com ambiente de teste configurado. Cobre fila, idempotência, vários RTDs por IN, mudança de situação e leitura por usuário/versão.
