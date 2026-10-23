# Instalação local — C-59 — 23/10/2026

- Instalação permanente: `C:\Users\Guilherme.medeiros\AERI-Executor`.
- Python isolado: `.venv\Scripts\pythonw.exe`, dependências de `requirements.txt`.
- Tarefa: **AERI Executor**, início no login do usuário, sem janela, intervalo
  de 15 segundos, recuperação automática e sem limite de duração.
- Esta sessão não tinha privilégio administrativo. Não foi instalada tarefa
  SYSTEM/no boot; encerrar a sessão do Windows interrompe o executor.
- Banco, autenticação Tri7, hash remoto, OCR do Windows e pastas do drive T:
  verificados. Migração aditiva 062 aplicada pelo fluxo normal de inicialização.
- Primeiro lote de matrículas concluído: 28 processadas, 28 encontradas, zero
  falhas. Lote de retentativas de auxiliares concluído: 20 processados; alguns
  registros antigos retornam HTTP 500 na Tri7 e permanecem para retentativa.
  A consulta direta de controle ao RA 29.667 recebeu texto normalmente.
- Módulo `ferramentas` instalado para a preparação de intimações. Após a
  correção da cópia de instalação, o laço retornou `SEM_TRABALHO`, sem erro.
- Heartbeats `C-59` e `C-59:indice` verificados no banco. O segundo não reporta
  capacidade plena enquanto houver falhas no lote; não mascarar com presença.
- C-49: último heartbeat encontrado em 22/10/2026, sem executor recente no
  momento da ativação. Acesso administrativo remoto não disponível. A tarefa
  antiga NÃO foi desativada; desativar na própria C-49 antes de reutilizá-la.
- A política de suspensão em energia AC já estava em zero (não suspender).

## Operação

`Get-ScheduledTask -TaskName 'AERI Executor'` verifica a tarefa.

O log rotativo fica em `.tmp\executor.log`. Não exibir nem versionar `.env` ou
`.env.buscas.local`; a pasta foi protegida para o usuário, SYSTEM e administradores.

A configuração do worker ignora marcadores `VERCEL` vindos de arquivo exportado,
sem remover marcadores reais do ambiente de uma função serverless.

Para atualizar, copiar a versão validada e compatível do backend, scripts e
ferramentas para esta instalação, preservando os arquivos privados e a `.venv`.
O executor detecta atualização de Python e reinicia após concluir os lotes.
O checkout usado para preparar esta instalação tem mudanças ainda sem commit;
a publicação do backend web é uma etapa separada, não executada nesta instalação.

Para rodar sem login, usar o instalador com `-AoIniciarSistema` em uma sessão
administrativa, verificando antes os acessos de SYSTEM às pastas da rede. O drive
T: desta sessão não estará automaticamente disponível para SYSTEM.
