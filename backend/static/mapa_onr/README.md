# Conversor ONR — matrícula para JSON de importação

Converte o texto de uma matrícula (Livro 2) no arquivo JSON de importação exigido
pela ITN 003/2025 do ONR, e valida o resultado contra o **schema oficial** antes
de liberar o download.

## Como usar

Abra o **`index.html`** no navegador, ou acesse a versão publicada. Não precisa
instalar nada, não precisa de servidor, não precisa de internet — é HTML e
JavaScript puros, tudo local.

Para levar a ferramenta num arquivo só (pendrive, e-mail, outra máquina), rode
`tools/build-inline.ps1`: ele gera um `Conversor-ONR.html` autossuficiente, com
CSS, JavaScript e schemas embutidos.

1. **Cole a matrícula inteira**, do primeiro ato ao último. Mesmo que você só vá
   exportar um ato, a leitura completa é o que apura a área, o CAR/CCIR/CIB e o
   regime de bens vigentes de cada pessoa.
2. **Marque quais atos entram na remessa.** Todos vêm marcados; desmarque o que
   não for enviar.
3. **Revise.** O que o parser encontrou já vem preenchido, com o trecho da
   matrícula que originou cada valor logo abaixo do campo.
4. **Valide e gere.** O que faltar aparece como pendência com o motivo
   ("obrigatório se `motivo_envio = 1`"), nunca preenchido por conta própria.

A aba **Validar JSON existente** confere um arquivo de remessa já pronto contra o
schema e agrupa os erros por campo — serve para auditar remessas antigas.

## Publicação na Vercel

O projeto é estático — não tem build, não tem dependências. Na Vercel, importe o
repositório e deixe o framework como **Other**, sem comando de build e com o
diretório de saída na raiz. O `index.html` é servido direto.

O `vercel.json` já define `X-Robots-Tag: noindex`, para a ferramenta não ser
indexada por buscadores.

A página publicada é **acessível a quem tiver o endereço**. Sendo uso interno da
serventia, vale proteger o acesso na Vercel (Deployment Protection). Nada é
enviado para servidor nenhum: o conversor roda inteiro no navegador, e a matrícula
que você cola não sai da máquina.

## Testes — e por que não estão aqui

São **219 testes** (76 de schema e regras + 143 de extração), calibrados contra o
texto real de cinco matrículas do acervo. Eles **não são publicados**: as fixtures
contêm nomes, CPF/CNPJ e endereços de pessoas identificadas, e este repositório é
público. `tests/` está no `.gitignore` por isso.

A suíte fica na máquina da serventia; para rodar, abra `tests/run-tests.html` no
navegador. Quem clonar daqui recebe o código e os exemplos sintéticos da pasta
`exemplos/` — suficientes para usar e conferir a ferramenta, mas não para
reproduzir a calibração.

## O que está dentro

```
index.html                 aplicação
exemplos/                  matrículas sintéticas para os botões de exemplo
src/parser.js              matrícula (texto) -> atos + preâmbulo
src/extrator.js            extração automática de cada campo, com evidência
src/builder.js             fichas -> objeto do imóvel + regras condicionais do manual
src/validator.js           validador JSON Schema (subconjunto usado pelo ONR)
src/enums.js               glossário de enums v1.3.0
src/documento.js           dígito verificador de CPF/CNPJ (inclusive alfanumérico) e do CNM
src/app.js                 interface
schemas/*.schema.json      schemas oficiais do Anexo II (cópia intacta)
schemas/*.schema.js        os mesmos, embrulhados em JS (file:// não faz fetch de .json)
docs/divergencias.md       divergências entre manual e schema, e o que fazer
tools/build-inline.ps1     gera o Conversor-ONR.html (arquivo único)
tools/gerar-schemas-js.ps1 regera schemas/*.schema.js a partir dos .json oficiais
tools/servir.ps1           servidor local para teste (não há Node nesta máquina)
```

## Decisões que valem saber

**Validação contra o arquivo oficial, não contra regra reescrita à mão.** Os
schemas do Anexo II são versionados junto com o projeto e usados como fonte da
verdade. Regra reescrita a partir do PDF erra em silêncio; o schema não.

**`motivo_envio` é calculado, não digitado.** É comparação de data com o corte de
02/12/2025 — aritmética, não julgamento. Se a data do ato não for confiável, vira
pendência em vez de virar chute.

**CIB e NIRF são campos diferentes.** O parser captura os dois separadamente e
avisa quando acha NIRF sem CIB. Preencher `cib` com o NIRF passa na validação de
formato e entrega dado errado — o pior tipo de erro.

**Nada é inventado, mas o que é dedutível é preenchido.** Há duas categorias
diferentes, e a ferramenta não as mistura:

- *Dedutível do próprio documento* — o proprietário vigente num ato que não
  qualifica ninguém, o regime de bens que outro ato declarou, o dígito do CNM.
  Isso é preenchido e listado no painel "Preenchido automaticamente", com a
  origem de cada item.
