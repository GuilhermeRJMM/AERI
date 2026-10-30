# Bancada de documentos de intimação — implementação local

Data: 30/10/2026. Estado: implementada e testada localmente, **não publicada**.

## 1. Investigação e comportamento anterior

A funcionalidade existente era o modal `modal-documentos-intimacao`, acionado pela própria rotina de intimações. Recebia dois PDFs e, opcionalmente, um título registrado; havia leitura pelo executor e complemento por consultas à Tri7. O navegador construía textos resumidos, com fonte diferente dos modelos fornecidos, e a revisão não era individualizada com auditoria de cada versão.

Foram examinados os três PDFs oficiais fornecidos: Autuação, Ofício Contra Fé e Convocação. São referências documentais, não instruções executáveis. Seus originais não foram alterados. Páginas de manifesto, certificados e papel de segurança não foram convertidos em assinaturas fictícias.

## 2. Alterações e escopo

O módulo existente foi reformulado, sem criar um segundo produto. Agora exige Recibo do Protocolo, Ofício do Credor e Planilha de Projeção. Prepara textos revisáveis; não emite selos, não assina, não pratica atos, não salva na Tri7 e não envia ao RTD. O fluxo de envio RTD já existente permanece separado.

Não foram executados SQLs no banco da Tri7, operações registrais ou alterações de dados de produção. Não houve deploy, push ou instalação desta versão no executor de produção.

## 3. Arquivos envolvidos

| Arquivo | Responsabilidade |
|---|---|
| `backend/app/servicos/anexos_intimacao.py` | Três anexos, Excel, OCR local, proveniência, divergências e seleção segura da pasta. |
| `backend/app/servicos/documentos_intimacao.py` | Reutilização do extrator existente com texto já lido, mantendo a assinatura anterior compatível. |
| `backend/app/servicos/preparacao_intimacao.py` | Extensão da fila/executor existente para listar e ler os três arquivos selecionados. |
| `backend/app/rotas/intimacoes.py` | Leitura manual, fila, descarte temporário e auditoria da revisão/cópia. |
| `backend/static/js/intimacao_documentos.js` | Controlador do modal, extração, conferência, edição, aprovação e área de transferência. |
| `backend/static/js/intimacao_modelos.js` | Redação e estrutura dos três modelos; próximo número do ofício. |
| `backend/templates/intimacao_documentos.html` | Conteúdo do modal existente em quatro etapas. |
| `backend/templates/index.html` | Inclusão da parcial e do CSS específico. |
| `backend/static/intimacao-documentos.css` | Estilização branca, azul-marinho e esmeralda, restrita à bancada. |
| `backend/static/js/intimacoes.js` | Atualização da versão do import do módulo existente. |
| `requirements.txt` | Declaração das bibliotecas pequenas de Excel: openpyxl e xlrd. |
| `tests/test_anexos_intimacao.py` | Extração, conflitos, pastas, segurança dos formatos, permissões e auditoria. |
| `tests/test_modelos_intimacao.mjs` | Numeração, validação de datas/valores, redação e estilo dos modelos. |
| `tests/test_documentos_intimacao.mjs` | Adequação das expectativas aos modelos oficiais e regressão dos pares RTD. |
| `tests/browser_documentos_intimacao.cjs` | Jornada no Chrome com dados sintéticos e chamadas interceptadas. |

## 4. Fluxo do funcionário

1. Abrir a preparação a partir de um IN existente na fase inicial.
2. Informar o último ofício efetivamente utilizado; conferir/corrigir o próximo número.
3. Localizar os arquivos da pasta pelo executor, ou anexar manualmente os três documentos.
4. Confirmar a origem e processar os anexos.
5. Examinar fontes, avisos e divergências; completar somente dados comprovados nos originais.
6. Confirmar a aplicabilidade do modelo e a conferência dos campos; preparar os textos.
7. Revisar e, se necessário, editar cada texto integralmente.
8. Aprovar cada versão e copiar individualmente para a Tri7. Conferir a colagem antes de salvar.

