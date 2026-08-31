"""Executor do AERI: roda fora do navegador e fora do limite serverless.

Configuração por ambiente; --once executa um ciclo para diagnóstico.
Instale como serviço/tarefa sem janela no servidor da serventia.
"""
import argparse
import logging
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.database import preparar_banco
from backend.app.servicos.automacoes_operacionais import executar_passo
from backend.app.rotas.contratos import processar_proximo_contrato


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--once",action="store_true")
    parser.add_argument("--intervalo",type=int,default=10)
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(message)s")
    preparar_banco()
    while True:
        try:
            for chave in ("intimacoes","livro_protocolos"):
                r=executar_passo(chave)
                logging.info("automacao=%s estado=%s",chave,r["estado"])
            r=processar_proximo_contrato()
            logging.info("contratos estado=%s",r["estado"])
        except Exception as exc:
            logging.error("ciclo_falhou tipo=%s",type(exc).__name__)
        if args.once: break
        time.sleep(max(5,min(args.intervalo,60)))


if __name__=="__main__": main()
