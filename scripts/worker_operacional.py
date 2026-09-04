"""Executor do AERI: roda fora do navegador e fora do limite serverless.

Configuração por ambiente; --once executa um ciclo para diagnóstico.
Instale como serviço/tarefa sem janela no servidor da serventia.
"""
import argparse
import logging
import os
import time
import sys
from logging.handlers import RotatingFileHandler
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

ARQUIVO_LOG = RAIZ / ".tmp" / "executor.log"
ARQUIVO_LOG.parent.mkdir(parents=True, exist_ok=True)

# Quanto o codigo precisa estar parado para ser considerado gravado. Um git pull
# escreve varios arquivos, e reiniciar no meio pegaria a arvore pela metade.
ASSENTAMENTO = 8


def versao_do_codigo() -> float:
    """Data do arquivo mais recente entre os que este processo executa.

    Python importa cada modulo uma vez: depois de um git pull, um executor ja
    rodando segue com a versao antiga indefinidamente. Foi assim que uma
    correcao para nao abrir console ficou sem efeito com o processo dizendo
    "Running" -- e pedir reinicio manual a cada mudanca nao e operacao.
    """
    recente = 0.0
    for alvo in (RAIZ / "backend", RAIZ / "scripts" / "worker_operacional.py"):
        if alvo.is_file():
            recente = max(recente, alvo.stat().st_mtime)
            continue
        for arquivo in alvo.rglob("*.py"):
            if "__pycache__" in arquivo.parts:
                continue
            try:
                recente = max(recente, arquivo.stat().st_mtime)
            except OSError:
                pass
    return recente

from backend.app.database import fechar_pool, preparar_banco
from backend.app.servicos.automacoes_operacionais import executar_passo
from backend.app.rotas.contratos import processar_proximo_contrato


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--once",action="store_true")
    parser.add_argument("--intervalo",type=int,default=10)
    args=parser.parse_args()
    # Instalado como Tarefa Agendada o executor roda por pythonw, sem console:
    # o que fosse so para stderr se perderia, e um processo de fundo invisivel e
    # impossivel de diagnosticar. O arquivo rotaciona para nao crescer sem fim.
    formato = logging.Formatter("%(asctime)s %(message)s")
    raiz_log = logging.getLogger()
    raiz_log.setLevel(logging.INFO)
    for destino in (logging.StreamHandler(),
                    RotatingFileHandler(ARQUIVO_LOG, maxBytes=2_000_000,
                                        backupCount=3, encoding="utf-8")):
        destino.setFormatter(formato)
        raiz_log.addHandler(destino)
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
    # A data do codigo carregado: Python importa uma vez, entao um executor
    # antigo segue rodando a versao velha depois de um git pull. Sem esta linha
    # nao ha como saber, olhando o log, se ele ja pegou a correcao.
    from datetime import datetime
    carregado = datetime.fromtimestamp(Path(ocr.__file__).stat().st_mtime)
    logging.info("ocr motor=%s codigo_de=%s",
                 ocr.motor() or "NENHUM (contrato digitalizado nao sera lido)",
                 carregado.strftime("%d/%m %H:%M"))
    versao = versao_do_codigo()
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
        # Codigo novo no disco: troca este processo por um limpo, que reimporta
        # tudo. execv substitui a imagem no lugar -- nao deixa processo orfao
        # nem depende da politica de reinicio da Tarefa Agendada. Espera o
        # arquivo assentar para nao pegar um git pull pela metade, e so entre
        # ciclos, nunca no meio de um OCR.
        if versao_do_codigo() > versao and time.time() - versao_do_codigo() > ASSENTAMENTO:
            logging.info("codigo atualizado no disco: reiniciando o executor")
            fechar_pool()
            logging.shutdown()
            os.execv(sys.executable, [sys.executable, *sys.argv])
        time.sleep(max(5,min(args.intervalo,60)))
    fechar_pool()
    return 0


if __name__=="__main__": sys.exit(main() or 0)