## 5. Pasta do IN no Windows

É reutilizado `ferramentas/abrir_pasta_intimacao.py`, incluindo o resolvedor já existente. O botão de abertura utiliza `aeri-intimacao://abrir/IN...`. Não há tentativa de forçar o caminho inicial de um input HTML de arquivos.

O seletor próprio solicita uma tarefa ao executor existente, que acessa a pasta autorizada do IN e suas subpastas imediatas. O navegador recebe nomes, tamanhos e IDs, nunca caminhos da rede. Seleciona três arquivos distintos. Nomes sugestivos só são selecionados automaticamente quando há um único candidato; o funcionário confere a seleção.

Pastas ausentes/inacessíveis, seleção inválida, arquivos fora da raiz e vínculos para fora do diretório são recusados. A leitura tem limite por arquivo e não percorre a rede inteira. O IN é validado antes da geração e o recibo deve confirmá-lo. PDFs com outro IN explícito são recusados. Quando credor/projeção não informam IN, é exigida correspondência da matrícula com o recibo.

## 6. Processamento e limites

- Recibo e Ofício: PDF pesquisável. Projeção: PDF, XLS BIFF/OLE ou XLSX válido.
- PDF sem texto suficiente: leitura pelo executor com o OCR local já existente. Não há IA externa.
- Leitura manual: até 4 MB somados, para respeitar o envio à hospedagem. Para arquivos maiores, usar o executor; limite de 8 MB por anexo.
- Excel: somente leitura, sem executar fórmulas/macros ou buscar vínculos externos. São utilizados resultados calculados previamente salvos. Formatos de moeda e identificadores são respeitados na representação textual.
- Limites de arquivos ZIP/XML, abas, linhas, colunas e células. Estruturas XML com declaração de entidades são recusadas. XLS contendo HTML disfarçado não é aceito por este leitor.
- Originais não são gravados no banco. O OCR utiliza arquivos temporários, removidos inclusive em falha.

O novo trabalho de rede expira em 15 minutos; a tela aguarda até aproximadamente 14 minutos. OCR que não concluir nesse prazo exige nova tentativa ou PDF pesquisável. O cancelamento não garante interrupção imediata de um processo de OCR já em execução; impede a publicação de seu resultado naquela tela.

## 7. Campos, origem e validações

| Campo | Tratamento |
|---|---|
| IN | Cadastro selecionado e confirmação no recibo; rejeição de outro IN nos anexos. |
| Protocolo RGI e data | Recibo; a data de entrada é distinta da data de impressão. Comparação com o vínculo do AERI, quando preenchido. |
| Processo do credor, partes e contrato | Extratores existentes do Ofício; identificação cruzada com a projeção e matrícula. |
| Matrícula | Conferência entre os anexos, incluindo o recibo. |
| Endereço do imóvel | Extração e indicação das fontes; divergências detectadas não são resolvidas silenciosamente. |
| Endereços de notificação | Mantidos nos textos, sem aplicar o filtro de cidade do envio RTD. |
| Projeção | Valor para a data de preparação, sem escolher valor futuro nem recalcular o débito. Datas/valores repetidos e divergentes são sinalizados. |
| Título, ato da garantia, selo e cláusula | Não presumidos. Conferência/complementação manual quando não constarem dos anexos. |
| Data do título na Autuação | Campo independente da data contratual do Ofício e da Convocação. Os próprios modelos fornecidos apresentam datas diferentes. |
| Escrevente | Informado e conferido; não há nome pessoal fixo no modelo. |

Campos conflitantes são destacados com suas fontes e, quando aplicável, esvaziados para correção. Valores são tratados sem arredondamento arbitrário. Um texto com dados essenciais faltantes permanece bloqueado em sua aba; os demais podem ser revisados se estiverem completos. A aprovação humana continua indispensável.

## 8. Geração e redação

