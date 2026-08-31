# Voltar à versão anterior à reestruturação

Ponto de retorno de 31/08/2026:

- Tag Git: `backup/antes-reestruturacao-20260831`.
- Commit anterior: `7c615b5cc1c2c161d06fe8dcde3d4649f3fe390a`.
- Deploy anterior: `dpl_6jVztKVcPhXUyaJoTMtmjUTJvoGe`.
- URL do deploy: https://aeri-2293i2n25-thaguienterprise.vercel.app
- Cópia local do código anterior: `tmp/backup-antes-reestruturacao-20260831.zip` (não contém variáveis de ambiente).

## Retorno rápido

Basta solicitar: **“Volte ao backup anterior à reestruturação dos setores”**.

Procedimento técnico:

1. Desabilitar as agendas em Administração → Integrações e agendamentos e parar o executor operacional, caso esteja instalado. Não interromper executores de indexação não relacionados.
2. Na Vercel, selecionar o deploy anterior acima e usar **Instant Rollback**. Alternativa com a CLI autenticada no projeto AERI:

   `vercel rollback aeri-2293i2n25-thaguienterprise.vercel.app --scope thaguienterprise`

3. Verificar login, permissões e módulos. O retorno do deploy é imediato, mas **não** altera o GitHub: preparar um commit de reversão dos commits desta reestruturação para o próximo deploy não reintroduzir a mudança. Não usar `reset --hard` nem forçar o push.
4. Preservar os dados criados depois da publicação. Não restaurar o banco inteiro sobre a produção e não apagar tabelas novas.

## Permissões e banco

A migração 041 salva, antes de alterar acessos, a fotografia `antes_setores_20260831` em `backups_acessos_aeri`: catálogo, permissões de perfis, concessões individuais e cargos. Não copia senhas nem sessões. A fotografia não é substituída se a migração for executada novamente.

As migrações 041/042 são aditivas. A fotografia é dos **acessos afetados**, não um backup integral do banco. Intimações, certidões, índices e demais dados existentes não são apagados pela reestruturação.

Versões antigas não aplicam as novas negações por setor da mesma forma. Na reversão, comparar a fotografia com os acessos atuais e preservar alterações administrativas legítimas posteriores. Se houve concessões/revogações após a publicação, o responsável deve decidir quais manter. Não restaurar permissões indiscriminadamente.

Históricos de contratos continuam cifrados no banco; não excluir nem trocar a chave utilizada. A versão antiga apenas não apresenta esse módulo.

## Executor

Publicar no GitHub/Vercel não instala automaticamente um serviço Windows. O executor e o OCR exigem ambiente separado, com as mesmas credenciais e chave do servidor web. Agendas nascem desativadas. O estado real da ativação deve ser conferido em `REESTRUTURACAO_SETORES.md`, sem presumir que publicar ligou as rotinas.
