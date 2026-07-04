# Segurança do AERI

## Proteções implementadas

- Senhas armazenadas com Argon2id e migração automática dos hashes PBKDF2 anteriores.
- Senha administrativa com no mínimo 14 caracteres, maiúscula, minúscula, número e símbolo.
- Sessões aleatórias e revogáveis persistidas no Postgres, com duração máxima de 8 horas e encerramento após 30 minutos de inatividade.
- Cookie de sessão `__Host-`, `Secure`, `HttpOnly`, `SameSite=Strict` e restrito ao caminho raiz.
- Token CSRF e validação de origem em todas as operações que alteram estado ou iniciam processamento.
- Bloqueio por 15 minutos após cinco falhas de login para a mesma combinação de usuário e IP.
- Auditoria de login, logout, análises e alterações de intimações sem armazenar senhas ou textos de matrículas.
- Contas individuais com perfis `ADMIN`, `OPERADOR` e `CONSULTA`, bloqueio imediato e troca obrigatória de senha temporária.
- Limite de 5 milhões de caracteres para matrícula, 15 MB para PDF e 16 MB por requisição.
- Cabeçalhos CSP, HSTS, anti-iframe, `nosniff`, política de referência e política de permissões.
- Consultas SQL parametrizadas, timeout de conexão e segredos somente em variáveis de ambiente.

## Variáveis obrigatórias na Vercel

- `POSTGRES_URL`: adicionada pela integração Neon/Postgres.
- `AERI_ADMIN_USER`: usuário administrativo.
- `AERI_ADMIN_PASSWORD`: senha forte usada somente para criar a conta administrativa inicial. Depois disso, a senha deve ser alterada pela opção **Alterar senha** do próprio AERI.
- `AERI_ORIGIN`: origem exata de produção, por exemplo `https://aeri.vercel.app`, sem barra no final.
- `AERI_AUDIT_RETENTION_DAYS`: retenção dos eventos de auditoria, entre 30 e 730 dias; padrão 180.

Depois de alterar qualquer variável, é obrigatório fazer um novo deployment.

## Configurações manuais na Vercel

1. Em **Firewall**, criar uma regra de rate limit para o caminho `/api/login`, por IP, inicialmente em modo Log e depois em modo Deny/429. Sugestão: cinco requisições em 10 minutos.
2. Em **Settings > Deployment Protection**, ativar Vercel Authentication para todos os deployments de Preview.
3. Restringir o acesso ao projeto e às variáveis de ambiente apenas aos administradores necessários.
4. Ativar alertas do Firewall e acompanhar respostas 401, 403, 429 e 5xx.

## Configurações manuais no Neon

1. Usar conexão com SSL e pooling fornecida pela integração.
2. Manter Preview e Production em bancos ou branches diferentes.
3. Ativar e testar restauração point-in-time conforme o plano contratado.
4. Criar um usuário de aplicação sem permissão de superusuário e conceder somente conexão, uso do schema e operações necessárias nas tabelas do AERI.
5. Fazer rotação das credenciais após desligamento de colaboradores ou suspeita de exposição.

## Operação e LGPD

- Não registrar matrículas, CPFs, senhas, tokens ou conteúdo integral de documentos em logs.
- Conceder acesso individual quando houver mais usuários; não compartilhar a conta ADM.
- Revisar a tabela `auditoria_aeri` periodicamente e definir prazo de retenção institucional.
- Testar restauração do banco, revogação de sessão e bloqueio de login antes de cada publicação relevante.
- Manter dependências atualizadas e habilitar Dependabot, Secret Scanning e proteção da branch principal no GitHub.

## Perfis de acesso

- `ADMIN`: acesso total, gestão de usuários, auditoria, exclusões, análises e manutenção das intimações.
- `OPERADOR`: análises e manutenção das intimações, sem excluir registros nem administrar usuários.
- `CONSULTA`: análises e consulta da rotina, sem criar, alterar, conferir ou excluir intimações.

Não existe cadastro público. Todo usuário é criado por um administrador e recebe uma senha temporária que deve ser substituída no primeiro acesso.
