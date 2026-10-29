# Publicação mínima: identidade e diagnóstico

Incluído:
- Registro Auxiliar: CPF/CNPJ completo é pesquisado somente por hash exato;
  documentos com tamanho inválido não são truncados.
- Nomes empresariais com números não viram documentos.
- Buscas por nome escapam caracteres curingas digitados.
- Informar Custas: sobrenomes faltando ou acrescentados não confirmam identidade.
- Diagnóstico somente leitura, restrito a ADMIN/SUBSTITUTO, compatível com o
  banco atual. GET /api/registros-auxiliares/diagnostico.
- Medição opcional: python scripts/diagnosticar_buscas.py --medir-nome.
  O nome é solicitado sem eco e não aparece na saída ou linha de comando.

Excluído:
- Migração 066, novos campos e vínculos produto/safra.
- Alteração do parser, versão de extração ou reprocessamento do acervo.
- Mudanças no pool de conexões, FTS ou configuração do Neon.
- Alterações visuais ou nos fluxos de Intimações.

O diagnóstico não comprova a correção de produto/safra. Apenas inventaria
índices válidos, consultas recentes, erros e filas existentes. A medição de
EXPLAIN ANALYZE usa SELECT limitado, transação read-only e timeout local;
Filter e Index Cond são removidos da saída para não expor termos pessoais.
