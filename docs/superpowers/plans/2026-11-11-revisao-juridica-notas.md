# Revisão jurídica das 72 pendências — plano de execução

**Objetivo:** corrigir referências incompletas, trechos revogados e comandos incompatíveis com suas próprias fontes, preservando os identificadores das pendências e as notas já emitidas.

**Escopo:** catálogo, dispositivos, resumos correspondentes, rastreabilidade das fontes e testes. Não alterar módulos de buscas, assinaturas, intimações ou banco de produção. Não publicar sem ordem expressa.

**Arquitetura:** manter o catálogo versionado e a geração determinística; revisar a associação de cada pendência à norma e aos trechos pertinentes. A revisão técnica não equivale à aprovação pelo registrador: manter `revisado` como falso.

## Etapas

- [x] Conferir individualmente as 72 entradas e registrar o problema e a solução.
- [x] Obter o CNPFE diretamente do TJGO, o CNN diretamente do CNJ e legislação federal em portais oficiais; excluir textos riscados/revogados da extração.
- [x] Criar testes de regressão antes da correção: ITCD parcelado, exceções de certidões, anuência, prazos úteis, ônus não impeditivos, transcrição e especialidade.
- [x] Corrigir o catálogo e os recortes legais, incluindo contexto hierárquico dos incisos, alíneas e itens; sincronizar os resumos alterados.
- [x] Conferir integralidade de todas as referências, ausência de partes revogadas, cobertura de 72/72 e rastreabilidade das fontes.
- [x] Gerar notas sintéticas, executar testes e renderizar amostras para inspeção.
- [ ] Entregar alterações locais e relatório, distinguindo verificações automáticas de validação jurídica humana.
