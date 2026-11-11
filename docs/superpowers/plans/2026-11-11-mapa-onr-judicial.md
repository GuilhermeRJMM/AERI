# MAPA-ONR: esquemas oficiais e reconhecimento judicial

> Execução nesta conversa: seguir superpowers:executing-plans, com testes antes das alterações e revisão própria ao final.

**Objetivo:** atualizar a validação para o pacote ativo 1.3.0 da ITN 003 e preencher o cumprimento de decisão judicial por ato com evidência, sem transformar referências históricas, negativas ou documentos extrajudiciais em decisões.

**Especificação:** pedido autorizado nesta conversa em 11/11/2026, após diagnóstico dos esquemas locais 1.2.0 e de quatro classes de títulos não reconhecidas.

**Arquitetura:** preservar o conversor local e as duas validações. Instalar cópias intactas dos esquemas oficiais atuais e seus wrappers JS, com origem e hash registrados. Identificação judicial determinística, sem LLM, rede operacional nova ou escrita na Tri7.

**Tecnologias:** JavaScript existente, JSON Schema Draft 7, FastAPI/jsonschema e testes Node/Python/navegador existentes.

## Restrições

- Português, tema branco, sem mudanças nos demais módulos ou dados reais.
- Não usar Sim para simplesmente liberar campos faltantes.
- Ato atual separado do histórico e decisões não herdadas entre atos.
- Seleção manual continua prevalecendo; ausência de prova não vira Não automaticamente.
- Compatibilidade 1.2.0 somente com esquema próprio; padrão 1.3.0.
- Não instalar dependências; preservar arquivos não relacionados.

## Pontos de revisão

- Sentença arbitral e mera certidão processual não são decisões estatais por palavra-chave.
- Escritura autorizada por alvará não é automaticamente cumprimento judicial do registro.
- Cancelamento de gravame judicial pode ser o próprio cumprimento da decisão atual.
- Alvará negado, ordem revogada e referência ao registro anterior não justificam Sim.
- Navegador e servidor precisam aceitar/rejeitar o mesmo arquivo por versão.

## Tarefa 1 — Esquemas

- [x] Criar testes de versão ativa, ramo judicial urbano/rural, enums/formatos e compatibilidade antiga.
- [x] Executar e confirmar falhas com o esquema antigo.
- [x] Obter pacote ativo pelo catálogo público indicado no portal RI Digital, conferir origem e hashes, instalar os dois JSONs e gerar wrappers mecanicamente.
- [x] Atualizar seleção de versão, validação por versão no cliente/servidor e rótulos, preservando legado explicitamente.
- [x] Executar regressões de esquema, builder e backend.

## Tarefa 2 — Reconhecimento por ato

- [x] Criar casos novos positivos (formal, alvará cumprido, acórdão, alienação, autos/termos) e adversariais independentes.
- [x] Confirmar falhas antes de alterar o detector.
- [x] Ampliar a análise contextual com evidências e manter o isolamento entre atos.
- [x] Executar os 1.000 casos existentes e as regressões de qualificação/titularidade.

## Tarefa 3 — Integração e publicação

- [x] Conferir interface real no navegador com dados sintéticos; download 1.3.0, manutenção manual e backend.
- [x] Rodar a suíte completa disponível e documentar eventuais limites/falhas preexistentes.
- [ ] Revisar diff, versionar somente esta correção, publicar em main e confirmar implantação e saúde.

## Registro de execução e decisões

- Base: `53db5c9`. Checkout real: worktree `aeri-protocolo-notas-20261106`; Desktop/AERI não estava disponível. Nenhum dado real alterado.
- Ruling: ampliar a função existente no app.js, sem criar módulo global novo — preserva os carregadores e testes da integração; custo é manter a função no arquivo atual.
- Ruling: não endurecer `additionalProperties: {}` do ramo judicial oficial — os JSONs publicados permanecem intactos; só são exigidos os campos do esquema e as regras locais existentes.
- Ruling: não corrigir falhas de outros módulos nesta publicação — seis falhas da suíte completa foram reproduzidas em checkout limpo de `53db5c9`, sem estas alterações. São fixture de contratos cifrada inválida, duas dependências de diretório output/relatorios, duas expectativas antigas de buscas e rodapé de notas.
- Ruling: não aplicar ausência de ordem específica como negativa universal — hipoteca judiciária pode decorrer de sentença condenatória. Expedientes meramente informativos de carta/mandado são tratados separadamente.
- RED observado para schemas 1.3 antes da mudança; campo urbano removido também teve teste falhando antes da correção.
- Testes novos de reconhecimento e os achados da revisão independente tiveram RED → GREEN; 1.294 testes Node do MAPA-ONR passaram, incluindo os 1.000 casos anteriores. São testes sintéticos, não uma taxa de acerto de produção.
- Pytest geral: 2.533 passaram, 6 falharam, 11 ignorados, 278 subtestes passaram. As mesmas seis falhas foram reproduzidas na base. Pytest MAPA-ONR: 49 passaram, 12 subtestes passaram.
- Browser plugin not available: usado Playwright/Chrome já instalado. Interface nativa, desktop 1440×1000 e viewport 390×844, oito validações pelo serviço Python real; exportação 1.3 rural/urbana, correção manual, bloqueio 1.2 judicial, aba externa 1.3/1.2 e JSON inválido sem erros de console. Transporte e sessão simulados; não foi feito envio à ONR ou teste com dados reais.
- Browser de qualificação histórica existente também passou: qualificação anterior preservada e decisão isolada por ato.
- `.gitattributes` impede conversão CRLF dos JSONs oficiais para preservar os hashes em novos checkouts Windows.
- Revisão independente final: sem achados críticos/importantes pendentes; 237 testes Node focados, 18 pytest e browser confirmados pelo revisor. Reconhecimento permanece heurístico, com evidência e correção humana, não garantia de cobertura jurídica universal.
