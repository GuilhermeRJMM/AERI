# AERI — Institucional moderna

Base compartilhada, navegação por setores e padronização transversal das telas.
Referência: proposta A, nó 2:124 do arquivo
https://www.figma.com/design/4rxZJBXcuqEMPszTrdPgJs

## Contrato visual

- Conteúdo branco, navegação navy, ação principal esmeralda e fonte Outfit.
- Tokens semânticos em backend/static/tokens.css e componentes em backend/static/design-system.css.
- Superfícies, texto secundário, bordas, foco e estados usam os tokens --aeri-*.
- Intimações usa backend/static/intimacoes-mesa.css, sem duplicar uma paleta.
- A ordem de folhas é legado, painel, RTD, Sync, Design System e Mesa.
  O carregamento do RTD não pode reposicionar o tema no fim do documento.
- Botões nativos e breadcrumb conservam as permissões e o histórico do navegador.
- Os estados operacionais verde, amarelo, vermelho e cinza permanecem distintos,
  com rótulos textuais. Campos desabilitados não devem usar opacidade sobre texto.

## Limites do lote

Não altera APIs, banco, cálculo de prazos, autenticação HUB, permissões,
pesquisa, motor registral, vínculo RTD ou regras de conferência.
O menu legado continua oculto: a navegação visível permanece por setores.
Outros módulos conservam seus layouts; somente componentes compartilhados
recebem as novas definições básicas.

## Validação

- python -m unittest tests.test_design_system
- tests/browser_mesa_intimacoes.cjs: dados sintéticos; bloqueia rede externa.
- tests/browser_sessao_hub.cjs: sessão HUB e navegador.
- tests/browser_buscas_pdf.cjs: exportação PDF existente.

Os scripts de navegador exigem Playwright e Chrome já disponíveis no ambiente.
Não é preciso adicioná-los às dependências de produção.
Capturas de teste são gravadas na pasta temporária, não no repositório.

## Padronização progressiva dos componentes — 29/10/2026

A base reaproveita CSS nativo e os seletores existentes; não incorpora o Tailwind
compilado do Sync nem muda o backend. Campos e ações têm altura mínima de 44px,
foco visível, borda legível e fundos claros opacos. Campos readonly continuam
selecionáveis. Checkbox, rádio, arquivo, range, cor e controles ocultos conservam
suas dimensões próprias. A autenticação mantém seu layout específico.

Botões primários usam verde escuro com texto branco legível. Botões desabilitados
têm cores explícitas, sem opacidade sobre o texto. Ações destrutivas existentes
não recebem um verde genérico. Cabeçalhos de tabela usam a mesma tipografia;
as cores operacionais das linhas não são sobrescritas pela base.

Novos componentes opcionais:
- `aeri-button` com variantes `--primary`, `--secondary`, `--danger`;
- `aeri-alert` e `aeri-status` com `data-state` success, warning, error ou info;
- `aeri-empty` para uma mensagem textual de ausência de resultados;
- `aeri-button[aria-busy="true"]` para processamento (o código consumidor
  deve fornecer rótulo acessível e controlar a operação; CSS não bloqueia ações).

Usar mensagens textuais para erro, confirmação e carregamento; a cor não basta.
Nenhuma validação, permissão ou confirmação operacional deve ser feita em CSS.

O acesso ao nó de referência no Figma foi tentado nesta etapa, mas a integração
retornou limite de chamadas do plano Starter. Não houve alteração do arquivo
Figma nem alegação de validação pixel a pixel. A validação desta etapa é feita
no navegador com os templates e estilos reais, dados sintéticos e rede bloqueada.

Teste adicional: `node tests/browser_design_system.cjs`.

## Cobertura transversal — 29/10/2026

- Fundação única para a aplicação, MAPA-ONR isolado/embutido e as três interfaces
  independentes do Gerador de Notas. Estilos legados mantidos por compatibilidade;
  não há importação integral do Tailwind ou dos módulos exclusivos do Sync.
- Login com cartão branco, marca existente sobre navy e campos legíveis. Não muda
  senha, sessão HUB, MFA, logout ou fluxo de troca obrigatória de senha.
- Cabeçalhos, cartões, botões, controles de arquivos, tabelas e estados de
  processamento padronizados. A navegação e os módulos conservam seus destinos.
- MAPA-ONR não alterna para dark pela preferência do Windows; o modo embutido
  conserva seu comportamento de ocultar o cabeçalho e receber o texto do AERI.
- Botão de fechar com alvo de 44px e camada acima do cabeçalho. Atributo `hidden`
  continua respeitado, inclusive na troca de senha obrigatória.
- Não altera jogos/atalhos recreativos, PDFs emitidos, conteúdo das minutas,
  informações dos registros, permissões ou integrações. Essas superfícies não
  devem receber mudanças de conteúdo em uma atualização somente visual.

Validação adicional:
- `node tests/browser_sistema_visual.cjs --exigir-limpo`: 18 páginas × 2 larguras
  e 12 modais × 2 larguras; mais login, imagem da marca e progresso de Minutas.
  Renderiza os templates com includes e usa os renderizadores reais de painel,
  configuração, intimações, análise registral e detalhes RTD com dados sintéticos.
- `node tests/browser_interfaces_independentes.cjs`: 20 combinações de interface,
  largura, preferência de cor e modo embutido do MAPA-ONR.
- Testes existentes de Mesa, PDF de Buscas e sessão HUB continuam separados.

Limite da validação: os testes visuais não usam o banco nem enviam documentos,
não constituem validação completa de todos os fluxos operacionais em produção
e não substituem o teste com dados reais feito pelo setor após a publicação.