Os três geradores usam os PDFs fornecidos como referência de redação, títulos, encerramentos, campos variáveis e seções. O Ofício inclui Contrafé, Certidão, endereços e Observações, com duas quebras de página indicadas no HTML.

Trechos sobre procurações recíprocas e financiamento residencial NÃO são deduzidos dos três anexos. Exigem conferência expressa da aplicabilidade e da cláusula no instrumento. Se não corresponderem ao caso, o modelo não deve ser aprovado sem revisão apropriada pelo responsável.

“Assinado Digitalmente” é texto do modelo, não uma assinatura produzida pelo AERI. Campos em branco destinados à diligência permanecem em branco. Manifestos e assinaturas reais dos PDFs de exemplo não são reproduzidos.

## 9. Formatação verificada e limites

| Modelo | Evidência identificada no PDF e representação HTML |
|---|---|
| Autuação | Arial 12 pt; Processo e SAEC/ONR em Arial negrito 15 pt; AUTUAÇÃO em 18 pt; rótulos em negrito/sublinhado e corpo justificado. Distância de linhas do corpo próxima de 20,76 pt. |
| Ofício | Arial 9,96 pt; títulos internos próximos de 11,04 pt; Observações em 12 pt; negritos e sublinhados; recuo inicial próximo de 25 mm; corpo com distância de linhas próxima de 13,2 pt; tabelas e campos da diligência. |
| Convocação | Arial 12 pt; título em Arial negrito/sublinhado 15 pt; destinatário em negrito; corpo justificado e encerramento centralizado; distância de linhas próxima de 13,8 pt. |

A largura útil aproximada foi representada em 165 mm. Os tamanhos das fontes foram lidos dos metadados; espaçamentos/margens são aproximações a partir das coordenadas do PDF, não o arquivo de estilo original da Tri7. Não há garantia de paginação ou equivalência pixel a pixel. Timbre, papel de segurança, contagem de páginas e assinatura permanecem sob responsabilidade da operação final na Tri7.

## 10. Aprovação, invalidação e auditoria

Cada documento tem aprovação independente e botões inicialmente bloqueados. A edição do texto invalida a aprovação desse texto. Trocar anexos, campos, data ou numeração invalida os rascunhos anteriores. Respostas atrasadas não podem repopular outro contexto/IN.

Rotas protegidas por sessão, permissão `alterar_intimacoes` e CSRF. Eventos de revisão/cópia registram usuário, IN, tipo, número, hashes dos três anexos e hash da versão HTML aprovada, sem gravar o conteúdo integral. O hash identifica a versão declarada pelo operador; não é assinatura digital nem certificação jurídica.

Fechar a bancada limpa arquivos, prévias, campos e referências em memória. O resultado de rede é cifrado na infraestrutura temporária existente e descartado após recebimento/fechamento, quando a solicitação de descarte chega ao servidor. Falhas de conexão deixam a proteção da expiração; a remoção física de trabalhos expirados ocorre na limpeza do executor quando ele estiver ativo. Não há armazenamento em localStorage.

O último número informado 52 sugere `INT/2026/053`. A geração não reserva número nem o marca utilizado. Há detecção de número já registrado em cópia para outro IN no histórico do AERI, com bloqueio para conferência/correção. Isso NÃO consulta a sequência oficial nem garante exclusividade concorrente: duas pessoas podem revisar antes de qualquer cópia registrada. A sequência oficial da Tri7 e a coordenação entre funcionários continuam necessárias. Cópia registrada não prova uso efetivo na Tri7; cancelamentos precisam ser avaliados antes de qualquer futuro controle de sequência.

## 11. Cópia

Botões separados por documento: HTML formatado ou texto simples explicitamente identificado. O HTML é sanitizado e inclui estilos inline, parágrafos, negritos, fonte, tabelas e quebras indicadas. A alternativa simples não se apresenta como cópia fiel. Falha de permissão do navegador informa o problema sem afirmar sucesso.

