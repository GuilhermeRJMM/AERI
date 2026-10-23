"""Sinais do Livro alimentam ambas as buscas, sem depender da conferência."""
import hashlib
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from backend.app.database import conectar
from backend.app.servicos.buscas_mencoes import enfileirar_matriculas
from backend.app.servicos.fila_auxiliares import enfileirar_auxiliares
from backend.app.servicos.livro_protocolos import janelas_livro_protocolos, montar_protocolos_do_dia, registros_alterados_no_protocolo
from backend.app.servicos.tri7 import cliente_tri7


def _descobrir_protocolos(cliente):
    # Uma passagem a cada cinco minutos, com sobreposição de sete dias.
    # O restante do acervo continua protegido pelo rodízio de revisão.
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute('''UPDATE sincronizacao_matriculas_busca_aeri
                SET sinais_trava_ate=NOW()+INTERVAL '10 minutes'
                WHERE id=1 AND (NOT indexacao_pausada OR EXISTS (
                    SELECT 1 FROM sincronizacao_registros_auxiliares_aeri
                    WHERE id=1 AND NOT indexacao_pausada))
                  AND (sinais_trava_ate IS NULL OR sinais_trava_ate<NOW())
                  AND (sinais_verificados_em IS NULL OR sinais_verificados_em<NOW()-INTERVAL '5 minutes')
                RETURNING sinais_trava_ate''')
            lease = cur.fetchone()
            if not lease:
                return 0
        con.commit()
    trava_ate = lease['sinais_trava_ate']
    try:
        hoje=datetime.now(ZoneInfo('America/Sao_Paulo')).date()
        respostas=[cliente.buscar_livro_protocolos(a,b) for a,b in janelas_livro_protocolos(hoje)]
        protocolos={}
        for atraso in range(8):
            for p in montar_protocolos_do_dia(respostas,hoje-timedelta(days=atraso)):
                if p['status']=='REGISTRADO':
                    protocolos[p['numero']]=p
        with conectar() as con:
            with con.cursor() as cur:
                for bruto, resumo in protocolos.items():
                    numero=int(str(bruto).replace('.',''))
                    assinatura=hashlib.sha256(json.dumps(
                        resumo, sort_keys=True, default=str, ensure_ascii=False
                    ).encode('utf-8')).hexdigest()
                    # Sem mudança no resumo, verifica de novo uma vez por dia:
                    # o texto pode ter sido corrigido sem mudar a linha do Livro.
                    cur.execute('''INSERT INTO sinais_protocolos_indice_aeri(numero, assinatura)
                        VALUES (%s,%s) ON CONFLICT(numero) DO UPDATE SET
                        assinatura=EXCLUDED.assinatura, verificado_em=NOW()
                        WHERE sinais_protocolos_indice_aeri.assinatura<>EXCLUDED.assinatura
                           OR sinais_protocolos_indice_aeri.verificado_em<NOW()-INTERVAL '1 day'
                        RETURNING numero''', (numero, assinatura))
                    if cur.fetchone():
                        cur.execute('''INSERT INTO fila_protocolos_busca_aeri(numero)
                            VALUES (%s) ON CONFLICT(numero) DO UPDATE SET
                            solicitada_em=clock_timestamp(), proxima_tentativa_em=NOW()''', (numero,))
                cur.execute('''UPDATE sincronizacao_matriculas_busca_aeri
                    SET sinais_verificados_em=NOW(), sinais_trava_ate=NULL
                    WHERE id=1 AND sinais_trava_ate=%s''', (trava_ate,))
            con.commit()
        return len(protocolos)
    except Exception:
        # Libera só o próprio lease, sem avançar o checkpoint de sucesso.
        with conectar() as con:
            with con.cursor() as cur:
                cur.execute('''UPDATE sincronizacao_matriculas_busca_aeri
                    SET sinais_trava_ate=NULL WHERE id=1 AND sinais_trava_ate=%s''', (trava_ate,))
            con.commit()
        raise


def recuperar_movimentacoes():
    cliente=cliente_tri7()
    try:
        _descobrir_protocolos(cliente)
    except Exception as erro:
        # Falha ao descobrir novidades não impede consumir a fila já salva.
        logging.getLogger(__name__).warning('descobrir_movimentacoes tipo=%s', type(erro).__name__)
    quantidade=0
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute('''SELECT numero FROM fila_protocolos_busca_aeri
                WHERE proxima_tentativa_em<=NOW() ORDER BY proxima_tentativa_em,numero
                LIMIT 2 FOR UPDATE SKIP LOCKED''')
            for item in cur.fetchall():
                numero=item['numero']
                try:
                    with con.transaction():
                        dados=cliente.buscar_protocolo_completo(numero)
                        referencias=registros_alterados_no_protocolo(dados)
                        numeros={n for tipo,n in referencias if tipo=='M'}
                        auxiliares={n for tipo,n in referencias if tipo=='RA'}
                        enfileirar_matriculas(cur,numeros,'MOVIMENTACAO_RECENTE')
                        enfileirar_auxiliares(cur,auxiliares,'MOVIMENTACAO_RECENTE')
                        cur.execute('''DELETE FROM fila_protocolos_busca_aeri
                            WHERE numero=%s AND solicitada_em<=transaction_timestamp()''',(numero,))
                        quantidade+=len(numeros)+len(auxiliares)
                except Exception:
                    cur.execute('''UPDATE fila_protocolos_busca_aeri SET tentativas=tentativas+1,
                        proxima_tentativa_em=NOW()+make_interval(mins=>LEAST(360,15*(1<<LEAST(tentativas,5))))
                        WHERE numero=%s''',(numero,))
        con.commit()
    return quantidade
