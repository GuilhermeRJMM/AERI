# Integração AERI com o MAPA-ONR

## Arquitetura

O conversor MAPA-ONR permanece como componente legado. Os arquivos originais em
`backend/static/mapa_onr/src` não são alterados pela integração híbrida.

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
