# Importação conservadora do cadastro Sync

## Execução em 23/10/2026

- Fonte SQLite fornecida pelo responsável, aberta exclusivamente com `mode=ro` e `query_only`.
- Foram lidos somente `id`, `nome`, `login` e `ativo`: nenhuma senha, contato, foto ou permissão Sync foi consultada pelo importador.
- Fonte: 67 cadastros. AERI anterior: 27 contas. Criadas: 59 contas. AERI após verificação independente: 86 contas.
- Lote auditado: `06c9486f-eb8b-4c89-af05-474b1be6047d`.
- As 59 contas receberam perfil `USUARIO`, todas as flags legadas falsas e negações individuais para o catálogo de permissões existente. Nenhum cargo ou acesso foi transferido do Sync.
- Estado ativo preservado da fonte. Credenciais locais são segredos aleatórios descartados, armazenados apenas pelo hash normal do AERI: não há senha inicial compartilhada, nem reutilização da senha Sync. Para login local, usar a redefinição administrativa já existente.
- Nomes, logins, estado e perfis das contas anteriores foram comparados antes do commit. A importação não atualiza contas ou permissões anteriores e não revoga suas sessões.
- Toda criação registra auditoria e proveniência na tabela `importacoes_usuarios_sync_aeri` (migração 064, aplicada dentro da transação da importação).
- Reexecução de diagnóstico confirmou 59 já importados, zero novos, oito pendentes. Não foi publicada uma nova versão do site nesta operação.

## Pendências sem divulgar nomes

| ID no Sync | Revisão necessária |
| --- | --- |
| 1 | Login já existente no AERI, com nome diferente |
| 4 | Login fora do formato aceito |
| 5, 177, 196 | Nome coincide com conta AERI de outro login; não presumir identidade |
| 10, 2432 | Login repetido e nome repetido na fonte |
| 15 | Nome repetido na fonte |

Os oito não foram unidos, renomeados ou importados automaticamente. Exigem reconciliação administrativa. Mesmo nome não é prova suficiente para vínculo de autenticação.

## Uso do importador

`scripts/importar_usuarios_sync.py --sqlite CAMINHO` apresenta apenas contagens e IDs pendentes. A escrita exige `--aplicar` e conexão Postgres configurada no ambiente. O script não carrega arquivos de credenciais automaticamente nem exibe dados de acesso.

A escrita usa uma transação, lock de cadastro, comparação das contas anteriores e verificação de privilégio mínimo antes do commit. A migração impede duplicar o mesmo ID de origem; conflitos cancelam a transação. O script nunca altera o arquivo SQLite.

## Separação do HUB

O ID inteiro do Sync não é o UUID `sub` do HUB. A tabela de proveniência NÃO concede SSO e não deve ser tratada como `vinculos_sso_hub_aeri`. A chave pública recebida e seu `kid` foram conferidos, mas ainda não configurados em produção. A ativação exige os UUIDs reais das contas HUB, vínculos administrados e teste conjunto do receptor novo. As permissões seguem exclusivamente sob controle do AERI.
