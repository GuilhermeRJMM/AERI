"""Acompanhamento RTD independente das filas de OCR, custas e indexação."""
import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

RAIZ=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(RAIZ))


def main():
    from scripts.sincronizar_rtd import carregar_ambiente
    carregar_ambiente()
    from backend.app.database import conectar,fechar_pool
    from backend.app.servicos.rtd_sincronizacao import executar_passo_rtd
    from backend.app.servicos.rtd_cliente import ClienteRTD
    (RAIZ/'.tmp').mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s',handlers=[
        RotatingFileHandler(RAIZ/'.tmp/rtd.log',maxBytes=1_000_000,backupCount=2,encoding='utf8')])
    try:
        ClienteRTD()  # Configuração obrigatória para iniciar a tarefa.
        logging.info('RTD iniciado; consulta incremental a cada 5 minutos; fila retomável.')
        while True:
            try:
                r=executar_passo_rtd()
                if r['estado'] not in ('AGUARDANDO','EM_EXECUCAO'):
                    logging.info('estado=%s processados=%s vinculados=%s',r['estado'],r.get('processados',0),r.get('vinculados',0))
            except Exception as exc:
                logging.error('falha tipo=%s; nova tentativa em 15 segundos',type(exc).__name__)
                try:
                    with conectar() as con, con.cursor() as cur:
                        cur.execute("UPDATE rtd_sincronizacao_aeri SET erro='RTD_EXECUTOR: falha local; confira o executor.',ultima_consulta=NOW() WHERE id=1")
                        con.commit()
                except Exception:
                    pass
            time.sleep(15)
    finally:
        fechar_pool()


if __name__=='__main__': main()
