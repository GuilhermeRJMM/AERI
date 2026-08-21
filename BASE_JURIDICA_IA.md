# Base jurídica e agente de análise do AERI

## O que foi construído

O agente jurídico faz parte da consulta do módulo **Ônus & Matrícula**. Não existe botão para acioná-lo: ao pesquisar uma matrícula, ele recebe o texto em memória, consulta a base normativa e executa uma análise jurídica própria dos três domínios obrigatórios: ônus, dados do imóvel e proprietários atuais.

O fluxo é:

1. o AERI consulta a matrícula na Tri7 e calcula o resultado determinístico;
2. o banco localiza até dez trechos jurídicos relacionados aos atos encontrados;
3. o texto é enviado em memória ao agente, com CPF, CNPJ e e-mail mascarados;
4. o agente analisa obrigatoriamente ônus, dados do imóvel e proprietários atuais, formulando seu próprio resultado em cada domínio e citando exclusivamente as fontes recebidas;
5. o backend rejeita citação inventada e não aceita conclusão afirmativa sem fonte;
6. a análise estruturada retorna junto com o resultado da consulta e é exibida automaticamente.

O texto integral da matrícula não é salvo. O banco persiste o hash do resultado, o hash da base, a análise, as fontes citadas e as métricas de uso. Se a matrícula ou a base mudar, a análise anterior não é reutilizada.

## Carga das fontes

O importador aceita PDF, DOCX, TXT, pastas e pacotes ZIP. O pacote é validado contra caminhos maliciosos, quantidade e tamanho excessivos. Arquivos repetidos são reconhecidos por SHA-256.

Exemplo, com a conexão do banco definida no ambiente:

```powershell
python -m scripts.indexar_fontes_juridicas "T:\Setor Registro de Imoveis\Legislacoes e Orientacoes" --usuario ADMIN
```

Para medir a extração sem gravar:

```powershell
python -m scripts.indexar_fontes_juridicas "C:\caminho\normas.zip" --simular
```

PDFs digitalizados sem camada de texto aparecem como `sem_texto` e precisam de OCR antes da carga definitiva. Não se deve considerar uma base pronta enquanto houver fontes essenciais nessa situação.

## Configuração da IA

O recurso nasce desativado. São necessárias as variáveis:

- `AI_GATEWAY_API_KEY` ou `VERCEL_OIDC_TOKEN`;
- `AERI_AGENTE_JURIDICO_LIMITE_DIA`, com valor maior que zero;
- `AERI_AGENTE_JURIDICO_MODELO`, opcional, com padrão `openai/gpt-5.4`.

Todo usuário autorizado a processar matrícula recebe a análise automática. A cota diária limita custo e exposição desnecessária de dados.

## Governança das normas

As fontes precisam ser classificadas e revistas antes de serem marcadas como vigentes. A ordem prática de confiança é:

1. Constituição, leis e decretos em fonte oficial;
2. Código Nacional e atos do CNJ;
3. Código de Normas e atos da Corregedoria de Goiás;
4. legislação estadual e municipal;
5. decisões, orientações, ofícios e termos aplicáveis à serventia;
6. doutrina, apenas como apoio e nunca para superar fonte primária.

Essa ordem não resolve antinomias por si só. Data, especialidade, competência, vigência e decisões vinculantes ainda exigem conferência humana.

## Lacunas identificadas em 21/08/2026

O material recebido já contém uma base ampla, mas o Código Nacional anexado não contempla todas as mudanças de 2026. Antes da ativação em produção, devem ser obtidas em fonte oficial e indexadas, conforme a pertinência ao Registro de Imóveis:

- texto vigente do Provimento CNJ 149/2023, incluindo alterações posteriores ao Provimento 194/2025;
- Provimentos CNJ 214/2026, 217/2026, 237/2026, 242/2026 e 246/2026;
- Lei 8.935/1994;
- Lei 13.709/2018 (LGPD), para o próprio tratamento de dados do AERI;
- Lei 11.977/2009 e Lei 10.257/2001;
- Lei 12.651/2012 e normas vigentes de CAR/reserva legal;
- normas atuais do INCRA/SIGEF, incluindo IN 77/2013, Portaria 2.502/2022 e Manual de Gestão da Certificação;
- versão vigente do Código de Normas do Foro Extrajudicial de Goiás e alterações posteriores ao Provimento 141/2025;
- legislação municipal posterior aos arquivos da pasta, especialmente alterações de logradouro, parcelamento do solo, Plano Diretor, Código de Obras e ITBI.

Referências oficiais verificadas durante o levantamento:

- CNJ, Provimento 149/2023: https://atos.cnj.jus.br/atos/detalhar/5243
- CNJ, Provimento 214/2026: https://atos.cnj.jus.br/atos/detalhar/6743
- CNJ, Provimento 217/2026: https://atos.cnj.jus.br/atos/detalhar/6775
- CNJ, Provimento 246/2026: https://atos.cnj.jus.br/atos/detalhar/3274
- INCRA, certificação de imóvel rural: https://www.gov.br/incra/pt-br/assuntos/governanca-fundiaria/certificacao-imoveis
- SIGEF, documentos e manuais: https://sigef.incra.gov.br/documentos/manual/

## Limite jurídico e operacional

Nenhum modelo garante acerto de 100%. O agente analisa o texto e fundamenta seu resultado; casos inconclusivos ou de atenção devem entrar na fila de auditoria e, se confirmados, virar teste de regressão e correção do sistema.
