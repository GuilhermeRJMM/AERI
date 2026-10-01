# Diligências RTD nas intimações

Integração de cliente ONRTDPJ, somente leitura. Não envia pedidos, não paga boletos e não altera o cadastro da central.

## Operação

- A tarefa Windows **AERI RTD** consulta mudanças a cada 5 minutos, independentemente do navegador e do executor operacional.
- A máquina precisa estar ligada, conectada à rede e com a sessão do usuário iniciada. O painel informa atraso após 10 minutos sem concluir uma consulta.
- Na primeira execução é percorrido o histórico paginado. Os PDFs são processados em lotes de dois, numa fila persistida no Postgres. Fechar a tela não interrompe o trabalho.
- Vínculo por IN exato extraído do PDF. Um IN pode ter várias diligências. Ausência, ambiguidade ou conflito ficam visíveis na revisão, sem escolher uma correspondência aproximada.
- Destinatários são identificados no vocativo do ofício. Somente lacunas explícitas de importação são preenchidas; nomes editados pela equipe não são sobrescritos. A origem automática fica registrada no banco e na auditoria.
- Orçamento, situação, resultado/data da diligência e histórico RTD ficam separados do andamento, fase e finanças internos.
- Novidades aparecem primeiro na lista; o botão **Marcar atualização como vista** vale apenas para o usuário e a versão exibida. Uma alteração concorrente permanece destacada.
- Documentos protegidos, digitalizados sem texto, grandes ou sem IN identificável ficam pendentes de revisão. Esta integração não executa OCR.

## Configuração local

1. Com o banco já configurado no `.env`, executar `python scripts/sincronizar_rtd.py --configurar --migrar-rtd --passos 1`.
2. Informar o JWT pela entrada oculta. A chave é validada e salva em `.env.rtd.local`, ignorado pelo Git. Nunca vai ao navegador.
3. Executar `powershell -ExecutionPolicy Bypass -File scripts/instalar_rtd.ps1`.
4. Após mudar o código: `powershell -ExecutionPolicy Bypass -File scripts/instalar_rtd.ps1 -Reiniciar`.

Estado: `Get-ScheduledTask -TaskName 'AERI RTD'`. Log local: `.tmp/rtd.log`. Para pausar, `Stop-ScheduledTask -TaskName 'AERI RTD'`; para retomar, `Start-ScheduledTask -TaskName 'AERI RTD'`.

Nenhuma chave RTD é necessária na Vercel para esse modo: o backend web só lê o resultado no Postgres. É necessário publicar os arquivos de backend/frontend para exibir o painel novo.

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
