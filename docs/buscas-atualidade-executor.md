# Buscas: atualidade do índice e executor

## Publicação de 29/10/2026

- A versão das regras não muda somente por diferença CRLF/LF entre Windows e Linux.
- Resultados de motor anterior recebem aviso e confiança baixa, sem criar bloqueio adicional de busca, texto ou PDF.
- Preparar o texto prioriza esses números na fila existente. A revisão automática também prioriza versões antigas.
- Permanecem os controles já existentes para divergências de identidade e de cadeia dominial.
- Cobertura informa versões antigas, falhas da última consulta e carga inicial incompleta, além das lacunas anteriores.
- PDF e texto copiado conservam os avisos; exportar PDF continua direto, sem conferência obrigatória.

Não são apagados textos, proprietários nem resultados anteriores. A atualização é gradual: publicar não significa que todas as matrículas já tenham sido reprocessadas.

## Atualizar uma instalação existente

Use um checkout limpo do commit publicado, com o executor já instalado e configurado. O procedimento é específico para Windows e para a tarefa `AERI Executor`.

```powershell
python scripts/atualizar_executor.py --destino "$env:USERPROFILE/AERI-Executor"
python scripts/atualizar_executor.py --destino "$env:USERPROFILE/AERI-Executor" --aplicar
```

A primeira execução apenas mostra a prévia. A aplicação usa somente os arquivos versionados de `backend/` e `scripts/worker_operacional.py` do HEAD. Não copia `.env` nem arquivos experimentais do checkout.

Se a tarefa estiver rodando, ela é interrompida durante a cópia e reiniciada ao final. São preservados o ambiente virtual, as credenciais, os logs e a definição da tarefa. Os arquivos substituídos recebem backup em `.tmp/atualizacoes/` da instalação. Se a validação de importações, versão ou preservação das configurações falhar, o código anterior é restaurado automaticamente.

Requisitos: dependências existentes compatíveis e permissão do usuário para controlar sua tarefa agendada. O comando não instala pacotes e não altera o banco. A execução normal do worker, depois de reiniciado, retoma suas rotinas já configuradas.

Após aplicar, confira a tarefa em execução, a versão informada pelo script e o avanço da revisão do índice. Não execute duas instalações com versões diferentes sobre a mesma fila sem coordenar sua atualização.
