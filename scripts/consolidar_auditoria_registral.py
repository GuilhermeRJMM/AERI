import argparse
import csv
import json
from collections import Counter
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent
DOMINIOS = ("onus", "cadeia", "imovel")
CAMPOS_DOMINIO = [
    "numero_matricula",
    "status",
    "situacao_aeri",
    "prioridade_revisao",
    "confianca",
    "veredito",
    "alertas",
    "evidencias",
    "resultado_onus_aeri",
    "erro",
]
CAMPOS_MASTER = [
    "numero_matricula",
    "status",
    "situacao_aeri",
    "prioridade_revisao",
    "estado_auditoria",
    "confianca_onus",
    "confianca_cadeia",
    "confianca_imovel",
    "veredito_onus",
    "veredito_cadeia",
    "veredito_imovel",
    "alertas_onus",
    "alertas_cadeia",
    "alertas_imovel",
    "evidencias_onus",
    "evidencias_cadeia",
    "evidencias_imovel",
    "erro",
]


def argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Separa a auditoria registral do AERI em ônus, cadeia dominial e dados do imóvel."
    )
    parser.add_argument("--entrada", type=Path, required=True)
    parser.add_argument(
        "--saida",
        type=Path,
        default=RAIZ / "output" / "relatorios" / "auditoria_registral",
    )
    parser.add_argument("--inicio", type=int, default=1)
    parser.add_argument("--fim", type=int, default=39_767)
    return parser.parse_args()


def ler_ultima_tentativa(caminho: Path, inicio: int, fim: int) -> dict[int, dict]:
    resultados: dict[int, dict] = {}
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            try:
                numero = int(linha.get("numero_matricula", ""))
            except (TypeError, ValueError):
                continue
            if inicio <= numero <= fim:
                resultados[numero] = linha
    return resultados


def gravar_csv(caminho: Path, campos: list[str], linhas: list[dict]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=campos)
        escritor.writeheader()
        for linha in linhas:
            escritor.writerow({campo: linha.get(campo, "") for campo in campos})


def prioridade_numerica(valor: str) -> int:
    if str(valor).startswith("P0"):
        return 0
    if str(valor).startswith("P1"):
        return 1
    return 2


def consolidar(entrada: Path, saida: Path, inicio: int, fim: int) -> dict:
    resultados = ler_ultima_tentativa(entrada, inicio, fim)
    linhas_ordenadas = [resultados[numero] for numero in sorted(resultados)]
    gravar_csv(saida / "auditoria_master.csv", CAMPOS_MASTER, linhas_ordenadas)

    resumo = {
        "faixa": {"inicio": inicio, "fim": fim, "quantidade": fim - inicio + 1},
        "matriculas_consolidadas": len(resultados),
        "status": dict(Counter(linha.get("status", "") for linha in linhas_ordenadas)),
        "prioridades": dict(
            Counter(linha.get("prioridade_revisao", "") for linha in linhas_ordenadas)
        ),
        "estados": dict(
            Counter(linha.get("estado_auditoria", "") for linha in linhas_ordenadas)
        ),
        "dominios": {},
        "observacao": (
            "Relatório técnico sem texto registral, nomes ou documentos pessoais. "
            "Alertas indicam necessidade de conferência; não constituem conclusão jurídica."
        ),
    }

    for dominio in DOMINIOS:
        alertas_por_tipo: Counter[str] = Counter()
        linhas_dominio = []
        for linha in linhas_ordenadas:
            alertas = str(linha.get(f"alertas_{dominio}", "")).strip()
            if not alertas:
                continue
            for alerta in filter(None, alertas.split(";")):
                alertas_por_tipo[alerta] += 1
            linhas_dominio.append(
                {
                    "numero_matricula": linha.get("numero_matricula", ""),
                    "status": linha.get("status", ""),
                    "situacao_aeri": linha.get("situacao_aeri", ""),
                    "prioridade_revisao": linha.get("prioridade_revisao", ""),
                    "confianca": linha.get(f"confianca_{dominio}", ""),
                    "veredito": linha.get(f"veredito_{dominio}", ""),
                    "alertas": alertas,
                    "evidencias": linha.get(f"evidencias_{dominio}", ""),
                    "resultado_onus_aeri": linha.get("resultado_onus_aeri", ""),
                    "erro": linha.get("erro", ""),
                }
            )
        linhas_dominio.sort(
            key=lambda item: (
                prioridade_numerica(item["prioridade_revisao"]),
                int(item["numero_matricula"]),
            )
        )
        gravar_csv(saida / f"revisao_{dominio}.csv", CAMPOS_DOMINIO, linhas_dominio)
        resumo["dominios"][dominio] = {
            "matriculas_para_revisao": len(linhas_dominio),
            "alertas_por_tipo": dict(alertas_por_tipo.most_common()),
        }

    (saida / "resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return resumo


def main() -> int:
    args = argumentos()
    if args.inicio < 1 or args.fim < args.inicio:
        raise SystemExit("Faixa inválida.")
    resumo = consolidar(args.entrada, args.saida, args.inicio, args.fim)
    print(json.dumps(resumo, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
