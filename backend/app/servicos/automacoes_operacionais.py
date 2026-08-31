"""Execução retomável em Postgres, compartilhada por worker e cron autenticado.

Cada chamada processa poucos protocolos. Checkpoints não guardam textos integrais
das matrículas. O lease impede duas instâncias de gravarem o mesmo trabalho.
"""
from datetime import datetime, timedelta, timezone
from time import monotonic
from uuid import uuid4
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from backend.app.database import conectar
from backend.app.servicos.conferencia_livro import conferir_itens_tri7
from backend.app.servicos.intimacoes import situacao_conferencia
from backend.app.servicos.livro_protocolos import janelas_livro_protocolos, montar_protocolos_do_dia, hash_regras_livro_protocolos
from backend.app.servicos.tri7 import cliente_tri7

FUSO = ZoneInfo("America/Sao_Paulo")


def dentro_do_horario(config, agora):
    local = agora.astimezone(FUSO)
    return local.weekday() in config["dias_semana"] and config["hora_inicio"] <= local.hour < config["hora_fim"]


def pendencias_intimacoes(cursor, hoje=None):
    cursor.execute("SELECT id, protocolo, ultima_conferencia FROM intimacoes_aeri WHERE excluida_em IS NULL")
    pendentes = []
    for item in cursor.fetchall():
        situacao = situacao_conferencia(item, hoje)
        if situacao["classe"] in {"vermelho", "cinza"}:
            pendentes.append({"id": str(item["id"]), "protocolo": item["protocolo"], "situacao": situacao})
    return pendentes


def excecoes_do_livro(cursor, data):
    cursor.execute("""SELECT titulo_tema,natureza_tema FROM livro_protocolos_excecoes_natureza_aeri
        WHERE ativa=TRUE AND vigencia_inicio<=%s AND (vigencia_fim IS NULL OR vigencia_fim>=%s)""", (data, data))
    return frozenset((r["titulo_tema"], r["natureza_tema"]) for r in cursor.fetchall())


def resumo_livro(resultados):
    return {
        "total": len(resultados), "prenotados": sum(r["status"] == "PRENOTADO" for r in resultados),
        "registrados": sum(r["status"] == "REGISTRADO" for r in resultados),
        "semEfeito": sum(r["status"] == "SEM_EFEITO" for r in resultados),
        "indefinidos": sum(r["status"] == "INDEFINIDO" for r in resultados),
        "conferidos": sum(r["conferido"] for r in resultados),
        "falhasConsulta": sum(bool(r.get("erro")) for r in resultados),
        "comOcorrencias": sum(bool(r["ocorrencias"]) for r in resultados),
        "totalOcorrencias": sum(len(r["ocorrencias"]) for r in resultados),
    }


def executar_passo(chave, limite=2):
    agora = datetime.now(timezone.utc)
    token = uuid4()
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute("SELECT * FROM automacoes_operacionais_aeri WHERE chave=%s FOR UPDATE", (chave,))
            config = cur.fetchone()
            if not config or not config["habilitada"] or not dentro_do_horario(config, agora):
                return {"estado": "INATIVO"}
            if config["trava_ate"] and config["trava_ate"] > agora:
                return {"estado": "EM_EXECUCAO"}
            cur.execute("SELECT * FROM execucoes_operacionais_aeri WHERE chave=%s AND estado='EM_EXECUCAO' ORDER BY inicio DESC LIMIT 1", (chave,))
            trabalho = cur.fetchone()
            if not trabalho and config["proxima_execucao"] and config["proxima_execucao"] > agora:
                return {"estado": "AGUARDANDO"}
            if not trabalho:
                cur.execute("""INSERT INTO execucoes_operacionais_aeri(id,chave,data_alvo,estado)
                    VALUES (%s,%s,%s,'EM_EXECUCAO') RETURNING *""", (uuid4(), chave, agora.astimezone(FUSO).date()))
                trabalho = cur.fetchone()
            cur.execute("""UPDATE automacoes_operacionais_aeri SET trava=%s,trava_ate=%s,ultima_tentativa=%s WHERE chave=%s""",
                        (token, agora + timedelta(minutes=15), agora, chave))
        con.commit()
    inicio = monotonic()
    resultado = trabalho["resultado"] or {}
    erro = None
    estado = "EM_EXECUCAO"
    try:
        if chave == "intimacoes":
            with conectar() as con:
                with con.cursor() as cur:
                    itens = pendencias_intimacoes(cur, trabalho["data_alvo"])
            resultado = {"pendentes": itens, "total": len(itens)}
            estado = "CONCLUIDO"
        else:
            cliente = cliente_tri7()
            if "fila" not in resultado:
                janelas = janelas_livro_protocolos(trabalho["data_alvo"])
                respostas = [cliente.buscar_livro_protocolos(a, b) for a, b in janelas]
                resultado = {"fila": montar_protocolos_do_dia(respostas, trabalho["data_alvo"]),
                             "protocolos": [], "regrasHash": hash_regras_livro_protocolos(),
                             "dataEsperada": str(trabalho["data_alvo"]), "fonte": "AUTOMATICO"}
            # Não mescla silenciosamente duas versões de regras na mesma rodada.
            if resultado["regrasHash"] != hash_regras_livro_protocolos():
                raise ValueError("VERSAO_ALTERADA")
            with conectar() as con:
                with con.cursor() as cur:
                    excecoes = excecoes_do_livro(cur, trabalho["data_alvo"])
            lote = resultado["fila"][:limite]
            processados, _, _ = conferir_itens_tri7(lote, trabalho["data_alvo"], excecoes, cliente)
            resultado["protocolos"].extend(processados)
            resultado["fila"] = resultado["fila"][len(lote):]
            resultado["resumo"] = resumo_livro(resultado["protocolos"])
            if not resultado["fila"]:
                estado = "PARCIAL" if resultado["resumo"]["falhasConsulta"] else "CONCLUIDO"
    except Exception as exc:
        # Sem exception string: bibliotecas podem carregar dados/URLs sensíveis.
        erro = f"Não foi possível concluir. Tipo: {type(exc).__name__}. Reexecute a verificação."
        estado = "FALHA"
    fim = datetime.now(timezone.utc)
    concluido = estado != "EM_EXECUCAO"
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute("SELECT trava FROM automacoes_operacionais_aeri WHERE chave=%s FOR UPDATE", (chave,))
            if cur.fetchone()["trava"] != token:
                return {"estado": "LEASE_EXPIRADO"}
            total = resultado.get("resumo", {}).get("total", resultado.get("total", 0))
            ocorrencias = resultado.get("resumo", {}).get("totalOcorrencias", resultado.get("total", 0))
            cur.execute("""UPDATE execucoes_operacionais_aeri SET estado=%s,resultado=%s,
                protocolos=%s,ocorrencias=%s,erro=%s,fim=%s,duracao_ms=COALESCE(duracao_ms,0)+%s WHERE id=%s""",
                (estado, Jsonb(resultado), total, ocorrencias, erro, fim if concluido else None,
                 int((monotonic()-inicio)*1000), trabalho["id"]))
            cur.execute("""UPDATE automacoes_operacionais_aeri SET trava=NULL,trava_ate=NULL,
                proxima_execucao=%s,ultimo_sucesso=CASE WHEN %s THEN %s ELSE ultimo_sucesso END WHERE chave=%s""",
                (fim + timedelta(minutes=config["intervalo_minutos"]) if concluido else fim,
                 estado == "CONCLUIDO", fim, chave))
        con.commit()
    return {"estado": estado, "id": str(trabalho["id"]), "processados": total, "ocorrencias": ocorrencias}
