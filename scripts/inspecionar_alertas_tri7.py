import argparse
import csv
import json
import re
import sys
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from scripts.auditar_semantica_tri7 import (
    ClienteTri7,
    analisar_matricula,
    cabecalho_matricula,
    carregar_env_local,
    separar_atos,
)
from backend.app.proprietarios import (
    extrair_bloco,
    extrair_pessoas,
    extrair_proprietario_inicial,
)


def argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Consulta amostras de alertas sem armazenar o texto registral."
    )
    parser.add_argument("--alerta", required=True)
    parser.add_argument("--limite", type=int, default=8)
    parser.add_argument(
        "--matriculas",
        help="Números separados por vírgula; quando informado, substitui a amostra do CSV.",
    )
    parser.add_argument(
        "--entrada",
        type=Path,
        default=RAIZ / "output" / "relatorios" / "auditoria_registral-v4.csv",
    )
    return parser.parse_args()


def selecionar_amostra(caminho: Path, alerta: str, limite: int) -> list[dict]:
    ultimos: dict[int, dict] = {}
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            ultimos[int(linha["numero_matricula"])] = linha
    candidatas = [
        linha
        for _, linha in sorted(ultimos.items())
        if alerta in str(linha.get("alertas", "")).split(";")
    ]
    if len(candidatas) <= limite:
        return candidatas
    indices = {
        round(indice * (len(candidatas) - 1) / (limite - 1))
        for indice in range(limite)
    }
    return [candidatas[indice] for indice in sorted(indices)]


def resumir_ato(ato: dict) -> dict:
    return {
        "codigo": ato.get("codigo", ""),
        "categoria": ato.get("categoria", ""),
        "tipo_onus": ato.get("tipo_onus", ""),
        "status": ato.get("status", ""),
        "cancela_atos": ato.get("cancela_atos", []),
        "descricao": " ".join(str(ato.get("descricao", "")).split())[:4000],
    }


def contextos_relevantes(texto: str, alerta: str) -> list[str]:
    if "CCI" in alerta:
        padrao = r"\bCCI\b"
    elif "ENCERRAMENTO" in alerta:
        padrao = r"\b(?:ENCERRAD[AO]|ENCERRAMENTO|CANCELAMENTO\s+(?:DA|DE)\s+MATR[ÍI]CULA)\b"
    elif "AREA" in alerta:
        padrao = r"\b[ÁA]REA\b"
    elif "CADEIA" in alerta or "VALIDACAO" in alerta:
        padrao = r"\b(?:ADQUIRENTE|COMPRADOR|COUBE\s+A[OA]|FOI\s+ADQUIRID[AO])\b"
    else:
        return []
    encontrados = []
    for correspondencia in re.finditer(padrao, texto, re.IGNORECASE):
        inicio = max(0, correspondencia.start() - 180)
        fim = min(len(texto), correspondencia.end() + 420)
        trecho = " ".join(texto[inicio:fim].split())
        if trecho not in encontrados:
            encontrados.append(trecho)
    return encontrados[:8]


