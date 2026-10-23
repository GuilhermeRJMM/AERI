# Sincronização contínua dos índices

## Compatibilidade

Mudança exclusivamente de backend. Não altera telas, autenticação, preços,
limites de upload, análise de ônus ou regras de cancelamento. Não modifica o
estado das intimações. A migração 062 é aditiva: não zera índices ou cursores e
não dispara carga inicial. Negativas ainda abertas podem ser promovidas a
positivas pela revalidação já existente, com histórico; pedidos finalizados
não são reabertos automaticamente.

## Execução

O executor existente passa a ter laços independentes para indexação e aquisição
de movimentações. OCR e preparação de documentos deixam de ser pré-condições
para indexar. Todos os laços compartilham o limitador da Tri7 no mesmo processo;
não instalar múltiplas cópias para acelerar. Leases do banco continuam protegendo
a concorrência com ações manuais e o cron de reserva.

A descoberta consulta o Livro a cada cinco minutos, quando ao menos uma fonte
está habilitada, com sobreposição de sete dias. Matrículas e registros auxiliares
registrados entram nas respectivas filas. Assinaturas dos resumos evitam
reenfileirar tudo a cada passagem; resumos sem mudança são revisitados em 24h.
Falha de descoberta não avança checkpoint nem impede consumir a fila existente.
Textos publicados com atraso são tentados novamente. Prioridade, novos números,
lacunas e revisão dividem o rodízio; uma fila não monopoliza o acervo.

A recuperação da busca consulta candidatos por pessoa sem exigir primeiro
produto/safra. A confirmação continua exigindo identidade compatível, situação
ativa, modalidade, produto e safra. CPF divergente da pessoa de mesmo nome não é
substituído por uma coincidência nominal. Hash por pessoa é acrescentado quando
o registro é revisitado; não requer revisão integral imediata.

Na pesquisa, candidatos incompletos/antigos são enfileirados. Até dois registros
por relatório são reconsultados imediatamente, com cache e orçamento de tempo;
o restante é atualizado em segundo plano. Falha externa não apaga resultado
pré-existente. O texto integral não é persistido. Não se introduz bloqueio geral
de negativa por índice em atualização; essa política do módulo é preservada.

## Ativação e verificação

1. Publicar o backend e executar as migrações pelo fluxo existente de
   `preparar_banco`. Não publicar um executor antigo contra esquema incompleto.
2. Atualizar o checkout **real do executor** para a mesma versão publicada.
   Alterar só a Vercel não atualiza Python que está rodando em outra máquina.
3. O executor reconhece arquivos atualizados e reinicia entre lotes, após
   concluir o trabalho em andamento. Alternativamente usar o instalador com
   `-Reiniciar`. Não encerrar um OCR à força para ativar a mudança.
4. Para funcionar sem sessão de usuário, usar um servidor sempre ligado e,
   em PowerShell elevado, `scripts/instalar_executor.ps1 -AoIniciarSistema`.
   Verificar previamente acesso de SYSTEM ao Python, dependências, .env e às
   pastas necessárias. O modo padrão continua sendo por logon e NÃO garante
   execução com o usuário desconectado. O instalador não guarda senha.
5. Conferir `.tmp/executor.log`, a tarefa agendada e a presença `:indice` no
   banco. A presença operacional não renova a capacidade do indexador; falha
   numa fonte não é encoberta pelo sucesso da outra. Não há painel novo.
6. Validar movimentação real com RA e matrícula, concorrência com OCR e
   retomada após indisponibilidade da API. A meta de poucos minutos depende
   da publicação pela Tri7, do tamanho da fila e da disponibilidade do servidor.

Não é necessária nova varredura integral: as filas fazem a atualização pontual,
e a revisão circular já existente renova os demais registros progressivamente.
Sem serviço de alterações fornecido pela Tri7, a sobreposição do Livro e o
rodízio não equivalem a uma garantia de acesso instantâneo a todo ato histórico.

## Reversão

As tabelas novas podem permanecer, sem perda de dados. Para voltar uma versão,
publicar backend e executor compatíveis juntos; manter apenas uma tarefa ativa.
Não apagar índice, filas ou histórico para reverter.

## Verificação desta implementação (23/10/2026)

- 210 testes direcionados e 37 subcasos aprovados.
- Três testes adicionais de SQL real aprovados, exclusivamente em tabelas
  temporárias com rollback, sem DDL/DML nas tabelas operacionais.
- Suíte geral: 1.252 aprovados, seis ignorados e cinco falhas também
  reproduzidas no código-base a63c78a: uma de fixture de criptografia em
  contratos, duas por diretório de relatório ausente e duas de expectativas
  antigas de bloqueio de negativa na pesquisa textual. Não foram alteradas
  regras dessas rotinas para tornar a suíte artificialmente verde.
- `git diff --check` e análise sintática do instalador PowerShell aprovados.
- Nenhuma alteração de frontend ou publicação foi realizada nesta etapa.
- A operação contínua em produção ainda exige atualização do executor real;
  os testes não equivalem a afirmar que o servidor já está executando a versão.
