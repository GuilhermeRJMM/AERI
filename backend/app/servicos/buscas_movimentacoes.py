"""Sinais do Livro localizam matrículas; a titularidade vem sempre do texto."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from backend.app.database import conectar
from backend.app.servicos.buscas_mencoes import enfileirar_matriculas
from backend.app.servicos.livro_protocolos import janelas_livro_protocolos, montar_protocolos_do_dia, registros_alterados_no_protocolo
from backend.app.servicos.tri7 import cliente_tri7


def _descobrir_protocolos(cliente):
    # Uma passagem por hora recupera hoje e os últimos sete dias, inclusive
    # dias não úteis. A cobertura da API segue limitada à janela disponível.
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute('''UPDATE sincronizacao_matriculas_busca_aeri
                SET sinais_trava_ate=NOW()+INTERVAL '10 minutes'
                WHERE id=1 AND NOT indexacao_pausada
                  AND (sinais_trava_ate IS NULL OR sinais_trava_ate<NOW())
                  AND (sinais_verificados_em IS NULL OR sinais_verificados_em<NOW()-INTERVAL '1 hour')
                RETURNING id''')
            if not cur.fetchone():
                return 0
        con.commit()
    hoje=datetime.now(ZoneInfo('America/Sao_Paulo')).date()
    # O checkpoint só avança se toda a leitura for bem-sucedida.
    respostas=[cliente.buscar_livro_protocolos(a,b) for a,b in janelas_livro_protocolos(hoje)]
    protocolos={}
    for atraso in range(8):
        for p in montar_protocolos_do_dia(respostas,hoje-timedelta(days=atraso)):
            if p['status']=='REGISTRADO':
                protocolos[p['numero']]=p
    with conectar() as con:
        with con.cursor() as cur:
            for numero in protocolos:
                numero=int(str(numero).replace('.',''))
                cur.execute('INSERT INTO fila_protocolos_busca_aeri(numero) VALUES (%s) ON CONFLICT DO NOTHING',(numero,))
            cur.execute('UPDATE sincronizacao_matriculas_busca_aeri SET sinais_verificados_em=NOW(),sinais_trava_ate=NULL WHERE id=1')
        con.commit()
    return len(protocolos)


def recuperar_movimentacoes():
    cliente=cliente_tri7()
    _descobrir_protocolos(cliente)
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
                        numeros={n for tipo,n in registros_alterados_no_protocolo(dados) if tipo=='M'}
                        enfileirar_matriculas(cur,numeros,'MOVIMENTACAO_RECENTE')
                        cur.execute('DELETE FROM fila_protocolos_busca_aeri WHERE numero=%s',(numero,))
                        quantidade+=len(numeros)
                except Exception:
                    cur.execute('''UPDATE fila_protocolos_busca_aeri SET tentativas=tentativas+1,
                        proxima_tentativa_em=NOW()+make_interval(mins=>LEAST(360,15*(1<<LEAST(tentativas,5))))
                        WHERE numero=%s''',(numero,))
        con.commit()
    return quantidade
