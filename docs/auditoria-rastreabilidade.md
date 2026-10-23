# Rastreabilidade da auditoria de matrículas — motor 2.2.0

## O que muda

- A origem de cada proprietário acompanha as alterações do cálculo cronológico: aquisição, alienação parcial, partilha, retificação e alteração territorial. Uma simples menção posterior ao nome não substitui o ato de aquisição.
- As evidências de ônus procuram a cláusula relevante no ato inteiro. Quando existe cancelamento, a evidência também aponta o ato cancelador e seu trecho.
- A cobertura compara os atos segmentados com cabeçalhos explícitos identificados independentemente. Na consulta por número, compara também com os atos registrados retornados pela Tri7.
- Se o catálogo da Tri7 indicar um ato ausente no texto, ocorre uma única nova leitura. Persistindo a divergência, os códigos ficam no diagnóstico e o resultado recebe indicação de revisão. Não se inventam atos nem se bloqueia o retorno da análise.
- A assinatura de regras passa a incluir os componentes de cadeia, evidências, cobertura e serviço de análise. A versão permite que a revisão existente reconheça resultados antigos, sem apagar o índice ou exigir uma varredura integral imediata.

## Limites

O observador não altera saldos, percentuais ou regras oficiais de classificação e cancelamento. Metadados de histórico e cobertura são adicionais; o hash de resultado não autentica esses diagnósticos posteriores. A conferência do catálogo depende da disponibilidade e completude da API. O reconhecimento independente de cabeçalhos é conservador, não uma garantia de leitura de todos os formatos históricos.

Não há migração de banco nem mudança visual. Os rastros transitórios usam documentos pessoais para desambiguar identidades; o histórico público não acrescenta esses documentos.

## Verificação

`tests/test_auditoria_rastreabilidade.py` cobre origem cadastral versus aquisição, transmissões parciais, retificações, partilha agrupada, alienação integral seguida de recompra, alterações territoriais, cancelamentos, trechos longos, Unicode, cobertura, respostas inválidas e recuperação limitada na Tri7. O corpus de referência compara o cálculo com e sem observação para preservar os resultados oficiais.