def main() -> int:
    args = argumentos()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.limite < 1:
        raise SystemExit("O limite deve ser positivo.")
    carregar_env_local()
    cliente = ClienteTri7()
    linhas = (
        [{"numero_matricula": numero} for numero in args.matriculas.split(",") if numero.strip()]
        if args.matriculas
        else selecionar_amostra(args.entrada, args.alerta, args.limite)
    )
    for linha in linhas:
        numero = int(linha["numero_matricula"])
        texto = cliente.buscar_texto_matricula(numero)["texto"]
        resultado = analisar_matricula(texto, numero_matricula=numero)
        titulos_atos = (
            [
                {
                    "codigo": ato.get("codigo", ""),
                    "titulo": " ".join(str(ato.get("texto", "")).split())[:240],
                }
                for ato in separar_atos(texto)
            ]
            if "TODOS_ATOS" in args.alerta
            else []
        )
        rastreio_cadeia = []
        if "RASTREIO" in args.alerta:
            atos_texto = separar_atos(texto)
            for indice, ato_texto in enumerate(atos_texto):
                descricao = str(ato_texto.get("texto", ""))
                if not any(
                    termo in descricao.upper()
                    for termo in (
                        "COMPRA E VENDA",
                        "VENDA E COMPRA",
                        "DOAÇÃO",
                        "DOACAO",
                        "INVENTÁRIO",
                        "INVENTARIO",
                        "PARTILHA",
                        "ADJUDICAÇÃO",
                        "ADJUDICACAO",
                    )
                ):
                    continue
                inicio = texto.find(descricao)
                fim = (
                    texto.find(str(atos_texto[indice + 1].get("texto", "")))
                    if indice + 1 < len(atos_texto)
                    else len(texto)
                )
                parcial = texto[:fim if fim > inicio else inicio + len(descricao)]
                parcial_resultado = analisar_matricula(
                    parcial,
                    numero_matricula=numero,
                )
                rastreio_cadeia.append(
                    {
                        "codigo": ato_texto.get("codigo", ""),
                        "proprietarios": parcial_resultado.get("proprietarios_atuais", []),
                    }
                )
        partes_cadeia = []
        proprietarios_cabecalho = []
        if "PARTES" in args.alerta:
            proprietarios_cabecalho = extrair_proprietario_inicial(
                cabecalho_matricula(texto)
            )
            for ato_texto in separar_atos(texto):
                descricao = str(ato_texto.get("texto", ""))
                bloco_adquirente = extrair_bloco(descricao, "ADQUIRENTE")
                bloco_transmitente = extrair_bloco(descricao, "TRANSMITENTE")
                contexto_estado_civil = any(
                    termo in descricao.upper()
                    for termo in ("SEPARA", "DIVÓRC", "DIVORC", "DESQUIT")
                )
                if not bloco_adquirente and not bloco_transmitente and not contexto_estado_civil:
                    continue
                partes_cadeia.append(
                    {
                        "codigo": ato_texto.get("codigo", ""),
                        "adquirentes": extrair_pessoas(bloco_adquirente),
                        "transmitentes": extrair_pessoas(bloco_transmitente),
                        "bloco_transmitente": " ".join(
                            (bloco_transmitente or descricao).split()
                        )[:2000],
                    }
                )
        codigos = {
            codigo
            for campo in (
                "onus_explicitos_nao_classificados_codigos",
                "onus_ativos_nao_confirmados_codigos",
                "cancelamentos_sem_alvo_codigos",
                "cancelamentos_alvo_divergente_codigos",
            )
            for codigo in str(linha.get(campo, "")).split(",")
            if codigo
        }
        codigos.update(
            codigo
            for codigo in str(linha.get("evidencias_cadeia", "")).split(",")
            if codigo.startswith(("R.", "AV."))
        )
        if args.alerta == "CANCELAMENTO_POSSIVELMENTE_INCOMPLETO":
            codigos.update(
                str(ato.get("codigo", ""))
                for ato in resultado.get("atos", [])
                if ato.get("categoria") == "CANCELAMENTO"
                or (ato.get("categoria") == "ÔNUS" and ato.get("status") == "ATIVO")
            )
        if any(
            marcador in args.alerta
            for marcador in (
                "CCI",
                "AREA",
                "ENCERRAMENTO",
                "TIPO_IMOVEL",
                "RUA",
                "SETOR",
                "CEP",
                "INCRA",
            )
        ):
            termos = (
                "DESIGNAÇÃO CADASTRAL",
                "DESIGNACAO CADASTRAL",
                "CCI",
                "ÁREA",
                "AREA",
                "ENCERR",
                "CEP",
                "INCRA",
            )
            codigos.update(
                str(ato.get("codigo", ""))
                for ato in resultado.get("atos", [])
                if any(termo in str(ato.get("descricao", "")).upper() for termo in termos)
            )
        if "CADEIA" in args.alerta or "VALIDACAO" in args.alerta:
            codigos.update(
                str(ato.get("codigo", ""))
                for ato in resultado.get("atos", [])
                if any(
                    termo in str(ato.get("descricao", "")).upper()
                    for termo in (
                        "COMPRA E VENDA",
                        "VENDA E COMPRA",
                        "DOAÇÃO",
                        "DOACAO",
                        "INVENTÁRIO",
                        "INVENTARIO",
                        "PARTILHA",
                        "DAÇÃO",
                        "DACAO",
                        "ARREMATAÇÃO",
                        "ARREMATACAO",
                        "TITULARIDADE",
                    )
                )
            )
            if "FINAL" in args.alerta:
                codigos.update({"AV.27", "AV.29", "AV.30", "AV.31", "R.32"})
            codigos.update(
                str(ato.get("codigo", ""))
                for ato in separar_atos(texto)
                if any(
                    termo in str(ato.get("texto", "")).upper()
                    for termo in (
                        "COMPRA E VENDA",
                        "VENDA E COMPRA",
                        "DOAÇÃO",
                        "DOACAO",
                        "INVENTÁRIO",
                        "INVENTARIO",
                        "PARTILHA",
                        "DAÇÃO",
                        "DACAO",
                        "ARREMATAÇÃO",
                        "ARREMATACAO",
                        "TITULARIDADE",
                    )
                )
            )
        atos_resultado = {
            str(ato.get("codigo", "")): ato for ato in resultado.get("atos", [])
        }
        atos = []
        for ato_texto in separar_atos(texto):
            codigo = str(ato_texto.get("codigo", ""))
            if codigo in codigos:
                ato = atos_resultado.get(codigo, {})
                atos.append(
                    resumir_ato(
                        {
                            **ato,
                            "codigo": codigo,
                            "descricao": ato_texto.get("texto", ""),
                        }
                    )
                )
        print(
            json.dumps(
                {
                    "numero": numero,
                    "alerta": args.alerta,
                    "codigos": sorted(codigos),
                    "resultado": resultado.get("resultado", ""),
                    "proprietarios_atuais": resultado.get("proprietarios_atuais", []),
                    "rastreio_cadeia": rastreio_cadeia,
                    "partes_cadeia": partes_cadeia,
                    "proprietarios_cabecalho": proprietarios_cabecalho,
                    "titulos_atos": titulos_atos,
                    "imovel": resultado.get("imovel", {}),
                    "contextos": contextos_relevantes(texto, args.alerta),
                    "cabecalho": (
                        " ".join(cabecalho_matricula(texto).split())[:6000]
                        if "VALIDACAO" in args.alerta or any(
                            args.alerta in str(linha.get(campo, "")).split(";")
                            for campo in ("alertas_cadeia", "alertas_imovel")
                        )
                        else ""
                    ),
                    "atos": atos,
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
