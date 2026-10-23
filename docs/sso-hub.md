# SSO HUB → AERI

## Estado e escopo

Receptor novo: `POST https://aeri-two.vercel.app/api/auth/hub/exchange`.
Independente de `/api/login/sync` e da configuração RSA legada. Não faz chamadas à API central do HUB, não abre CORS e não cria contas ou permissões.

Sem configuração Ed25519 válida, responde genericamente com 503. O login por senha permanece inalterado. A implementação, por si só, não significa que a integração HUB esteja ativa em produção.

## Configuração e ativação pelo administrador

1. Receber do HUB somente a chave **pública** Ed25519 hexadecimal minúscula (64 caracteres) e o `kid`. Nunca copiar a chave privada.
2. Configurar no ambiente de produção Vercel `AERI_HUB_SSO_PUBLIC_KEY_HEX` e `AERI_HUB_SSO_KID`. O receptor exige que o `kid` seja `sso-` seguido dos primeiros 16 caracteres hexadecimais do SHA-256 dos 32 bytes da chave pública.
3. Aplicar a migração aditiva `063_sso_hub.sql`, normalmente pelo mecanismo existente de migrações do AERI. Não altera contas, senhas ou permissões existentes.
4. Com autorização administrativa, cadastrar na tabela `vinculos_sso_hub_aeri` um vínculo explícito entre emissor `sync-hub`, `subject` (UUID imutável informado pelo HUB) e `usuario` exato da conta AERI existente. Conferir a identidade nos dois sistemas antes de cadastrar. Não inferir pelo `preferred_username`, nome ou e-mail. A chave primária impede dois vínculos para o mesmo emissor/subject.
5. Publicar a configuração e testar com o HUB atualizado, incluindo a troca de uma sessão de outra conta e posterior logout. A navegação inicial de `/` deve carregar sem redirecionamento. O transporte deve preservar `Host: aeri-two.vercel.app` e `Origin: https://aeri-two.vercel.app`.

Não há interface pública para criar vínculos. O cadastro é feito pelo administrador do banco, por comando parametrizado; nunca registrar tickets ou credenciais em scripts versionados. A integração não é OIDC completo nem implementa logout global do HUB.

## Contrato e segurança

- Corpo JSON UTF-8 contendo exclusivamente `ticket`, até 8192 bytes inclusive quando enviado em partes; somente `Content-Type: application/json`.
- Origin e Host exatos e únicos. Não confiar no `X-Forwarded-Host` fornecido pelo chamador nem liberar previews automaticamente. Não aceitar query string; fragmentos não chegam ao servidor e nunca devem transportar credenciais.
- JWT compacto canônico: cabeçalho exatamente `typ=JWT`, `alg=EdDSA` e `kid` configurado. Assinatura Ed25519 validada antes de usar claims. JSON com chaves duplicadas ou constantes não JSON é rejeitado.
- Emissor exato `sync-hub`, audiência string exata `aeri`, `sub` e `jti` UUIDs canônicos. `iat`/`exp` inteiros, duração positiva até 60 segundos e tolerância fixa de 5 segundos. `preferred_username` não decide a conta.
- A transação bloqueia o vínculo e a conta ativa, revalida a expiração depois da espera por lock, consome o `jti` com chave primária e `ON CONFLICT DO NOTHING`, revoga a sessão cujo cookie foi recebido e cria a sessão normal do AERI. Uma falha desfaz essas alterações juntas. Tickets consumidos ficam até expiração mais tolerância; a limpeza ocorre nas trocas subsequentes.
- Resposta de sucesso: 200, `{"ok":true}`, cookie atual `HttpOnly`, `Secure`, host-only, SameSite vigente e cache desabilitado. Identificador novo inclusive quando a conta é a mesma. Duração de 8 horas, inatividade de 30 minutos e atualização agrupada de 5 minutos continuam no serviço existente.
- Assinatura, claims, replay, ausência de vínculo e conta inativa retornam a mesma mensagem genérica, sem novo cookie. Erros de transporte/configuração/indisponibilidade também não revelam contas. Auditoria de sucesso registra apenas a ação e a identidade local, nunca o ticket, cookie ou corpo.
- Não altera MFA local nem exige MFA extra no fluxo HUB. Autorizações e eventuais exigências locais de troca de senha continuam nas dependências existentes.

## Rotação e retorno ao acesso local

O receptor aceita um único par público chave/kid fixado por configuração. Coordenar a troca no HUB e no AERI; não buscar chaves desconhecidas a partir do ticket. Após rotação, tickets da chave antiga falham, mas sessões já criadas seguem as regras normais. Remover a configuração desativa somente novas trocas HUB; não revoga automaticamente sessões emitidas. Revogar sessões pelos controles administrativos existentes quando necessário.

## Reconciliação recebida em 23/10/2026

O responsável forneceu `Usuarios-HUB-SSO-AERI-2026-10-23.docx`, com 51 UUIDs únicos e canônicos. O documento informa oito contas ativas no HUB e 43 com primeiro acesso pendente.

Pelo importador administrativo `scripts/vincular_usuarios_hub.py`, foram vinculadas 45 identidades a contas ativas com proveniência da importação Sync, sem alterar permissões, estado ou senha. A migração 063 foi aplicada na mesma transação; cada vínculo registrou auditoria. Lote: `42314fcd-65d9-423b-a551-6bd6c2b907df`.

Cinco identidades não têm conta local correspondente e uma corresponde a conta desativada; nenhuma foi criada ou reativada automaticamente. A reexecução em somente leitura confirmou 45 já vinculadas e as mesmas seis pendências. Essa tabela foi configurada pelo documento revisado, não por login declarado em um ticket recebido.

Na preparação desta publicação, a chave pública Ed25519 e o `kid` fornecidos pelo responsável foram configurados exclusivamente no ambiente de produção Vercel. O código do receptor integra esta atualização; confirmar a implantação READY e suas sondas no domínio canônico após o envio. As contas pendentes no HUB devem concluir o primeiro acesso lá. A integração de ponta a ponta somente poderá ser considerada operacional após o teste conjunto com o HUB.

## Validação

`tests/test_sso_hub.py` usa chaves/identidades sintéticas e testa assinatura, claims, entrada restrita, cookies, replay, substituição e indisponibilidade. `tests/test_sso_hub_postgres.py` é opt-in com `AERI_TEST_POSTGRES_URL`: deve apontar para banco **de testes**, nunca produção. Verifica concorrência na tabela real e rollback da rotação. O teste de ponta a ponta com WebView/Host da Vercel e a chave do HUB permanece para a ativação conjunta.
