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
| Responsável | Luiz Fernando Ribeiro como padrão setorial expressamente autorizado; pode ser corrigido antes da revisão. Não há assinatura digital. |
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

## Ajustes de endereço e paginação — 30/10/2026

- Endereço do imóvel compacto, sem área/confrontações, reutilizado na Autuação e Convocação. CEP confirmado pelo ViaCEP somente com município/UF, rua e bairro correspondentes e resultado único; abreviação por inicial do bairro pode ser expandida apenas com as demais palavras iguais e correspondência única. Consulta externa recebe só rua e município, não PDFs, nomes ou CPF.
- CEP indisponível/ambíguo fica `CEP: ________`, sem CEP genérico. Nenhum cadastro registral é alterado.
- Primeira notificação usa endereços do Ofício do credor, inclusive rurais/multilinha. Somente município de Morrinhos-GO confirmado; outras localidades e município indefinido ficam fora da minuta e são sinalizados para revisão. A descrição do imóvel não é transformada em endereço de diligência.
- Encerramento do Ofício usa o nome do credor quando não há substituição explícita; campo opcional vazio não gera marcador de pendência.
- Ofício dividido em três seções: assinatura encerra página 1; CONTRA-FÉ/CERTIDÃO iniciam página 2; continuação, Observações e endereços locais ao final da página 3. Não inclui manifesto de assinaturas do PDF-modelo.
- Impressão Chrome A4 validada com margem superior 52 mm, laterais 22,5 mm e inferior 20 mm. Medição de 165 × 225 mm por página bloqueia aprovação/cópia quando o texto excede o espaço, sem cortar informação. Testes cobrem caso sintético e caso real lido da rede/Tri7, sem emissão/salvamento na Tri7.
- Editor nativo pode ignorar quebras do HTML ao colar: há alternativa para copiar cada página separadamente, sempre após aprovação/auditoria da mesma versão. Conferir as três páginas na Tri7 antes de salvar continua necessário.
- Regressão geral: 1.575 testes e 278 subtestes passaram, 8 ignorados. Cinco falhas também reproduzidas em checkout isolado do commit anterior `0ff9bf0` (mock cifrado de Contratos, diretório ausente em dois testes do inventário e duas expectativas antigas de bloqueio das Buscas). Nenhuma foi mascarada ou alterada nesta entrega.

### Modelo revisado pela gravação de 30/10, 20:12

A gravação enviada posteriormente pelo operador passa a orientar a disposição: corpo dos três documentos em Arial 10; CONTRA-FÉ e CERTIDÃO em 10; a última opção da Certidão, incluindo as três tentativas, termina inteira na página 2. Página 3 começa pela devolução/assinatura e apresenta endereços antes do quadro de Observações, com divisórias. Esta ordem substitui a disposição anterior dos endereços ao final da página 3. Continuam válidos o filtro de Morrinhos, CEP confirmado ou branco, signatário padrão e credor literal.

O vídeo mostra a régua e o tamanho da fonte, não o diálogo de margens/entrelinhas. Espaçamentos foram ajustados visualmente e verificados em impressão Chrome com o perfil A4 documentado; não se declara medição exata das margens da Tri7 nem colagem nativa homologada. Não são copiados dados do caso-modelo nem placeholders operacionais fixos para os novos casos.
