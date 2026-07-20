import argparse
import csv
import json
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend.app.servicos.tri7 import ClienteTri7, ErroTri7
from scripts.validar_base_tri7 import LimitadorTaxa, carregar_env_local


PADROES_ALTERNATIVOS = {
    "R_AV_COM_SEPARADOR_ALTERNATIVO": re.compile(
        r"(?im)^[ \t\-–—]*(?:R|AV)\s*(?:[º°/:]|N[º°.]?)\s*[0-9OIL]{1,4}\b"
    ),
    "AV_PONTUADO": re.compile(
        r"(?im)^[ \t\-–—]*A\s*\.\s*V\s*\.\s*[0-9OIL]{1,4}\b"
    ),
    "REGISTRO_POR_EXTENSO": re.compile(
        r"(?im)^[ \t\-–—]*REGISTRO\s*(?:N[º°.]?|[.(:\-])?\s*[0-9OIL]{1,4}\b"
    ),
    "AVERBACAO_POR_EXTENSO": re.compile(
        r"(?im)^[ \t\-–—]*AVERBA(?:ÇÃO|CAO)\s*(?:N[º°.]?|[.(:\-])?\s*[0-9OIL]{1,4}\b"
    ),
    "NUMERO_COM_OCR": re.compile(
        r"(?im)^[ \t\-–—]*(?:R|AV)\s*[.\-]\s*[OIL]+[0-9OIL]*\b"
    ),
}


def ultimos_resultados(caminho: Path) -> dict[int, dict]:
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        return {int(linha["numero_matricula"]): linha for linha in csv.DictReader(arquivo)}


def auditar(numero: int, cliente: ClienteTri7, limitador: LimitadorTaxa) -> tuple[int, list[str], str]:
    for tentativa in range(3):
        try:
            limitador.aguardar()
            texto = cliente.buscar_texto_matricula(numero)["texto"]
            assinaturas = [nome for nome, padrao in PADROES_ALTERNATIVOS.items() if padrao.search(texto)]
            return numero, assinaturas, ""
        except ErroTri7 as erro:
            if tentativa < 2:
                time.sleep(2 ** tentativa)
                continue
            return numero, [], str(erro)[:200]
    raise RuntimeError("Fluxo de tentativas inválido.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audita cabeçalhos alternativos em matrículas sem blocos R/AV.")
    parser.add_argument("--entrada", type=Path, required=True)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--rps", type=float, default=12)
    args = parser.parse_args()

    carregar_env_local()
    resultados = ultimos_resultados(args.entrada)
    numeros = sorted(
        numero for numero, linha in resultados.items()
        if linha["status"] == "OK" and int(linha.get("blocos") or 0) == 0
    )
    cliente = ClienteTri7()
    limitador = LimitadorTaxa(args.rps)
    candidatos: dict[str, list[int]] = {nome: [] for nome in PADROES_ALTERNATIVOS}
    erros: dict[int, str] = {}
    concluidos = 0
    print(f"Auditando {len(numeros)} matrículas sem blocos...", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futuros = {executor.submit(auditar, numero, cliente, limitador): numero for numero in numeros}
        for futuro in as_completed(futuros):
            numero, assinaturas, erro = futuro.result()
            if erro:
                erros[numero] = erro
            for assinatura in assinaturas:
                candidatos[assinatura].append(numero)
            concluidos += 1
            if concluidos % 500 == 0 or concluidos == len(numeros):
                print(f"PROGRESSO {concluidos}/{len(numeros)}", flush=True)

    candidatos = {chave: sorted(valores) for chave, valores in candidatos.items() if valores}
    relatorio = {
        "matriculas_sem_blocos": len(numeros),
        "assinaturas_encontradas": {chave: len(valores) for chave, valores in candidatos.items()},
        "matriculas_por_assinatura": candidatos,
        "erros_api": erros,
        "observacao": "Nenhum texto registral ou dado pessoal foi armazenado.",
    }
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"CONCLUÍDO {args.saida}", flush=True)
    return 1 if erros else 0


if __name__ == "__main__":
    raise SystemExit(main())
