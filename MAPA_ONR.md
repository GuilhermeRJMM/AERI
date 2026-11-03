# Integração AERI com o MAPA-ONR

## Arquitetura

O conversor MAPA-ONR permanece como motor da conversão. A integração híbrida
complementa a extração; correções locais no motor são acompanhadas de regressões.

Ao consultar uma matrícula na Tri7, o backend executa o analisador do AERI e monta
um contexto complementar para o conversor. Na extração de confrontantes, a camada
do AERI separa:

- número da matrícula confrontante;
- descrição física ou registral da confrontação;
- nome do proprietário, somente quando o texto usa uma indicação explícita, como
  “propriedade de” ou “pertencente a”;
- confiança e motivo de revisão.

Descrição de fazenda, servidão, estrada, córrego ou órgão cadastral não é tratada
como nome de proprietário. Nome truncado por reticências também não é exportado.

Quando a confiança é baixa, a tela exige conferência antes de liberar o JSON. A
confirmação exporta somente a matrícula confrontante, sem inventar ou completar o
nome do proprietário.

## Reversão imediata

A integração híbrida é controlada por uma única variável de ambiente:

```text
MAPA_ONR_MODO_ANALISE=hibrido
```

Esse é o modo padrão. Para restaurar integralmente a extração anterior:

```text
MAPA_ONR_MODO_ANALISE=legado
```

Depois de alterar a variável na Vercel, é necessário realizar um novo deployment.
O modo legado ignora o contexto complementar e chama diretamente o extrator
original, sem exigir exclusão de arquivos ou reversão de commit.

## Limites deliberados

A camada não tenta adivinhar o proprietário a partir do nome da fazenda ou de um
cadastro. Se o documento não trouxer a relação de propriedade de forma completa,
o caso permanece em revisão humana. Essa restrição evita que um JSON formalmente
válido contenha uma afirmação registral incorreta.

## Qualificação histórica e decisão judicial — 03/11/2026

- Partes que o ato identifica como já/acima qualificadas são recuperadas na seção de partes correspondente, com nome completo único, documento e fonte anterior. Não se reaproveitam papéis, percentuais ou titularidade de outro negócio.
- Qualificação de cada ato é cronológica: alterações posteriores não retroagem. Estado civil é lido na janela da própria pessoa, não na qualificação do casal vizinho. Regime declarado anteriormente pode preencher omissão; regime presumido continua identificado como presumido e para revisão.
- Homônimos com documentos diferentes, CPF explícito contraditório, mera menção em confrontação e identidade ambígua não são completados. Uma letra excedente no nome do marido só pode ser resolvida com esposa exata e única e casamento anterior compatível, mantendo aviso de grafia divergente.
- O caso real 2.460 foi consultado somente por leitura na Tri7: R.20 recupera o casal qualificado nos R.01/R.02, sinaliza a grafia divergente do marido e mantém o terceiro devedor como solteiro, sem regime. Não há alteração na Tri7 nem no índice de buscas.
- Campo **Decisão Judicial** por R./AV., opções vazio/Sim/Não. Usa a chave `decisao_jud` do manual 1.3.0 em cada registro exportado, sem criar atributo alheio ao contrato.
- Versão 1.2.0 não admite `decisao_jud`: **Sim** gera pendência específica, impedindo eliminar o campo e utilizar silenciosamente a dispensa de dados. Selecionar 1.3.0 só quando o destino aceitar essa versão; o campo não é enviado à Tri7. **Não** mantém as exigências normais de preenchimento.
- Testes sintéticos cobrem cronologia, casal sem documentos repetidos, homônimos, documento contraditório, grafia divergente condicionada, campos independentes por ato e compatibilidade de exportação. Dados reais e credenciais não são versionados.

### Sugestão de Decisão Judicial pelo texto

Indicações expressas da base judicial do próprio ato (cumprimento de mandado/ordem/sentença judicial, formal de partilha julgado por sentença ou instrumento expedido por Juízo/Vara) preenchem Sim com trecho e aviso de sugestão para revisão. Origem extrajudicial expressa, escritura pública de inventário/partilha ou declaração explícita de inexistência de decisão podem preencher Não. Ausência de referência, simples menção a processo/inventário, referência histórica negada e evidências conflitantes mantêm o campo vazio. Nenhuma decisão é herdada de outro ato. Edição manual prevalece durante a revisão; reler a matrícula recompõe as sugestões.

Não é consulta ao cadastro da decisão na Tri7 nem julgamento jurídico do documento: a sugestão vem somente do texto registral e permanece editável. Mantida a exigência da versão compatível e a validação da remessa; o AERI não escreve esse campo na Tri7.

### Bateria de 1.000 simulações e conclusões explícitas

`tests/test_mapa_onr_decisao_1000.js`: 250 combinações de redação × quatro formatos (normal, caixa alta, sem acentos e linhas quebradas), totalizando 1.000 textos distintos. São 200 casos em cada grupo: base judicial, base extrajudicial, referência histórica, origem não declarada e contradição. Há ainda casos adversariais separados para mandado revogado/não expedido, “não informado”, determinação judicial sobre escritura e quebra de palavra em OCR. Expectativas são fixadas nas categorias antes da execução, não calculadas pelo detector.

A interface sempre apresenta uma conclusão legível, com evidência quando disponível: **SIM — base judicial**, **NÃO — base extrajudicial/negativa expressa**, **NÃO COMPROVADO — conferir título de origem**, ou **REVISÃO OBRIGATÓRIA — bases incompatíveis**. Os dois últimos não exportam um booleano inventado. Detalhamento fica visível, sem reticências escondendo a justificativa.

Ordem judicial expressa pode prevalecer sobre instrumento notarial que a executa; declarações fortes e incompatíveis não são resolvidas pela ordem em que aparecem. Referências antigas, negativas, instrumentos sem efeito e ausência de dado não são tratados como confirmação do cadastro da Tri7. Não existe promessa de precisão de 100% em documentos futuros: testes sintéticos são regressão técnica, não validação jurídica independente ou medição de acerto em produção.
