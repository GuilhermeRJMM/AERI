"""Diagnóstico somente leitura. Não registra nomes, documentos ou texto."""
from backend.app.servicos.buscas import HASH_DOCUMENTOS_VERSAO
from backend.app.servicos.busca_textual import escapar_like

INDICES_ESPERADOS = {
    "idx_reg_aux_nomes_trgm", "idx_busca_proprietario_nome_trgm",
    "idx_reg_aux_produtos", "idx_reg_aux_safras", "idx_reg_aux_documentos_hash",
    "idx_busca_proprietario_documento",
}


def diagnosticar_cursor(cursor) -> dict:
    cursor.execute("SELECT extname FROM pg_extension WHERE extname='pg_trgm'")
    trgm = bool(cursor.fetchone())
    cursor.execute("""
        SELECT i.relname AS nome, ix.indisvalid AS valido, ix.indisready AS pronto,
               COALESCE(s.idx_scan, 0) AS leituras
        FROM pg_index ix JOIN pg_class i ON i.oid=ix.indexrelid
        JOIN pg_class t ON t.oid=ix.indrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace
        LEFT JOIN pg_stat_user_indexes s ON s.indexrelid=i.oid
        WHERE n.nspname=current_schema()
          AND t.relname IN ('registros_auxiliares_aeri', 'proprietarios_matriculas_busca_aeri')
        ORDER BY i.relname
    """)
    indices = [dict(r) for r in cursor.fetchall()]
    validos = {r["nome"] for r in indices if r["valido"] and r["pronto"]}
    cursor.execute("""
        SELECT COUNT(*) AS total,
          COUNT(*) FILTER (WHERE documentos_hash_versao IS DISTINCT FROM %s) AS documentos_pendentes,
          COUNT(*) FILTER (WHERE consultado_em >= NOW()-INTERVAL '24 hours') AS consultados_24h,
          MIN(consultado_em) AS consulta_mais_antiga,
          MAX(consultado_em) AS consulta_mais_recente
        FROM registros_auxiliares_aeri
    """, (HASH_DOCUMENTOS_VERSAO,))
    cobertura = dict(cursor.fetchone())
    for chave in ("consulta_mais_antiga", "consulta_mais_recente"):
        valor = cobertura.get(chave)
        cobertura[chave] = valor.isoformat() if valor else None
    cursor.execute("""
        SELECT (SELECT COUNT(*) FROM registros_auxiliares_erros_aeri) AS erros,
          (SELECT COUNT(*) FROM fila_registros_auxiliares_aeri) AS fila_total,
          (SELECT COUNT(*) FROM fila_registros_auxiliares_aeri
           WHERE proxima_tentativa_em<=NOW()) AS fila_vencida,
          (SELECT COUNT(*) FROM registros_auxiliares_varredura_aeri
           WHERE resultado='AUSENTE') AS ausencias
    """)
    pendencias = dict(cursor.fetchone())
    cursor.execute("""
        SELECT ultima_sondagem_novos_em, ultima_varredura_lacunas_em,
               ultima_sincronizacao FROM sincronizacao_registros_auxiliares_aeri WHERE id=1
    """)
    rotinas = {k: v.isoformat() if v else None for k, v in (cursor.fetchone() or {}).items()}
    return {
        "pgTrgmAtivo": trgm, "indices": indices,
        "indicesAusentesOuInvalidos": sorted(INDICES_ESPERADOS - validos),
        "documentosHashVersaoAtual": HASH_DOCUMENTOS_VERSAO,
        "cobertura": cobertura, "pendencias": pendencias, "rotinas": rotinas,
        "observacoes": [
            "Cobertura inicial não prova atualização nem correção dos resultados.",
            "Leituras de índice dependem do período desde o reset das estatísticas.",
            "Este diagnóstico não valida os vínculos entre produto e safra.",
        ],
    }


def medir_nome_cursor(cursor, nome_normalizado: str, limite: int = 100) -> dict:
    """EXPLAIN ANALYZE de SELECT fixo e limitado, com saída sem condições/PII."""
    cursor.execute("""
        EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
        SELECT numero FROM registros_auxiliares_aeri
        WHERE situacao='ATIVO' AND nomes_busca LIKE %s
        ORDER BY numero DESC LIMIT %s
    """, (f"%{escapar_like(nome_normalizado)}%", limite))
    linha = cursor.fetchone()
    dados = next(iter(linha.values()))[0]
    operacoes = []

    def resumir(plano):
        operacoes.append({k: plano[k] for k in (
            "Node Type", "Index Name", "Actual Rows", "Actual Loops",
            "Actual Total Time", "Shared Hit Blocks", "Shared Read Blocks",
        ) if k in plano})
        for filho in plano.get("Plans", []):
            resumir(filho)
    resumir(dados["Plan"])
    return {"planejamentoMs": dados.get("Planning Time"),
            "execucaoMs": dados.get("Execution Time"), "operacoes": operacoes}
