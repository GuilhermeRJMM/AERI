import argparse
import csv
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend.app.parser import separar_atos
from backend.app.servicos.analise_matricula import analisar_matricula
from backend.app.servicos.tri7 import (
    ClienteTri7,
    ErroTri7,
    MatriculaTri7NaoEncontrada,
    MatriculaTri7SemTexto,
)


CAMPOS = [
    "numero_matricula",
    "status",
    "caracteres",
    "blocos",
    "atos_classificados",
    "proprietarios",
    "matricula_identificada",
    "marcadores_genericos",
    "resultado",
    "duracao_ms",
    "erro",
]
STATUS_TERMINAIS = {"OK", "NAO_ENCONTRADA", "SEM_TEXTO"}
REFERENCIAS_INTERNAS_REVISADAS = {2374, 2598, 5103, 19670, 29774}
PADRAO_MARCADOR = re.compile(
    r"(?im)(?:^|\n)[ \t\-–—]*(?:R|AV)\s*[.\-]\s*\d+(?=[\s.\-–—:,]|$)"
)


def carregar_env_local() -> None:
    caminho = RAIZ / ".env"
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if not linha or linha.lstrip().startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor)


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


def identificou_matricula(resultado: dict) -> bool:
    imovel = resultado.get("imovel") or {}
    return any(
        item.get("rotulo") == "Matrícula" and str(item.get("valor", "")).strip()
        for item in imovel.get("identificacao", [])
    )


def linha_base(numero: int, inicio: float) -> dict:
    return {
        "numero_matricula": numero,
        "status": "",
        "caracteres": "",
        "blocos": "",
        "atos_classificados": "",
        "proprietarios": "",
        "matricula_identificada": "",
        "marcadores_genericos": "",
        "resultado": "",
        "duracao_ms": round((time.monotonic() - inicio) * 1000),
        "erro": "",
    }


def processar_numero(numero: int, cliente: ClienteTri7, limitador: LimitadorTaxa, tentativas: int) -> dict:
    inicio = time.monotonic()
    for tentativa in range(1, tentativas + 1):
        try:
            limitador.aguardar()
            matricula = cliente.buscar_texto_matricula(numero)
            texto = matricula["texto"]
            blocos = separar_atos(texto)
            resultado = analisar_matricula(texto)
            linha = linha_base(numero, inicio)
            linha.update(
                status="OK",
                caracteres=len(texto),
                blocos=len(blocos),
                atos_classificados=len(resultado["atos"]),
                proprietarios=len(resultado["proprietarios_atuais"]),
                matricula_identificada=identificou_matricula(resultado),
                marcadores_genericos=len(PADRAO_MARCADOR.findall(texto)),
                resultado=resultado["resultado"],
            )
            return linha
        except MatriculaTri7NaoEncontrada:
            linha = linha_base(numero, inicio)
            linha["status"] = "NAO_ENCONTRADA"
            return linha
        except MatriculaTri7SemTexto:
            linha = linha_base(numero, inicio)
            linha["status"] = "SEM_TEXTO"
            return linha
        except ErroTri7 as erro:
            if tentativa < tentativas:
                time.sleep(min(2 ** (tentativa - 1), 8))
                continue
            linha = linha_base(numero, inicio)
            linha.update(status="ERRO_API", erro=str(erro)[:240])
            return linha
        except Exception as erro:
            linha = linha_base(numero, inicio)
            linha.update(status="ERRO_PROCESSAMENTO", erro=f"{type(erro).__name__}: {erro}"[:240])
            return linha
    raise RuntimeError("Fluxo de tentativas inválido.")


def ler_ultimo_resultado(caminho: Path) -> dict[int, dict]:
    if not caminho.exists():
        return {}
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        return {int(linha["numero_matricula"]): linha for linha in csv.DictReader(arquivo)}