- *Ausente de verdade* — CPF que não consta, regime que a matrícula não diz.
  Isso vira pendência com o motivo, nunca um palpite.

**O dígito verificador de CPF/CNPJ é conferido** — nem o schema nem o manual
fazem isso, e um documento com um dígito trocado passa nos dois. Quando a
matrícula traz só a base de 9 dígitos (formato antigo), a ferramenta calcula o
único DV possível e **oferece** o CPF completo num botão, para você conferir no
documento e aprovar. Nunca aplica sozinha: se a base estiver transcrita errada, o
cálculo produz um CPF válido de outra pessoa.

## O que é preenchido automaticamente

Calibrado sobre o texto real de **cinco** matrículas do acervo — uma rural de 56
atos, uma urbana, uma com usufruto/doação/permuta/dação, uma com edificação e uma
com servidão/desapropriação. Cada campo vem com o trecho de origem embaixo, para
conferência:

**Do imóvel** (varrendo o documento inteiro, valor rotulado mais recente vence):
número e data da matrícula, nome do imóvel, CIB, CCIR, COD_SNCR, CAR (normalizado
dos 41 caracteres com hífen do recibo), CEP, área total, georreferenciamento,
certificação INCRA, sistema de coordenadas e de referência, código IBGE do
município e UF, e a lista de confrontantes.

**De cada ato**: data (do cabeçalho, não a primeira do corpo), tipo do ato,
classificação do ato e da transmissão, valor da transação, imposto recolhido e
base de cálculo, número e data do protocolo, e as partes — com nome, CPF/CNPJ,
papel (transmitente/adquirente/credor/avalista), estado civil, regime de bens e
percentual.

**O CNM é calculado**, não digitado. Ele não consta na matrícula, mas é dedutível
do CNS + número + dígito verificador ISO 7064 MOD 97-10 (algoritmo deduzido de 7
CNM reais da serventia — ver `docs/divergencias.md`, item 6). Um CNM digitado à
mão tem o dígito conferido, e DV errado vira pendência dizendo qual era o certo.

O que sobra manual são apenas as escolhas que o texto não resolve — ver abaixo.

## Auto-correção: atos que não qualificam ninguém

A maior parte das averbações — CAR, CEP, CCIR/CIB, óbito, cláusulas restritivas —
não qualifica nenhuma pessoa no texto, mas o layout do ONR **exige**
`dados_pessoa`. Antes esses atos eram recusados por falta de parte.

A ferramenta agora rastreia a **titularidade vigente** ao longo da matrícula:

- as tabelas de "INDICAÇÃO DE TITULARIDADE" (AV.37, AV.43, AV.44) são o retrato
  oficial e **substituem** a lista de donos;
- fora delas, os adquirentes de cada ato de transmissão entram e os alienantes
  saem;
- os nomes da tabela (que não trazem CPF) são casados com os CPFs qualificados em
  outros atos, trazendo junto estado civil e regime.

Num ato sem parte própria, entram os proprietários vigentes como
`relacao_juridica: 1`, com percentual e data de início, e a linha na tela diz
*"vinculado automaticamente"*. O painel **"Preenchido automaticamente"** lista
tudo o que foi completado, com o motivo de cada item.

As demais auto-correções: `valor_imposto: 0` quando o ato é transmissão e o texto
não cita imposto; `percentual: 100` para titular único e `0` para quem não tem
percentual próprio (credor, avalista, anuente); `data_inicio_rel_juridica` igual à
data do ato; `estrangeiro: false` quando nada indica o contrário;
`relacao_juridica: 1` para quem é citado sem papel mas consta como proprietário;
e o **CPF antigo de 9 dígitos completado** pelo mesmo número que aparece inteiro
em ato posterior — o mais recente é o correto.

### Regime de bens e a Lei 6.515/77

O regime legal mudou em 26/12/1977: antes era comunhão **universal**, depois
comunhão **parcial**. A ferramenta usa isso, nesta ordem:

1. o que o ato **declara** ("comunhão universal", "separação obrigatória");
2. o que o ato diz sobre a lei ("anteriormente à vigência da Lei 6.515/77" →
   universal, mesmo num ato de 2016);
3. `"regime da comunhão de bens"` sem qualificar, em ato **anterior a 1977** →
   universal, porque era o único regime legal possível;
4. só `"casados"`, sem regime nenhum → o regime legal da data do ato, marcado
   como **presunção** no painel.

**Declaração vence presunção, em qualquer ato.** Se um casal aparece apenas como
"casados" em dois atos, mas outros três declaram comunhão universal, é universal
que vale nos cinco. A presunção só permanece quando a matrícula inteira nunca diz
o regime daquela pessoa.

