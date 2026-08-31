# AERI — setores, automações e Contratos e Minutas

Implementação de 31/08/2026, autorizada para publicação pelo usuário. Ponto de retorno e procedimento de reversão em `VOLTAR_VERSAO_ANTERIOR.md`. As verificações descritas abaixo distinguem testes locais de ativação da infraestrutura.

## Organização e preservação

A tela inicial após login passa a ser o dashboard. O setor Certidão reúne Ônus e Matrícula, Buscas, INCRA, Livro de Protocolos, Informar Custas, Registro Auxiliar e Rotina — Intimação. RGI reúne MAPA-ONR, Polígonos, Gerador de Notas, Auditoria registral e Contratos e Minutas. Usuários e Acessos e Integrações/agendamentos ficam em Administração/Sistema.

Os módulos antigos permanecem. O registro de navegação `.nav-item` foi mantido oculto para compatibilidade, mas a navegação principal utiliza cards e breadcrumbs. As ferramentas administrativas de indexação que ficavam em Buscas foram movidas para Auditoria registral.

Arquivos principais: `backend/templates/painel.html`, `contratos.html`, `backend/static/painel.css`, `backend/static/js/painel.js`, `sistema.js`, `contratos.js`, `backend/app/servicos/painel.py`.

## Permissões e migração

O catálogo e as tabelas relacionais existentes são reutilizados. Não foi criado outro banco de usuários.

- ADM e Substituto: acesso integral.
- Novo perfil Usuário comum (`USUARIO`): nenhum acesso por padrão.
- Novos Supervisores: ambos os setores e os demais módulos, exceto Intimações e gestão de usuários; o administrador pode conceder ou negar individualmente.
- Contas existentes: a migração preserva as concessões anteriores, inclusive Supervisores, sem ampliar automaticamente seu acesso. Os defaults novos valem para novas contas; acessos antigos podem ser ajustados pela administração.
- Auditor: mantém as atribuições fixas e opcionais legadas.
- Um módulo exige a concessão do setor **e** do módulo no backend. Esconder um card não é a proteção de acesso.
- Negação individual (`concedida=FALSE`) prevalece sobre concessão herdada do perfil. Antes a união dos perfis com usuários não permitia essa revogação.
- Gestão delegada não pode promover administradores, modificar contas administrativas, alterar seu próprio acesso nem conceder gestão administrativa.

Migração aditiva `041_setores_e_paineis.sql`: catálogo, setores, fotografia dos acessos e tabelas de automação. Antes de alterar concessões, salva catálogo, perfis, concessões individuais e cargos em `backups_acessos_aeri` (versão `antes_setores_20260831`), sem senhas ou sessões. Migração `042_contratos_minutas.sql`: fila e histórico de contratos. Nenhuma tabela operacional antiga é apagada. Escrita dupla nas colunas legadas permanece para facilitar reversão.

## Livro de Protocolos e alertas

`backend/app/servicos/conferencia_livro.py` é o núcleo de conciliação utilizado tanto na rota manual quanto no executor. Ele usa `protocolo-completo`, textos de matrícula/Registro Auxiliar, atos confirmados e as regras existentes de conferência. Não compara cadastros de proprietários ou ônus da Tri7 com o analisador.

`automacoes_operacionais.py` mantém configuração, horário de Brasília, intervalos, leases com expiração e checkpoints em Postgres. Processa poucos protocolos por ciclo e retoma o restante. A última execução registra horário, duração acumulada, estado, quantidade e resultados. Uma regra alterada durante a execução interrompe a mistura de versões. Falhas/parciais não são apresentadas como conferência limpa.

A execução por data mantém a limitação atual da Tri7: pesquisa apresentações em três janelas cobrindo 90 dias e filtra a data de registro. Protocolos apresentados antes dessa janela podem exigir o PDF existente. Não se deve chamar esse recorte de cobertura ilimitada.

A conferência automática **não** reindexa silenciosamente toda a base de buscas. A atualização dos registros alterados pelo Livro manual foi preservada. Rodadas automáticas têm histórico separado em `execucoes_operacionais_aeri`; a comparação de rodadas manuais existente continua intacta.

Alertas de Intimações usam a regra visual preexistente, agora calculada no servidor: sem check = pendente; hoje = verde; ontem = amarelo; 2–4 dias = atrasada; mais de 4 = sem atividade. Isso não cria prazo jurídico novo. O cálculo do 16.º dia útil e o calendário existente não foram alterados. O dashboard mostra apenas os alertas dos módulos autorizados.

## Contratos e Minutas

Fluxo: protocolo → lista GED → seleção explícita → extração digital sob demanda → conferência da ficha → texto atual da matrícula → decisões justificadas → rascunho editável → histórico.

