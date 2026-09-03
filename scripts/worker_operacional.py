"""Executor do AERI: roda fora do navegador e fora do limite serverless.

Configuração por ambiente; --once executa um ciclo para diagnóstico.
Instale como serviço/tarefa sem janela no servidor da serventia.
"""
import argparse
import logging
import os
import time
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def carregar_env(caminho: Path) -> None:
    """Le o .env da raiz, sem sobrescrever o que ja veio do sistema.

    O app roda na Vercel, onde as variaveis vem do painel; nada carregava .env.
    O worker roda numa maquina da serventia, a partir do repositorio, e sem isto
    ele morre em "DATABASE_URL ausente" antes de qualquer diagnostico. Variavel
    ja definida no ambiente vence o arquivo: quem opera a maquina manda.
    """
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        valor = valor.strip().strip('"').strip("'")
        # `vercel env pull` escreve "[SENSITIVE]" no lugar do valor quando a
        # variavel e marcada como secreta la -- ela e de escrita apenas e nao
        # volta. Aceitar esse texto e pior que nao ter nada: em vez do aviso do
        # que falta, vira erro de conexao do driver ("missing = after
        # [SENSITIVE]"), que nao diz o que fazer.
        if not valor or "[SENSITIVE]" in valor:
            continue
        os.environ.setdefault(chave.strip(), valor)


carregar_env(RAIZ / ".env")

from backend.app.database import fechar_pool, preparar_banco
from backend.app.servicos.automacoes_operacionais import executar_passo
from backend.app.rotas.contratos import processar_proximo_contrato


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--once",action="store_true")
    parser.add_argument("--intervalo",type=int,default=10)
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(message)s")
    # Os nomes aceitos aqui espelham quem le de verdade: database.py aceita
    # POSTGRES_URL ou DATABASE_URL, e cifrador() aceita a chave dos contratos ou
    # a das buscas. Exigir so um nome reprovaria maquina bem configurada.
    faltando = []
    if not (os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")):
        faltando.append("POSTGRES_URL (ou DATABASE_URL)")
    if not (os.getenv("AERI_CONTRATOS_ENCRYPTION_KEY") or os.getenv("AERI_BUSCAS_HMAC_KEY")):
        faltando.append("AERI_CONTRATOS_ENCRYPTION_KEY (ou AERI_BUSCAS_HMAC_KEY)")
    if faltando:
        logging.error("configure no ambiente ou no .env da raiz: %s", ", ".join(faltando))
        return 1
    from backend.app.contratos_nucleo import ocr
    logging.info("ocr motor=%s", ocr.motor() or "NENHUM (contrato digitalizado nao sera lido)")
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
    fechar_pool()
    return 0


if __name__=="__main__": sys.exit(main() or 0)
