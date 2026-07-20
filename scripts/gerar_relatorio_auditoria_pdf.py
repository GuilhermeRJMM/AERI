import argparse
import csv
from collections import Counter
from datetime import datetime
from pathlib import Path

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)


ROTULOS_ALERTAS = {
    "ADQUIRENTE_ROTULADO_NAO_EXTRAIDO": "Adquirente identificado no texto, mas não extraído",
    "AREA_CONSTRUIDA_NAO_EXTRAIDO": "Área construída mencionada, mas não extraída",
    "AREA_NAO_EXTRAIDO": "Área do imóvel mencionada, mas não extraída",
    "CADEIA_DOMINIAL_VAZIA_COM_TRANSFERENCIA": "Cadeia dominial vazia apesar de existir transferência",
    "CAR_NAO_EXTRAIDO": "CAR mencionado, mas não extraído",
    "CCIR_NAO_EXTRAIDO": "CCIR mencionado, mas não extraído",
    "CCI_NAO_EXTRAIDO": "CCI mencionado, mas não extraído",
    "CEP_NAO_EXTRAIDO": "CEP mencionado, mas não extraído",
    "ENCERRAMENTO_NAO_RECONHECIDO": "Encerramento mencionado, mas não reconhecido",
    "TITULARIDADE_FORA_DE_100": "Percentual total de titularidade diferente de 100%",
}

PRIORIDADE_ALTA = {
    "ADQUIRENTE_ROTULADO_NAO_EXTRAIDO",
    "CADEIA_DOMINIAL_VAZIA_COM_TRANSFERENCIA",
    "ENCERRAMENTO_NAO_RECONHECIDO",
    "TITULARIDADE_FORA_DE_100",
}


def argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gera o relatório PDF da auditoria semântica do AERI.")
    parser.add_argument("--entrada", type=Path, required=True)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--inicio", type=int, default=13001)
    parser.add_argument("--fim", type=int, default=39767)
    return parser.parse_args()


def ler_resultados(caminho: Path, inicio: int, fim: int) -> dict[int, dict]:
    resultados: dict[int, dict] = {}
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            try:
                numero = int(linha.get("numero_matricula", ""))
            except ValueError:
                continue
            if inicio <= numero <= fim:
                # O arquivo pode conter uma nova tentativa da mesma matrícula.
                # A linha mais recente representa o resultado consolidado.
                resultados[numero] = linha
    return resultados


def registrar_fontes() -> None:
    pasta = Path("C:/Windows/Fonts")
    pdfmetrics.registerFont(TTFont("Calibri", str(pasta / "calibri.ttf")))
    pdfmetrics.registerFont(TTFont("Calibri-Bold", str(pasta / "calibrib.ttf")))


def alertas_da_linha(linha: dict) -> list[str]:
    return [item for item in str(linha.get("alertas", "")).split(";") if item]


def rotulo_alerta(alerta: str) -> str:
    return ROTULOS_ALERTAS.get(alerta, alerta.replace("_", " ").capitalize())


def prioridade(linha: dict) -> int:
    return 0 if PRIORIDADE_ALTA.intersection(alertas_da_linha(linha)) else 1