Correção de 31/08/2026: o botão registra/reaproveita o trabalho e chama `POST /api/contratos/{id}/extrair`, que processa somente aquele contrato na própria requisição. PDF com texto não depende de executor. Trabalhos pendentes anteriores podem ser retomados em “Meus trabalhos” → “Retomar extração”, inclusive quando já existem cinco pendências. O limite continua valendo para novos trabalhos.

A extração direta não liga agendas e não chama OCR. Documento em imagem ou página com imagem e texto insuficiente retorna falha explicativa, sem ficha parcial. Página digital curta sem imagem é preservada e sinalizada para revisão. O worker continua disponível para futura ativação, sem ser iniciado por essa rota.

Concorrência: trava de 90 segundos, revalidação do vínculo GED, gravação somente pelo detentor da trava e retorno sem sobrescrever trabalhos já extraídos/conferidos. Após interrupção, a trava expira e o mesmo trabalho pode ser retomado. Orçamento de extração verificado entre etapas: 45 segundos; cliente Tri7 isolado com timeout de 8 segundos e uma tentativa transitória, sem alterar a configuração compartilhada dos demais módulos. A tela limita a espera HTTP a 70 segundos e o acompanhamento a 95 segundos, orientando retomada em vez de polling infinito. Esses limites entre etapas não substituem o timeout de execução imposto pela hospedagem.

1. O cliente Tri7 centralizado consulta os documentos vinculados ao protocolo. Mesmo com um único arquivo, a escolha é explícita; versões ou anexos não são escolhidos por adivinhação.
2. Na seleção e no processamento, o backend verifica o vínculo do documento ao protocolo. Nome e caminho de rede originais não são expostos na listagem.
3. PDF digital: extração por página. PDF digitalizado, JPEG, PNG e TIFF: OCR automático local no executor. Windows usa OCR pt-BR; Linux usa Tesseract com português. Sem OCR instalado, a fila relata falha controlada, sem inventar dados.
4. Mantém texto original extraído, texto normalizado, SHA-256, método e confiança por página. Windows não informa confiança numérica: o sistema mostra essa ausência, não cria um percentual. Não troca automaticamente O/0, I/1 ou dígitos.
5. Limites: 60 MB, 100 páginas, 20 milhões de pixels por imagem, renderização OCR limitada e timeout por página. Há limite de cinco trabalhos pendentes por solicitante.
6. O núcleo do Preenchedor extrai ficha e produz os atos; o adaptador preserva empresas, cônjuges, procuradores e valores de terreno/obra.
7. A matrícula vem do endpoint de **texto**, processada pelo motor atual do AERI para situação, titularidade e ônus. Esses resultados podem conter erros; não são uma certificação de certeza jurídica.
8. Comparações de valores, credores e financiamento da nova operação não pressupõem igualdade com um financiamento antigo. Os itens sem equivalência direta exigem conferência, não substituição automática.
9. Decisão de utilizar valor da matrícula só é oferecida para campos substituíveis e disponíveis. A escolha altera efetivamente a ficha usada para gerar. Demais itens registram conferência manual. Justificativa é obrigatória para as decisões.
10. Alterar a ficha depois do confronto exige confrontar novamente. Versão otimista impede sobrescrever edição concorrente. A ficha extraída originalmente e as versões geradas/editadas permanecem distinguíveis.
11. O resultado é um **rascunho**. Pendências e marcadores devem ser resolvidos antes de utilização. Não envia nem registra atos na Tri7 e não valida assinatura digital.

O modelo inicial suportado é o conjunto de contratos habitacionais CAIXA reconhecido pelo projeto integrado. Não é um extrator genérico de qualquer contrato/banco. Documento sem identificação suficiente de contrato e partes falha com aviso. OCR depende da qualidade da imagem e exige conferência humana.

## Proteção dos documentos

Sessão revogável, troca obrigatória de senha temporária, CSRF e headers de segurança do AERI são mantidos. Cada trabalho é restrito ao solicitante; ADM/Substituto podem consultá-lo. Acesso ao módulo é revalidado pelo worker antes de processar. Credenciais Tri7 não são enviadas ao navegador.

Ficha, texto, decisões e versões são cifrados com Fernet antes de persistir. Configure `AERI_CONTRATOS_ENCRYPTION_KEY` (segredo aleatório de pelo menos 32 caracteres), igual no servidor web e no worker. Como compatibilidade, a chave já existente `AERI_BUSCAS_HMAC_KEY` pode ser usada com derivação de domínio separada. Não coloque valores no Git, no JS nem nesta documentação. A perda ou troca unilateral da chave impede ler o histórico: guardar em gerenciador seguro e planejar rotação/migração.

Não se grava cópia binária duplicada do PDF em cada versão; guarda-se referência GED e hash, além do texto cifrado. Ao baixar novamente o documento, o hash é comparado. Se mudou, o download retorna conflito e orienta nova extração, sem chamar a versão nova de original. Metadados (número de protocolo, documento e usuário) continuam presentes no banco. Proteja também backups, executor e acesso ao Postgres.