def gravar_resumo(caminho_csv: Path, resultados: dict[int, dict], inicio: int, fim: int) -> Path:
    totais: dict[str, int] = {}
    alertas_regex = []
    for numero, linha in sorted(resultados.items()):
        status = linha["status"]
        totais[status] = totais.get(status, 0) + 1
        if status == "OK" and int(linha.get("marcadores_genericos") or 0) > int(linha.get("blocos") or 0):
            alertas_regex.append(numero)
    resumo = {
        "faixa": {"inicio": inicio, "fim": fim, "quantidade": fim - inicio + 1},
        "totais": totais,
        "alertas_regex": [numero for numero in alertas_regex if numero not in REFERENCIAS_INTERNAS_REVISADAS],
        "referencias_internas_revisadas": [
            numero for numero in alertas_regex if numero in REFERENCIAS_INTERNAS_REVISADAS
        ],
        "observacao": "O relatório não armazena o texto das matrículas nem dados pessoais.",
    }
    caminho = caminho_csv.with_name(f"{caminho_csv.stem}-resumo.json")
    caminho.write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    return caminho


def argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Consulta e processa uma faixa de matrículas da Tri7.")
    parser.add_argument("--inicio", type=int, default=1)
    parser.add_argument("--fim", type=int, default=39_767)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--rps", type=float, default=16.0)
    parser.add_argument("--tentativas", type=int, default=4)
    parser.add_argument("--refazer", default="", help="Números separados por vírgula que devem ser reprocessados.")
    parser.add_argument("--saida", type=Path, default=RAIZ / "output" / "relatorios" / "validacao_tri7_1_39767.csv")
    return parser.parse_args()


def main() -> int:
    args = argumentos()
    if args.inicio < 1 or args.fim < args.inicio or args.workers < 1 or args.workers > 20:
        raise SystemExit("Faixa ou quantidade de workers inválida.")
    carregar_env_local()
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    anteriores = ler_ultimo_resultado(args.saida)
    refazer = {int(item) for item in args.refazer.split(",") if item.strip()}
    concluidos = {
        numero for numero, linha in anteriores.items()
        if linha["status"] in STATUS_TERMINAIS and numero not in refazer
    }
    pendentes = [numero for numero in range(args.inicio, args.fim + 1) if numero not in concluidos]
    cliente = ClienteTri7()
    limitador = LimitadorTaxa(args.rps)
    novo_arquivo = not args.saida.exists() or args.saida.stat().st_size == 0
    inicio_execucao = time.monotonic()
    ultimo_aviso = inicio_execucao
    processados = 0

    print(
        f"Iniciando faixa {args.inicio}-{args.fim}: pendentes={len(pendentes)}, "
        f"workers={args.workers}, limite={args.rps:g} req/s",
        flush=True,
    )
    with args.saida.open("a", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=CAMPOS)
        if novo_arquivo:
            escritor.writeheader()
            arquivo.flush()
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futuros = {
                executor.submit(processar_numero, numero, cliente, limitador, args.tentativas): numero
                for numero in pendentes
            }
            for futuro in as_completed(futuros):
                linha = futuro.result()
                escritor.writerow(linha)
                arquivo.flush()
                anteriores[int(linha["numero_matricula"])] = linha
                processados += 1
                agora = time.monotonic()
                if agora - ultimo_aviso >= 20 or processados == len(pendentes):
                    decorridos = max(agora - inicio_execucao, 0.001)
                    velocidade = processados / decorridos
                    restantes = len(pendentes) - processados
                    eta = restantes / velocidade if velocidade else 0
                    contagem_ok = sum(1 for item in anteriores.values() if item["status"] == "OK")
                    contagem_ausentes = sum(1 for item in anteriores.values() if item["status"] == "NAO_ENCONTRADA")
                    contagem_erros = sum(1 for item in anteriores.values() if item["status"].startswith("ERRO"))
                    print(
                        f"PROGRESSO {processados}/{len(pendentes)} desta execução; "
                        f"base: ok={contagem_ok}, ausentes={contagem_ausentes}, erros={contagem_erros}; "
                        f"velocidade={velocidade:.1f}/s; eta={eta / 60:.1f}min",
                        flush=True,
                    )
                    ultimo_aviso = agora

    resumo = gravar_resumo(args.saida, anteriores, args.inicio, args.fim)
    erros = sum(1 for item in anteriores.values() if item["status"].startswith("ERRO"))
    print(f"CONCLUÍDO relatório={args.saida} resumo={resumo} erros={erros}", flush=True)
    return 2 if erros else 0


if __name__ == "__main__":
    raise SystemExit(main())
