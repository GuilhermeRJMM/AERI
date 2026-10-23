"""Executor do AERI: roda fora do navegador e fora do limite serverless.

Configuração por ambiente; --once executa um ciclo para diagnóstico.
Instale como serviço/tarefa sem janela no servidor da serventia.
"""
import argparse
import logging
import os
import socket
import time
import sys
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import HTTPException

MAQUINA = socket.gethostname() or "executor"

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
        chave = chave.strip()
        # Arquivos exportados da Vercel também trazem marcadores da
        # plataforma. Importá-los no Windows bloqueia o hash remoto, pois o
        # processo passa a se identificar falsamente como função serverless.
        # Não altera marcadores reais já definidos no ambiente do processo.
        if chave == "VERCEL" or chave.startswith("VERCEL_"):
            continue
        valor = valor.strip().strip('"').strip("'")
        # `vercel env pull` escreve "[SENSITIVE]" no lugar do valor quando a
        # variavel e marcada como secreta la -- ela e de escrita apenas e nao
        # volta. Aceitar esse texto e pior que nao ter nada: em vez do aviso do
        # que falta, vira erro de conexao do driver ("missing = after
        # [SENSITIVE]"), que nao diz o que fazer.
        if not valor or "[SENSITIVE]" in valor:
            continue
        os.environ.setdefault(chave, valor)


# Lido em main(), nao ao importar: o modulo precisa poder ser importado por um
# teste sem despejar a configuracao de producao no ambiente do processo.
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

from backend.app.database import conectar, fechar_pool, preparar_banco
from backend.app.servicos.automacoes_operacionais import executar_passo
from backend.app.servicos.executor_presenca import registrar_presenca
from backend.app.rotas.contratos import processar_proximo_contrato
from backend.app.rotas.buscas import passo_automatico as passo_buscas
from backend.app.rotas.registros_auxiliares import passo_automatico as passo_registros_auxiliares
from backend.app.servicos.preparacao_intimacao import processar_preparacao_intimacao
from backend.app.servicos.buscas_movimentacoes import recuperar_movimentacoes


# A indexacao avancava por uma aba de navegador em laco: 4.605 lotes de
# matriculas e 2.559 de registros auxiliares em 30 dias, com picos as 23h, 00h
# e 01h -- alguem deixando a tela aberta de madrugada, cada lote gastando CPU
# cobrada na Vercel. O cron diario nao substituia isso: sozinho, a revisao
# pendente levaria anos. Aqui o trabalho e o mesmo, na maquina da serventia.
FONTES_INDEXACAO = (
    ("matriculas", "sincronizacao_matriculas_busca_aeri", passo_buscas),
    ("registros_auxiliares", "sincronizacao_registros_auxiliares_aeri", passo_registros_auxiliares),
)

# Falta de configuracao nao e evento novo a cada 15 segundos: sem isto, uma
# chave ausente escreveria 5.760 linhas iguais por dia e afogaria o log onde se
# procura o que de fato aconteceu. Avisa na primeira vez e quando voltar.
_indexacao_avisada = set()


def passo_indexacao():
    """Um lote de cada fonte, independente da fila de OCR/documentos.

    O sinal agregado só dispensa o cron se TODAS as fontes estiverem aptas.
    Uma fonte saudável não pode esconder a indisponibilidade da outra.
    """
    capacidades = []
    for nome, tabela, passo in FONTES_INDEXACAO:
        try:
            with conectar() as con:
                with con.cursor() as cur:
                    # Nome de tabela vem da constante acima, nunca de entrada.
                    cur.execute(f"SELECT indexacao_pausada FROM {tabela} WHERE id=1")
                    linha = cur.fetchone()
            if not linha:
                capacidades.append(False)
                continue
            if linha["indexacao_pausada"]:
                capacidades.append(True)  # preserva a pausa deliberada
                continue
            r = passo(None, "executor")
            if nome in _indexacao_avisada:
                _indexacao_avisada.discard(nome)
                logging.info("indexacao=%s voltou a funcionar", nome)
            logging.info("indexacao=%s modo=%s processados=%s", nome,
                         r.get("modo"), r.get("processados"))
            capacidades.append(not r.get("falha") and not r.get("falhas"))
        except HTTPException as exc:
            capacidades.append(exc.status_code == 409)
            # 409: alguem sincronizando pela tela, e o lease e dele. 503:
            # configuracao ausente nesta maquina. Nenhum dos dois e falha do
            # ciclo -- na proxima volta tenta de novo, de graca, porque as duas
            # barram antes de qualquer consulta a Tri7.
            if nome not in _indexacao_avisada:
                _indexacao_avisada.add(nome)
                logging.info("indexacao=%s parada: %s (so avisa de novo quando mudar)",
                             nome, str(exc.detail)[:90])
        except Exception as exc:
            capacidades.append(False)
            logging.error("indexacao=%s falhou tipo=%s", nome, type(exc).__name__)
    return bool(capacidades) and all(capacidades)