Logs de execução registram estados/identificadores, não os textos ou documentos pessoais. Arquivos temporários do OCR são removidos ao final do subprocessamento. As versões cifradas crescem com as edições; definir política institucional de retenção antes de uso prolongado.

## Ativação — infraestrutura necessária

O processamento direto de PDFs com texto funciona pela requisição do usuário. OCR e execução contínua ainda precisam de executor; o cron gratuito da Vercel não oferece a frequência de 30/60 minutos pretendida. O executor separado independe de navegador aberto.

1. Fazer backup e validar as migrações em banco de homologação antes de produção.
2. Instalar `requirements.txt` em Python compatível com o projeto (3.12 em produção).
3. Preparar um executor confiável, preferencialmente servidor da serventia: mesmas variáveis de Postgres e Tri7 do AERI, chave de cifragem e OCR Windows pt-BR ou Tesseract `por`. Não colocar segredos em argumentos de linha de comando.
4. Rodar `python scripts/worker_operacional.py --once` para um ciclo controlado de homologação. O comando prepara o banco configurado: conferir a conexão antes de executar.
5. Instalar `python scripts/worker_operacional.py` como serviço/tarefa supervisionada, sem janela e com reinício automático. Não deixá-lo dependente deste chat. `--intervalo 10` é a frequência de consulta da fila, não a frequência de conferência do Livro.
6. Em Administração → Integrações e agendamentos, habilitar dias/horários e intervalo. As agendas nascem desativadas para não iniciar carga de produção inadvertidamente.
7. Conferir horário do último sucesso e resultados. Testar desconexão, retomada e um contrato real autorizado em homologação antes de liberar aos funcionários.

Existe também `GET /api/sistema/cron`, protegido por `Authorization: Bearer CRON_SECRET` (mínimo 32 caracteres), para disparar ciclos de Livro/Intimações em infraestrutura compatível. Não há cron Vercel ativado automaticamente. OCR de contratos permanece no worker, fora do timeout serverless.

## Verificação realizada e pendências de implantação

- Suíte AERI após a correção de extração: 890 testes aprovados, 1 ignorado e 220 subtestes. Inclui isolamento por usuário, CSRF, escolhas de origem, GED inválido, fila, retomada sem duplicação, lease expirada/concorrente, bloqueio de OCR e permissões.
- Contrato real do protocolo 185.623, GED 252567: 19 páginas extraídas sem OCR em aproximadamente 4 segundos, usando leitura real da Tri7 e processamento local em memória. Modelo MO30173Av120 identificado. Isso não equivale a uma gravação autenticada da ficha no banco de produção nem a atestado de exatidão jurídica.
- Núcleo original: 145 testes executados, 10 ignorados pelo upstream, sem falhas.
- Contrato anexado: 19 páginas extraídas digitalmente; partes, modelo, venda e financiamento reconhecidos. Nenhuma transmissão a provedor de IA.
- OCR Windows real: leitura da primeira página rasterizada; nenhum índice de confiança fabricado.
- Navegador local: dashboard, dois setores, cards e fluxo de contrato com dados fictícios. Nenhum usuário ou documento operacional alterado por esses testes.
- Migrações 041/042 executadas em PostgreSQL descartável em memória (PGlite), com usuários fictícios: preservação de acessos antigos, setores herdados, defaults de novos Supervisores, negação individual, agendas desativadas e deduplicação da fila aprovadas. O teste não carrega `.env` nem acessa a produção.
- Publicação em produção em 31/08/2026: build Python 3.12 concluído; página e arquivos novos respondendo 200; rotas protegidas respondendo 401 sem autenticação, sem erro 500 na preparação do banco. Tela de login verificada no navegador. Não equivale a homologação autenticada de todos os fluxos.
- O executor persistente, a renovação real de lease após reinício e o fluxo completo GED→banco ainda dependem da escolha/configuração do servidor. Nenhum serviço Windows foi instalado nesta publicação. Agendas permanecem desativadas; OCR em produção não deve ser anunciado como ativo até essa configuração.

Para repetir o teste SQL local: instalar a dependência de desenvolvimento com `npm install --prefix tmp/teste-postgres @electric-sql/pglite --no-audit --no-fund` e executar `node tests/test_migracoes_setores.mjs`. O banco existe apenas em memória e não usa a conexão do AERI.

## Reversão

Antes de publicar, manter referência do commit/deploy anterior. Em reversão, parar o executor e desabilitar agendas primeiro. As migrações são aditivas: não apagar tabelas nem históricos para voltar a uma interface anterior. O código mantém colunas legadas sincronizadas, mas uma versão antiga pode não respeitar negações por setor; revisar permissões ao reverter. Não fazer rollback cego do banco de produção.