def gerar_pdf(entrada: Path, saida: Path, inicio: int, fim: int) -> None:
    registrar_fontes()
    resultados = ler_resultados(entrada, inicio, fim)
    esperadas = fim - inicio + 1
    alertadas = [(numero, linha) for numero, linha in resultados.items() if alertas_da_linha(linha)]
    alertadas.sort(key=lambda item: (prioridade(item[1]), item[0]))
    nao_processadas = [
        (numero, linha)
        for numero, linha in sorted(resultados.items())
        if linha.get("status") not in {"OK", "NAO_ENCONTRADA"}
    ]
    contagem_alertas = Counter(
        alerta for _, linha in alertadas for alerta in alertas_da_linha(linha)
    )

    saida.parent.mkdir(parents=True, exist_ok=True)
    documento = SimpleDocTemplate(
        str(saida),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Relatório de auditoria AERI - matrículas {inicio} a {fim}",
        author="AERI",
    )
    base = ParagraphStyle(
        "Base",
        fontName="Calibri",
        fontSize=12,
        leading=15,
        spaceAfter=5,
    )
    titulo = ParagraphStyle(
        "Titulo",
        parent=base,
        fontName="Calibri-Bold",
        alignment=TA_CENTER,
        spaceAfter=12,
    )
    secao = ParagraphStyle(
        "Secao",
        parent=base,
        fontName="Calibri-Bold",
        spaceBefore=10,
        spaceAfter=7,
    )
    item_titulo = ParagraphStyle(
        "ItemTitulo",
        parent=base,
        fontName="Calibri-Bold",
        spaceAfter=1,
    )

    historia = [
        Paragraph("RELATÓRIO FINAL DE AUDITORIA SEMÂNTICA DO AERI", titulo),
        Paragraph(f"Faixa analisada: matrículas {inicio:,} a {fim:,}.".replace(",", "."), base),
        Paragraph(
            f"Resultados consolidados: {len(resultados):,} de {esperadas:,} matrículas; "
            f"{len(alertadas):,} matrículas alertadas."
            .replace(",", "."),
            base,
        ),
        Paragraph(f"Relatório gerado em {datetime.now():%d/%m/%Y às %H:%M}.", base),
        Spacer(1, 5 * mm),
        Paragraph("Critério do relatório", secao),
        Paragraph(
            "Os alertas indicam divergências ou lacunas detectadas automaticamente entre marcadores "
            "presentes no texto e a extração realizada pelo AERI. Um alerta não confirma, isoladamente, "
            "erro jurídico; ele identifica a matrícula que deve ser conferida e usada para aperfeiçoar "
            "as regras do analisador.",
            base,
        ),
        Paragraph("Resumo por tipo de alerta", secao),
    ]
    for alerta, quantidade in sorted(contagem_alertas.items(), key=lambda item: (-item[1], item[0])):
        historia.append(Paragraph(f"• {rotulo_alerta(alerta)}: {quantidade}", base))

    grupos = (
        ("PRIORIDADE ALTA - SITUAÇÃO E TITULARIDADE", 0),
        ("DADOS DO IMÓVEL E IDENTIFICADORES", 1),
    )
    for indice, (nome_grupo, valor_prioridade) in enumerate(grupos):
        historia.append(PageBreak())
        historia.append(Paragraph(nome_grupo, titulo))
        itens = [(numero, linha) for numero, linha in alertadas if prioridade(linha) == valor_prioridade]
        if not itens:
            historia.append(Paragraph("Nenhuma matrícula neste grupo.", base))
            continue
        for numero, linha in itens:
            alertas_formatados = "; ".join(rotulo_alerta(item) for item in alertas_da_linha(linha))
            situacao = linha.get("situacao_aeri") or "Não determinada"
            historia.append(
                KeepTogether(
                    [
                        Paragraph(f"Matrícula {numero:,}".replace(",", "."), item_titulo),
                        Paragraph(f"Situação indicada pelo AERI: {situacao}. Alertas: {alertas_formatados}.", base),
                        Spacer(1, 2 * mm),
                    ]
                )
            )

    historia.append(PageBreak())
    historia.append(Paragraph("CONSULTAS SEM RESULTADO CONCLUSIVO", titulo))
    if nao_processadas:
        for numero, linha in nao_processadas:
            status = linha.get("status") or "INDETERMINADO"
            historia.append(Paragraph(f"Matrícula {numero:,}: {status}.".replace(",", "."), base))
    else:
        historia.append(Paragraph("Nenhuma consulta pendente ou com erro técnico.", base))

    def numerar_pagina(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Calibri", 12)
        canvas.drawCentredString(A4[0] / 2, 9 * mm, f"Página {doc.page}")
        canvas.restoreState()

    documento.build(historia, onFirstPage=numerar_pagina, onLaterPages=numerar_pagina)


def main() -> int:
    args = argumentos()
    gerar_pdf(args.entrada, args.saida, args.inicio, args.fim)
    print(args.saida)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
