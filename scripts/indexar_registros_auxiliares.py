import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend.app.servicos.registros_auxiliares import extrair_indice_registro_auxiliar
from backend.app.servicos.tri7 import (
    ClienteTri7,
    ErroTri7,
    RegistroAuxiliarTri7NaoEncontrado,
    RegistroAuxiliarTri7SemTexto,
)


STATUS_TERMINAIS = {"OK", "NAO_ENCONTRADO", "SEM_TEXTO"}


def carregar_env_local() -> None:
    caminho = RAIZ / ".env"
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if not linha or linha.lstrip().startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


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
        espera = reservado - agora
        if espera > 0:
            time.sleep(espera)

def processar(
    numero: int,
    cliente: ClienteTri7,
    limitador: LimitadorTaxa,
    tentativas: int,
) -> dict:
    for tentativa in range(1, tentativas + 1):
        try:
            limitador.aguardar()
            resposta = cliente.buscar_texto_registro_auxiliar(numero)
            indice = extrair_indice_registro_auxiliar(numero, resposta["texto"])
            return {"status": "OK", **indice}
        except RegistroAuxiliarTri7NaoEncontrado:
            return {"status": "NAO_ENCONTRADO", "numero": numero}
        except RegistroAuxiliarTri7SemTexto:
            return {"status": "SEM_TEXTO", "numero": numero}
        except ErroTri7 as erro:
            if tentativa < tentativas:
                time.sleep(min(2 ** (tentativa - 1), 8))
                continue
            return {"status": "ERRO_API", "numero": numero, "erro": str(erro)[:200]}
        except Exception as erro:
            return {
                "status": "ERRO_PROCESSAMENTO",
                "numero": numero,
                "erro": f"{type(erro).__name__}: {erro}"[:200],
            }
    raise RuntimeError("Fluxo de tentativas inválido.")


def ler_checkpoint(caminho: Path) -> dict[int, dict]:
    resultados = {}
    if not caminho.exists():
        return resultados
    with caminho.open("r", encoding="utf-8") as arquivo:
        for linha in arquivo:
            try:
                item = json.loads(linha)
                resultados[int(item["numero"])] = item
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    return resultados


def compactar_checkpoint(caminho: Path, resultados: dict[int, dict]) -> None:
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    with temporario.open("w", encoding="utf-8", newline="\n") as arquivo:
        for numero in sorted(resultados):
            arquivo.write(json.dumps(
                resultados[numero], ensure_ascii=False, separators=(",", ":")
            ) + "\n")
    os.replace(temporario, caminho)


def gravar_resumo(caminho: Path, resultados: dict[int, dict], inicio: int, fim: int) -> Path:
    totais = {}
    situacoes = {}
    sem_emitente_devedor = []
    sem_produto = []
    sem_safra = []
    hashes_invalidos = []
    hashes = []
    garantias_ativas = []
    erros_api = []
    for numero, item in sorted(resultados.items()):
        status = item.get("status", "DESCONHECIDO")
        totais[status] = totais.get(status, 0) + 1
        if status == "ERRO_API":
            erros_api.append(numero)
        if status != "OK":
            continue
        situacao = item.get("situacao", "DESCONHECIDA")
        situacoes[situacao] = situacoes.get(situacao, 0) + 1
        if not item.get("pessoas"):
            sem_emitente_devedor.append(numero)
        if not item.get("produtos"):
            sem_produto.append(numero)
        if not item.get("safras"):
            sem_safra.append(numero)
        if len(str(item.get("texto_hash", ""))) != 64:
            hashes_invalidos.append(numero)
        hashes.append(item.get("texto_hash", ""))
        if item.get("modalidade") != "OUTROS" and item.get("situacao") == "ATIVO":
            garantias_ativas.append(item)
    lacunas_pesquisa = {
        "sem_emitente_com_produto_e_safra": [
            item["numero"] for item in garantias_ativas
            if not item.get("pessoas") and item.get("produtos") and item.get("safras")
        ],
        "sem_produto_com_emitente_e_safra": [
            item["numero"] for item in garantias_ativas
            if item.get("pessoas") and not item.get("produtos") and item.get("safras")
        ],
        "sem_safra_com_emitente_e_produto": [
            item["numero"] for item in garantias_ativas
            if item.get("pessoas") and item.get("produtos") and not item.get("safras")
        ],
    }
    completas = sum(
        bool(item.get("pessoas") and item.get("produtos") and item.get("safras"))
        for item in garantias_ativas
    )
    resumo = {
        "faixa": {"inicio": inicio, "fim": fim, "quantidade": fim - inicio + 1},
        "totais": totais,
        "situacoes": situacoes,
        "hashes": {
            "validos": len(hashes) - len(hashes_invalidos),
            "invalidos": hashes_invalidos,
            "duplicados": len(hashes) - len(set(hashes)),
        },
        "pesquisa": {
            "garantias_ativas": len(garantias_ativas),
            "garantias_ativas_com_tres_criterios": completas,
            "lacunas": lacunas_pesquisa,
        },
        "erros_api_adiados": erros_api,
        "qualidade": {
            "sem_emitente_devedor": sem_emitente_devedor,
            "sem_produto": sem_produto,
            "sem_safra": sem_safra,
            "hashes_invalidos": hashes_invalidos,
        },
        "seguranca": (
            "O texto integral não é armazenado. O arquivo contém somente hash SHA-256 "
            "e campos estruturados necessários à pesquisa."
        ),
    }
    destino = caminho.with_name("resumo.json")
    destino.write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino


def argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Indexa os textos dos Registros Auxiliares sem persistir o texto integral."
    )
    parser.add_argument("--inicio", type=int, default=1)
    parser.add_argument("--fim", type=int, default=29_538)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--rps", type=float, default=10.0)
    parser.add_argument("--tentativas", type=int, default=4)
    parser.add_argument("--refazer-erros", action="store_true")
    parser.add_argument(
        "--refazer-sem-emitente-com-produto-safra",
        action="store_true",
        help="Reprocessa garantias ativas com produto e safra, mas sem emitente/devedor.",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=RAIZ / "output" / "registros_auxiliares" / "indice-v1.jsonl",
    )
    return parser.parse_args()


def main() -> int:
    args = argumentos()
    if args.inicio < 1 or args.fim < args.inicio or not 1 <= args.workers <= 10:
        raise SystemExit("Faixa ou quantidade de workers inválida.")
    carregar_env_local()
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    resultados = ler_checkpoint(args.saida)
    refazer_lacunas = {
        numero for numero, item in resultados.items()
        if args.refazer_sem_emitente_com_produto_safra
        and item.get("status") == "OK"
        and item.get("modalidade") != "OUTROS"
        and item.get("situacao") == "ATIVO"
        and not item.get("pessoas")
        and item.get("produtos")
        and item.get("safras")
    }
    concluidos = {
        numero for numero, item in resultados.items()
        if numero not in refazer_lacunas
        and (
            item.get("status") in STATUS_TERMINAIS
            or (not args.refazer_erros and str(item.get("status", "")).startswith("ERRO"))
        )
    }
    pendentes = [numero for numero in range(args.inicio, args.fim + 1) if numero not in concluidos]
    cliente = ClienteTri7()
    limitador = LimitadorTaxa(args.rps)
    inicio_execucao = time.monotonic()
    ultimo_aviso = inicio_execucao
    processados = 0

    print(
        f"REGISTROS_AUXILIARES faixa={args.inicio}-{args.fim} pendentes={len(pendentes)} "
        f"workers={args.workers} rps={args.rps:g}",
        flush=True,
    )
    with args.saida.open("a", encoding="utf-8", newline="\n") as arquivo:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            fila = iter(pendentes)
            futuros = {}
            for _ in range(min(len(pendentes), args.workers * 3)):
                try:
                    numero = next(fila)
                except StopIteration:
                    break
                futuros[executor.submit(
                    processar, numero, cliente, limitador, args.tentativas
                )] = numero

            while futuros:
                concluidos_agora, _ = wait(futuros, return_when=FIRST_COMPLETED)
                for futuro in concluidos_agora:
                    futuros.pop(futuro)
                    item = futuro.result()
                    arquivo.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
                    arquivo.flush()
                    resultados[int(item["numero"])] = item
                    processados += 1
                    try:
                        proximo = next(fila)
                    except StopIteration:
                        proximo = None
                    if proximo is not None:
                        futuros[executor.submit(
                            processar, proximo, cliente, limitador, args.tentativas
                        )] = proximo

                agora = time.monotonic()
                if agora - ultimo_aviso >= 20 or processados == len(pendentes):
                    velocidade = processados / max(agora - inicio_execucao, 0.001)
                    restantes = len(pendentes) - processados
                    erros = sum(
                        str(item.get("status", "")).startswith("ERRO")
                        for item in resultados.values()
                    )
                    print(
                        f"PROGRESSO {processados}/{len(pendentes)} base={len(resultados)} "
                        f"erros={erros} velocidade={velocidade:.2f}/s "
                        f"eta={restantes / velocidade / 60:.1f}min",
                        flush=True,
                    )
                    ultimo_aviso = agora

    compactar_checkpoint(args.saida, resultados)
    resumo = gravar_resumo(args.saida, resultados, args.inicio, args.fim)
    erros = sum(
        str(item.get("status", "")).startswith("ERRO") for item in resultados.values()
    )
    print(f"CONCLUIDO indice={args.saida} resumo={resumo} erros={erros}", flush=True)
    return 2 if erros else 0


if __name__ == "__main__":
    raise SystemExit(main())
