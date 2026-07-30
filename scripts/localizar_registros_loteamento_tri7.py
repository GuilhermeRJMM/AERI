import argparse
import csv
import os
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import replace
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend.app.servicos.tri7 import (
    ClienteTri7,
    ConfiguracaoTri7,
    ErroTri7,
    MatriculaTri7NaoEncontrada,
    MatriculaTri7SemTexto,
)
from scripts.exportar_inventario_registral import (
    carregar_env_local,
    evidencias_registro_loteamento,
)


CAMPOS = [
    "numero_matricula",
    "status",
    "registro_loteamento",
    "evidencias",
    "caracteres",
    "duracao_ms",
    "erro",
]
STATUS_TERMINAIS = {"OK", "SEM_TEXTO", "NAO_ENCONTRADA"}


class LimitadorTaxa:
    def __init__(self, requisicoes_por_segundo: float):
        self.intervalo = 1.0 / max(requisicoes_por_segundo, 0.1)
        self.proximo = 0.0
        self.trava = threading.Lock()

    def aguardar(self) -> None:
        with self.trava:
            agora = time.monotonic()
            reservado = max(agora, self.proximo)
            self.proximo = reservado + self.intervalo
        if reservado > agora:
            time.sleep(reservado - agora)


def processar(numero: int, cliente: ClienteTri7, limitador: LimitadorTaxa, tentativas: int) -> dict:
    inicio = time.monotonic()
    for tentativa in range(1, tentativas + 1):
        try:
            limitador.aguardar()
            texto = cliente.buscar_texto_matricula(numero)["texto"]
            evidencias = evidencias_registro_loteamento(texto)
            return {
                "numero_matricula": numero,
                "status": "OK",
                "registro_loteamento": "SIM" if evidencias else "NÃO",
                "evidencias": ";".join(evidencias) if evidencias else "NÃO CONSTA",
                "caracteres": len(texto),
                "duracao_ms": round((time.monotonic() - inicio) * 1000),
                "erro": "NÃO CONSTA",
            }
        except MatriculaTri7SemTexto:
            status = "SEM_TEXTO"
            erro = "NÃO CONSTA"
            break
        except MatriculaTri7NaoEncontrada:
            status = "NAO_ENCONTRADA"
            erro = "NÃO CONSTA"
            break
        except ErroTri7 as exc:
            if tentativa < tentativas:
                time.sleep(min(2 ** (tentativa - 1), 30))
                continue
            status = "ERRO_API"
            erro = str(exc)
            break
        except Exception as exc:
            status = "ERRO_PROCESSAMENTO"
            erro = f"{type(exc).__name__}: {exc}"
            break
    return {
        "numero_matricula": numero,
        "status": status,
        "registro_loteamento": "NÃO CONSTA",
        "evidencias": "NÃO CONSTA",
        "caracteres": "NÃO CONSTA",
        "duracao_ms": round((time.monotonic() - inicio) * 1000),
        "erro": erro,
    }


def ler(caminho: Path) -> dict[int, dict]:
    if not caminho.exists():
        return {}
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        return {int(linha["numero_matricula"]): linha for linha in csv.DictReader(arquivo)}


def gravar(caminho: Path, resultados: dict[int, dict], inicio: int, fim: int) -> None:
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    with temporario.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=CAMPOS)
        escritor.writeheader()
        for numero in range(inicio, fim + 1):
            if numero in resultados:
                escritor.writerow({campo: resultados[numero].get(campo, "NÃO CONSTA") for campo in CAMPOS})
    os.replace(temporario, caminho)


def argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Localiza registros do próprio loteamento na base Tri7.")
    parser.add_argument("--inicio", type=int, default=1)
    parser.add_argument("--fim", type=int, default=39_827)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--rps", type=float, default=6.0)
    parser.add_argument("--tentativas", type=int, default=6)
    parser.add_argument(
        "--timeout",
        type=int,
        help="Timeout excepcional da auditoria em segundos (3 a 300); não altera o AERI.",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=RAIZ / "output" / "relatorios" / "registros_loteamento-v1.csv",
    )
    return parser.parse_args()


def main() -> int:
    args = argumentos()
    if args.inicio < 1 or args.fim < args.inicio or not 1 <= args.workers <= 20:
        raise SystemExit("Faixa ou workers inválidos.")
    if args.timeout is not None and not 3 <= args.timeout <= 300:
        raise SystemExit("O timeout excepcional deve estar entre 3 e 300 segundos.")
    carregar_env_local()
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    resultados = ler(args.saida)
    concluidos = {
        numero for numero, item in resultados.items()
        if item.get("status") in STATUS_TERMINAIS
    }
    pendentes = [numero for numero in range(args.inicio, args.fim + 1) if numero not in concluidos]
    configuracao = ConfiguracaoTri7.do_ambiente()
    if args.timeout is not None:
        configuracao = replace(configuracao, timeout=args.timeout)
    cliente = ClienteTri7(configuracao)
    limitador = LimitadorTaxa(args.rps)
    inicio_execucao = time.monotonic()
    ultimo_aviso = inicio_execucao
    processados = 0
    print(
        f"Iniciando localização {args.inicio}-{args.fim}: pendentes={len(pendentes)}, "
        f"workers={args.workers}, limite={args.rps:g} req/s",
        flush=True,
    )
    with args.saida.open("a", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=CAMPOS)
        if args.saida.stat().st_size == 0:
            escritor.writeheader()
        fila = iter(pendentes)
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futuros = {}
            for _ in range(min(len(pendentes), args.workers * 3)):
                try:
                    numero = next(fila)
                except StopIteration:
                    break
                futuros[executor.submit(processar, numero, cliente, limitador, args.tentativas)] = numero
            while futuros:
                concluidos_agora, _ = wait(futuros, return_when=FIRST_COMPLETED)
                for futuro in concluidos_agora:
                    futuros.pop(futuro)
                    item = futuro.result()
                    escritor.writerow(item)
                    arquivo.flush()
                    resultados[int(item["numero_matricula"])] = item
                    processados += 1
                    try:
                        proximo = next(fila)
                    except StopIteration:
                        proximo = None
                    if proximo is not None:
                        futuros[executor.submit(processar, proximo, cliente, limitador, args.tentativas)] = proximo
                agora = time.monotonic()
                if agora - ultimo_aviso >= 20 or processados == len(pendentes):
                    velocidade = processados / max(agora - inicio_execucao, 0.001)
                    candidatos = sum(item.get("registro_loteamento") == "SIM" for item in resultados.values())
                    erros = sum(str(item.get("status", "")).startswith("ERRO") for item in resultados.values())
                    print(
                        f"PROGRESSO {processados}/{len(pendentes)}; base={len(resultados)}; "
                        f"candidatos={candidatos}; erros={erros}; velocidade={velocidade:.2f}/s",
                        flush=True,
                    )
                    ultimo_aviso = agora
    gravar(args.saida, resultados, args.inicio, args.fim)
    erros = sum(str(item.get("status", "")).startswith("ERRO") for item in resultados.values())
    candidatos = sorted(
        numero for numero, item in resultados.items()
        if item.get("registro_loteamento") == "SIM"
    )
    print(f"CONCLUÍDO candidatos={candidatos} erros={erros} saída={args.saida}", flush=True)
    return 2 if erros else 0


if __name__ == "__main__":
    raise SystemExit(main())
