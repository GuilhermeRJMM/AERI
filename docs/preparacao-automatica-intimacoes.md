# Preparação automática de Autuação, Ofício Contrafé e Convocação

Implementação com publicação autorizada pelo responsável. O estado operacional deve ser conferido no deploy do commit correspondente. Complementa a bancada dos três anexos existente.

## Operação

IN e último número do ofício → seleção dos três anexos → processamento → consultas de leitura à Tri7 → três prévias preenchidas → conferência e cópia individual.

As prévias são preparadas imediatamente. O formulário foi recolhido em “Exceções e correções”; somente campos vazios/incompletos e seleção de devedor quando há mais de uma pessoa aparecem inicialmente. Há opção para inspecionar todos os dados extraídos. Editar um dado invalida as versões anteriores e habilita a atualização dos textos. Alterar uma confirmação revoga a aprovação sem apagar a prévia.

Uma prévia incompleta identifica os espaços pendentes expressamente; não pode ser aprovada/copiada como documento pronto. As três prévias não significam três documentos aprovados. Não existe assinatura, emissão de selo ou envio automático.

## Fontes e limites

| Dado | Regra |
|---|---|
| Protocolo RGI | Recibo que confirma o IN; diferença cadastral permanece visível e exige confirmação. |
| Ato da garantia | Ato próprio do parser registral, cruzado por contrato, CNPJ do credor e CPFs no bloco de devedores. Não se usa CPF do procurador do banco nem referência solta ao R. no corpo de outro ato. |
| Ato indicado no Ofício | Quando informado, restringe a seleção; não é trocado silenciosamente por outro R. |
| Garantia cancelada/ambígua | Não preenche automaticamente. O analisador de ônus existente é reutilizado sem mudar suas regras. |
| Contrato | Número literal confirmado, admitindo o DV final quando a correspondência é única; grupo/cota de consórcio não é convertido em número de contrato de adesão. |
| Título e data | Forma do título no ato correspondente, inclusive título extenso. Data contratual não é a data do registro. Divergência com o Ofício vira exceção. |
| Endereço | Anexos; se ausente, descrição de abertura da matrícula identificada como tal nas fontes, sem proprietário histórico. Deve ser conferida quanto a alterações posteriores. Não substitui endereços de notificação. |
| Cláusula | Referência expressa no Ofício ou outorga descrita no ato; diferença não é resolvida arbitrariamente. |
| Selo | Somente selo já emitido no item de intimação do protocolo e da matrícula corretos, quando único. Não reutiliza selo da prenotação, busca ou garantia antiga. |
| Responsável | Nome completo sugerido pelo cadastro do operador autenticado, a conferir. Contas genéricas de administrador/sistema não são inventadas como escreventes. Não há assinatura digital. |
| Projeção | Preservada dos anexos/OCR; o complemento não recalcula nem substitui valores por valores antigos da matrícula. |

O número de processo do credor não é inventado a partir de código de barras ou protocolo RGI. Selo ainda não emitido e documento sem informação essencial continuam sendo exceções reais. Não há promessa de todos os casos exigirem apenas a numeração.

O modelo institucional continua exigindo confirmação de aplicabilidade, especialmente em consórcio. Este desenvolvimento não aprova nem cria uma nova redação jurídica para outro tipo de instrumento.

## Integração

- `servicos/enriquecimento_intimacao.py`: complemento compartilhado e somente leitura, com proveniência dos campos e hash do texto consultado, sem armazenar o texto integral.
- `rotas/intimacoes.py`: usa o complemento tanto no upload quanto no retorno da leitura de rede; busca o nome do operador no banco com parâmetros. Sessão, permissão e CSRF existentes são mantidos.
- `servicos/anexos_intimacao.py`: extrai também o registro indicado, cláusula e endereço expressamente informados pelo credor.
- Consultas autenticadas usam o cliente Tri7 existente. As credenciais permanecem no backend; o executor não precisa ter credencial Tri7 para esta etapa.
- Atualizar também o executor antes da homologação da leitura de rede para obter os novos metadados dos anexos. Não há migração nova nem alteração de credenciais.
- Resultados temporários mantêm o ciclo de cifragem/expiração/descarte existente. Não há dados operacionais em localStorage.

## Verificação

- 206 testes Python e 21 subtestes aprovados, incluindo seleção de garantia, cancelamento, ambiguidade, identidade, selos, datas divergentes, títulos extensos e compatibilidade com os módulos anteriores.
- Navegador: caso completo gera prévias sem preenchimento adicional e mantém correções recolhidas; caso incompleto bloqueia aprovação; confirmação de protocolo e revogação de consentimento são exigidas; cópias continuam individualizadas.
- Teste anterior da Mesa de Conferência, testes dos modelos e pares RTD aprovados.
- Consultas reais de leitura com os dois conjuntos fornecidos: garantia e título identificados nos dois; no financiamento foi localizado selo já emitido; no consórcio a API ainda não disponibilizou selo da intimação nem o Ofício explicitou número de processo do credor. Não foram feitos salvamentos ou emissões na Tri7.
- Colagem/paginação no editor nativo da Tri7 continua dependendo de homologação presencial; esta etapa não a certifica.
