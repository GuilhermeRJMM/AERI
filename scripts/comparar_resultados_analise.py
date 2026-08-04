"""Compara dois arquivos JSONL de auditoria sem acessar a Tri7.

Cada linha deve conter ``numero_matricula`` e o resultado estruturado da análise.
O comando termina com código 1 quando encontra regressões, permitindo seu uso
em uma esteira de validação antes da publicação.
"""

import argparse
import json
from pathlib import Path


CAMPOS = ("resultado", "publicidade", "atos", "proprietarios_atuais", "imovel")


def carregar(caminho: Path) -> dict[str, dict]:
    itens = {}
    with caminho.open(encoding="utf-8") as arquivo:
        for numero_linha, linha in enumerate(arquivo, 1):
            if not linha.strip():
                continue
            item = json.loads(linha)
            numero = str(item.get("numero_matricula", "")).strip()
            if not numero:
                raise ValueError(f"Linha {numero_linha} sem numero_matricula em {caminho}.")
            itens[numero] = item
    return itens


def comparar(base: dict[str, dict], atual: dict[str, dict]) -> list[dict]:
    diferencas = []
    for numero in sorted(set(base) | set(atual), key=lambda valor: (len(valor), valor)):
        if numero not in base or numero not in atual:
            diferencas.append({"numero_matricula": numero, "campo": "registro", "base": numero in base, "atual": numero in atual})
            continue
        for campo in CAMPOS:
            if base[numero].get(campo) != atual[numero].get(campo):
                diferencas.append({"numero_matricula": numero, "campo": campo})
    return diferencas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("atual", type=Path)
    parser.add_argument("--saida", type=Path)
    args = parser.parse_args()
    diferencas = comparar(carregar(args.base), carregar(args.atual))
    relatorio = {"total_diferencas": len(diferencas), "diferencas": diferencas}
    texto = json.dumps(relatorio, ensure_ascii=False, indent=2)
    if args.saida:
        args.saida.write_text(texto + "\n", encoding="utf-8")
    print(texto)
    return 1 if diferencas else 0


if __name__ == "__main__":
    raise SystemExit(main())