def ciclo_indexacao():
    indexa = passo_indexacao()
    registrar_presenca(f"{MAQUINA[:100]}:indice", datetime.fromtimestamp(versao_do_codigo()), indexa)


def ciclo_operacional():
    # Uma rotina com erro não impede as outras de receberem trabalho.
    for nome, passo in (
        ("intimacoes", lambda: executar_passo("intimacoes")),
        ("livro_protocolos", lambda: executar_passo("livro_protocolos")),
        ("contratos", processar_proximo_contrato),
        ("preparacao_intimacao", processar_preparacao_intimacao),
    ):
        try:
            resultado = passo()
            logging.info("automacao=%s estado=%s", nome, resultado.get("estado"))
        except Exception as exc:
            logging.error("automacao=%s falhou tipo=%s", nome, type(exc).__name__)


def executar_rotina_continua(nome, passo, parar, intervalo):
    """Laço próprio com espera interrompível e recuo nas falhas.

    Threads no mesmo processo compartilham o limitador global da Tri7 (3/s).
    Não cria outro robô com orçamento de requisições independente.
    """
    falhas = 0
    while not parar.is_set():
        try:
            passo()
            falhas = 0
        except Exception as exc:
            falhas += 1
            logging.error("rotina=%s falhou tipo=%s", nome, type(exc).__name__)
        espera = min(300, intervalo * (2 ** min(falhas, 5)))
        parar.wait(espera)


def iniciar_sincronizadores(parar, intervalo):
    rotinas = []
    for nome, passo in (("indice", ciclo_indexacao), ("movimentacoes", recuperar_movimentacoes)):
        rotina = threading.Thread(
            name=f"aeri-{nome}", target=executar_rotina_continua,
            args=(nome, passo, parar, intervalo), daemon=True,
        )
        rotina.start()
        rotinas.append(rotina)
    return rotinas


def main():
    carregar_env(RAIZ / ".env")
    carregar_env(RAIZ / ".env.buscas.local")
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
    carregado = datetime.fromtimestamp(Path(ocr.__file__).stat().st_mtime)
    logging.info("ocr motor=%s codigo_de=%s",
                 ocr.motor() or "NENHUM (contrato digitalizado nao sera lido)",
                 carregado.strftime("%d/%m %H:%M"))
    versao = versao_do_codigo()
    preparar_banco()
    intervalo = max(5, min(args.intervalo, 60))
    parar = threading.Event()
    rotinas = [] if args.once else iniciar_sincronizadores(parar, intervalo)
    reiniciar = False
    try:
        while True:
            if args.once:
                try:
                    recuperar_movimentacoes()
                except Exception as exc:
                    logging.error("rotina=movimentacoes falhou tipo=%s", type(exc).__name__)
                try:
                    ciclo_indexacao()
                except Exception as exc:
                    logging.error("rotina=indice falhou tipo=%s", type(exc).__name__)
            ciclo_operacional()
            # O trabalho operacional não renova a presença do sincronizador.
            try:
                registrar_presenca(MAQUINA, datetime.fromtimestamp(versao), False)
            except Exception as exc:
                logging.error("presenca_operacional falhou tipo=%s", type(exc).__name__)
            if args.once:
                break
            # Código novo: espera o arquivo assentar e os lotes terminarem.
            atual = versao_do_codigo()
            if atual > versao and time.time() - atual > ASSENTAMENTO:
                reiniciar = True
                break
            parar.wait(intervalo)
    finally:
        parar.set()
        # Termina o lote/checkpoint antes de trocar o código ou fechar o pool.
        for rotina in rotinas:
            rotina.join()
        fechar_pool()
    if reiniciar:
        logging.info("codigo atualizado no disco: reiniciando o executor")
        logging.shutdown()
        os.execv(sys.executable, [sys.executable, *sys.argv])
    return 0


if __name__=="__main__": sys.exit(main() or 0)
