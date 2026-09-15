# Buscas: atualização e recuperação por texto

## Pesquisa

- O nome e o CPF/CNPJ podem ser informados juntos. A pesquisa reúne as correspondências; documento divergente não confirma identidade.
- Por padrão são exibidas matrículas ativas. Encerradas podem ser consultadas separadamente pelo filtro.
- Titulares vêm da cadeia dominial extraída do texto, nunca do cadastro de pessoas da Tri7.
- Menções por ato são um índice auxiliar: transmitentes, adquirentes, qualificados e retificações aparecem em uma seção de conferência. Não viram proprietários pela simples menção.
- Variações históricas de nome só são associadas a um titular pelo mesmo documento protegido e na mesma matrícula.
- Auditoria da cadeia pendente, documento conflitante, índice antigo ou falha de reconsulta reduzem a confiança. A geração do texto é bloqueada quando há pendências relevantes. Sem resultados, lacunas no índice impedem gerar uma negativa automática.
- A exportação antiga também usa essas salvaguardas. Os endpoints continuam exigindo sessão e permissão de Buscas; reconsultas exigem permissão de revisão e CSRF.

## Atualização

O executor alterna seis posições persistidas: prioritárias, novas, revisão, lacunas, erros e revisão. Erros têm intervalo crescente de nova tentativa, até seis horas. A revisão prioriza versões antigas e depois textos há mais tempo sem consulta.

A consulta recebe o texto da Tri7 e compara hash do texto, versão do motor, versão do índice e versão da proteção dos documentos. Se tudo permanece igual e existe auditoria, atualiza a data da consulta sem reexecutar a análise nem substituir os titulares. Resposta vazia posterior preserva os dados anteriores, marcados para conferência.

O Livro manual e o automático usam o mesmo serviço para atualizar os índices de matrículas e Registro Auxiliar, reutilizando os textos já consultados. Falhas de matrículas entram na fila prioritária.

No executor local, uma passagem por hora consulta as três janelas de apresentações disponíveis e recupera protocolos registrados hoje e nos sete dias anteriores. Processa até dois protocolos por passo, localiza as matrículas com atos e agenda nova consulta do texto. Isso não é webhook nem prova de cobertura de protocolos fora da janela da API. A revisão do acervo continua necessária.

## Implantação

1. As migrações 046 e 047 são aditivas; 046 corrige o último número conhecido pelo maior texto realmente localizado. 047 cria índices auxiliares e filas, sem remover titulares.
2. O executor precisa da **mesma** `AERI_BUSCAS_HMAC_KEY` de produção. Não gerar outra: documentos indexados deixariam de coincidir.
3. `scripts/configurar_chave_buscas.ps1` recebe a chave existente de forma oculta e salva somente `.env.buscas.local`, ignorado pelo Git. O executor carrega esse arquivo depois de `.env`, preservando variáveis já definidas no processo.
4. Reiniciar o executor após configurar a chave. Sem ela a indexação permanece indisponível. Não basta publicar o frontend.
5. As menções são preenchidas gradualmente, durante a reindexação. Publicar não significa que todo o acervo foi reanalisado. A interface informa quantas matrículas ainda aguardam esse índice.

## Verificação e reversão

Testes cobrem hash estável, mudança de versão, preservação após texto vazio, homônimos, histórico separado, rodízio, recuperação de protocolos, Livro automático e regressões do analisador. `tests/test_buscas_postgres.py` usa tabelas TEMP isoladas e rollback, somente quando `AERI_TEST_POSTGRES_URL` é fornecida explicitamente. Nunca executar a suíte inteira com credenciais de produção.

Para voltar, publicar o commit anterior. As colunas/tabelas adicionais podem permanecer: a versão anterior não depende delas. Não apagar tabelas operacionais nem trocar a chave HMAC. Alterações legítimas já feitas nos índices não são desfeitas por rollback de código.

## Informar Custas: safra sem rótulo

O relatório pode trazer `MILHO 2026/2027` sem escrever SAFRA. O importador reconhece o par de anos imediatamente após o produto, sem confundir datas completas ou números de guias. Preserva literalmente `2026/2026` quando assim informado. O PDF de teste de 15/09/2026 contém 12 pedidos: seis alienações com 2026/2027 e seis penhores com 2026/2026.

Pedidos já salvos não têm resultados ou safra sobrescritos silenciosamente por essa correção; a revisão dos dados importados anteriormente continua necessária.