**Sanidade da titularidade:** se a soma dos percentuais não fechar 100%, a tela
avisa — o retrato da tabela pode ser anterior a atos posteriores de transmissão,
e aí a conferência é sua.

## Onde a ferramenta se recusa a decidir

- **Área parcial x total.** "10,67% do imóvel, equivalente a 32,8504ha" é a
  fração do negócio, não a área do imóvel. Só entra área rotulada como total,
  remanescente ou do CCIR — e quando há mais de uma, as outras aparecem numa
  lista para você trocar com um clique.
- **"Regime da comunhão de bens"** sem dizer se universal ou parcial: a diferença
  muda o direito, então aparecem dois botões para você escolher.
- **CPF sem dígito verificador**: sugestão calculada num botão, nunca aplicada.
- **Valor em ato sem transação**: emolumentos, taxa judiciária, ITBI, valor da
  causa e valor de cédula rural nunca viram `valor_transacao`.
- **Representante legal** de pessoa jurídica é identificado e mantido fora das
  partes — quem representa não é parte do ato.
- **Cônjuge citado como "casado com X"** é marcado como cônjuge para você
  confirmar se entra como parte: depende do regime, e não é a ferramenta que
  decide isso.
- **Filiação não é parte.** "filho de X e Y" é qualificação do falecido, não duas
  pessoas do ato.

## Classificação do ato: vale o título, não o corpo

`INSTITUIÇÃO DE USUFRUTO` e `DOAÇÃO` podem citar **a mesma escritura** ("Instituição
Gratuita de Usufruto Com Doação de Nua Propriedade"), e `CLÁUSULAS RESTRITIVAS`
fala da "liberalidade da doação registrada no R.12". Classificar pelo corpo erra
os três. A ferramenta lê primeiro o **título** do ato (o rótulo em caixa depois do
protocolo) e só usa o corpo como reserva — e diz qual dos dois decidiu.

Refinamentos que vêm do tipo de ato:

| Ato | `ato` | Complemento |
|---|---|---|
| Venda e compra | 4 | titularidade 1 |
| Inventário/partilha | 4 | titularidade 9 |
| Doação | 4 | titularidade 6 |
| Permuta | 4 | titularidade 14 |
| Dação em pagamento | 4 | titularidade 5 |
| Desapropriação | 4 | titularidade 17 (outras onerosas) |
| Instituição de usufruto | 3 | beneficiário → `relacao_juridica` 2 |
| Doação da **nua** propriedade | 4 | donatário → `relacao_juridica` 3 |
| Servidão | 3 | beneficiário → `relacao_juridica` 18 |
| Hipoteca / cédula rural | 3 | credor → 18 |
| Estremação | 5 | `alteracao_imovel` 6 |
| Retificação de área | 5 | 10 |
| Edificação | 5 | 12 (Outro — o enum não tem item próprio) |
| CEP, CAR, CCIR/CIB, óbito, cláusulas restritivas | 6 | — |

## Rural e urbano

O seletor **tipo do imóvel** troca os campos, as regras e o schema de validação.

No urbano o schema é mais exigente no endereço — pede `tipo_logradouro`,
`logradouro`, `numero_logradouro`, `cep`, `cod_ibge_municipio` e `uf` —, então a
extração quebra o endereço em pedaços: "Rua Exemplo esquina com a Rua Segunda
Via, Nº197, Setor Modelo, 2ª Etapa" vira tipo 250 (Rua),
logradouro, número 197 e bairro, com quadra/lote no complemento.

Três cuidados que o urbano exigiu:

- **Área construída não é área do terreno.** "Casa residencial com 59,98m² de
  área construída" e "terreno [...] com a área de 246,50m2" são coisas diferentes;
  só a segunda vai para `area_terreno_total`, e a construída é mostrada à parte
  (o layout não tem campo para ela).
- **Endereço só vale da abertura ou de ato que altera o imóvel.** Num ato de
  transmissão, "Quadra 03, Lote 16" é onde as partes *moram*, não o imóvel.
- **`cif`** sai do cadastro da Prefeitura ("CCI n.º 10.630" ou "Cadastrado na
  Prefeitura sob o Nº...").

## Limitações conhecidas

- Contextos **União** (2) e **Estrangeiros** (3) têm as regras implementadas em
  `builder.js`, mas ainda sem campos próprios na interface — só Padrão (1) está
  exercitado ponta a ponta, no rural e no urbano.
- Averbações cadastrais (CAR, CEP, CCIR/CIB, óbito, pacto, premonitória) entram
  como `ato: 6` (Outro), por decisão da serventia, com o motivo registrado.
- Os polígonos do memorial georreferenciado (AV.55 tem ~200 vértices) não são
  transcritos para `coordenadas`: o campo aceita 3000 caracteres no schema
  publicado. O centróide do CAR é capturado e fica disponível.
- Matrícula só é lida como **texto**. PDF precisa ser copiado e colado.