O clipboard não pode ser transacionado com o banco: se a cópia ocorrer e o registro de auditoria falhar em seguida, a interface informa precisamente essa situação. Nenhum texto é inserido automaticamente na Tri7.

## 12. Testes executados

- 127 testes Python aprovados e 17 subtestes: anexos, documentos existentes, pastas, rotas/permissões, auditoria, intimações, RTD e instalação do executor.
- JavaScript: modelos e validações; teste de regressão dos pares RTD mantido aprovado.
- Chrome/Playwright: três anexos obrigatórios; incremento; três cópias HTML independentes; bloqueio anterior à aprovação; edição/invalidação; resposta atrasada; seleção por IDs; ausência de caminhos internos; fundo branco e viewport móvel.
- Chrome/Playwright: teste já existente da Mesa de Conferência aprovado, incluindo busca, fases, RTD, conferência, erro e mobile.
- `git diff --check` sem erros de espaço. Avisos de depreciação de biblioteca de testes e identificação de módulos no Node não impediram os testes.
- Leitura local dos três anexos reais do IN fornecido conferida sem chamada à Tri7, sem salvamento dos originais e sem expor dados pessoais nos testes automatizados.

Os testes de clipboard interceptam a API do navegador para verificar o conteúdo HTML. Não são teste de colagem no editor nativo. OCR foi testado com motor simulado e limpeza de temporários; não foi executada diligência nem comprovada leitura real de todos os tipos de PDF digitalizado. O caminho XLS tem proteções e implementação, mas ainda precisa de amostra real de projeção XLS para homologação; XLSX foi testado com arquivo sintético real.

## 13. Limitações e preparação para homologação

Esta versão está no checkout limpo de trabalho; o checkout principal já continha alterações alheias e não foi sobrescrito. Não foi instalada no executor em uso e não está disponível em produção.

Antes de liberar o seletor de rede, atualizar o executor com esta versão e suas dependências e verificar sua chave de cifragem e acesso à raiz T: já configurados. A tela rejeita resultado de executor antigo em vez de aceitar leitura incompleta de dois anexos. Nenhuma configuração secreta foi adicionada ao código.

Os três anexos podem não conter título literal, ato da garantia, selo, cláusula e data própria da Autuação. Não é possível automatizar dados ausentes com segurança. A bancada pede complemento humano comprovado em vez de inventar informações ou assumir os dados do exemplo. Não foram feitas consultas externas para preencher essas lacunas.

Não houve homologação de transação PostgreSQL real desta funcionalidade nova: testes de endpoints e auditoria usam conexões simuladas. É necessário validar o ciclo fila → executor → resultado → descarte em ambiente de homologação com a versão nova, sem operações registrais.

## 14. Checklist presencial na Tri7, antes de produção

1. Em ambiente de teste autorizado, abrir o mesmo IN e comparar os três documentos completos com os modelos institucionais.
2. Colar cada HTML no editor da Tri7; conferir fonte/tamanho, recuos, espaços, parágrafos, negritos, tabelas, quebras e paginação.
3. Conferir todas as páginas do Ofício, inclusive continuação da Certidão e campo Observações.
4. Conferir destinatário selecionado, todos os endereços, cláusula contratual, valor/data da projeção, selo já existente e escrevente.
5. Conferir especialmente as duas datas independentes: Autuação versus referência contratual nos demais textos.
6. Testar arquivo XLS real e PDF digitalizado em OCR local no executor de homologação.
7. Testar dois operadores, cópia cancelada na Tri7 e possíveis números repetidos. Não tratar o histórico de cópias como livro oficial.
8. Se a Tri7 descartar atributos HTML, mapear quais; validar alternativa RTF/colagem por editor compatível ou ajuste explícito dos estilos na Tri7 antes de prometer fidelidade. O fallback de texto simples não resolve essa equivalência.
9. Só publicar após autorização e resultados satisfatórios de homologação. Nenhum salvamento/assinatura na Tri7 está autorizado por esta implementação.
