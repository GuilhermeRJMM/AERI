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
- Campo **Decisão Judicial** por R./AV., opções vazio/Sim/Não, inicialmente vazio; não inferido de palavras como inventário ou sentença. Usa a chave oficial `decisao_jud` do manual 1.3.0 em cada registro exportado, sem criar atributo alheio ao contrato.
- Versão 1.2.0 não admite `decisao_jud`: **Sim** gera pendência específica, impedindo eliminar o campo e utilizar silenciosamente a dispensa de dados. Selecionar 1.3.0 só quando o destino aceitar essa versão; o campo não é enviado à Tri7. **Não** mantém as exigências normais de preenchimento.
- Testes sintéticos cobrem cronologia, casal sem documentos repetidos, homônimos, documento contraditório, grafia divergente condicionada, campos independentes por ato e compatibilidade de exportação. Dados reais e credenciais não são versionados.
