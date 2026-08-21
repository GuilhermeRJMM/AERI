"""Gera lotes compactos de normas públicas para carga privada no AERI.

Os lotes contêm somente metadados e texto extraído. PDFs, documentos sem
texto e qualquer dado operacional da serventia ficam fora do repositório.
"""

import argparse
import gzip
import json
import re
import tempfile
from pathlib import Path

from backend.app.servicos.fontes_juridicas import preparar_documento
from scripts.indexar_fontes_juridicas import _fontes_entrada


EXCLUIR_NOMES = re.compile(
    r"(?:^~\$|THUMBS|JERONIMO|\bPIX\b|MEMORIAL|NOTA\s+PROTOCOLO|"
    r"SEI_GOVERNADORIA|^MA(?:PA|PP)?\b|^ME(?:M|MM)?\b|^MPA\b)",
    re.IGNORECASE,
)
NORMAS_PUBLICAS = re.compile(
    r"^(?:\d{4}-\d{2}-\d{2}\s+-\s+LEI|ADI\b|ALTERA[CÇ][AÃ]O\s+DO\s+CEP|"
    r"C[ÓO]DIGO\s+DE\s+OBRAS|CONSULTA\s+-\s+DECIS[AÃ]O|DECIS[AÃ]O\b|"
    r"DECRETO\b|INFORMATIVO\b|INSTRU[CÇ][AÃ]O\s+NORMATIVA|LEI\b|"
    r"NOTA-\d|OF[IÍ]CIO\b|PRAZOS\s+GEORREFERENCIAMENTO|PROVIMENTO\b|"
    r"RESOLU[CÇ][AÃ]O\b|TERMO\s+DE\s+AJUSTE)",
    re.IGNORECASE,
)
MAXIMO_BYTES_LOTE = 3_200_000
MAXIMO_DOCUMENTOS_LOTE = 50


def _fonte_juridica_valida(caminho: Path) -> bool:
    partes = {parte.casefold() for parte in caminho.parts}
    if "obsoleto" in partes or "modelos notas - fundamentacoes legais" in partes:
        return False
    if EXCLUIR_NOMES.search(caminho.stem):
        return False
    if "downloads" in partes and "leis" in partes:
        return True
    return bool(NORMAS_PUBLICAS.search(caminho.stem))


def gerar(fontes: list[Path], destino: Path) -> dict:
    documentos_por_hash = {}
    sem_texto = []
    falhas = []
    with tempfile.TemporaryDirectory(prefix="aeri-base-juridica-") as pasta:
        arquivos = [
            arquivo for arquivo in _fontes_entrada(fontes, Path(pasta))
            if _fonte_juridica_valida(arquivo)
        ]
        for indice, arquivo in enumerate(arquivos, start=1):
            try:
                documento = preparar_documento(arquivo)
                if not documento["texto_extraido"] or not documento["trechos"]:
                    sem_texto.append(arquivo.name)
                else:
                    documentos_por_hash.setdefault(documento["sha256"], documento)
                print(json.dumps({
                    "progresso": f"{indice}/{len(arquivos)}",
                    "arquivo": arquivo.name,
                    "qualidade": documento["qualidade_extracao"],
                    "trechos": len(documento["trechos"]),
                }, ensure_ascii=False), flush=True)
            except Exception as erro:
                falhas.append({"arquivo": arquivo.name, "erro": str(erro)[:300]})
    documentos = sorted(
        documentos_por_hash.values(),
        key=lambda item: (item["jurisdicao"], item["titulo"].casefold()),
    )
    destino.mkdir(parents=True, exist_ok=True)
    lotes, lote = [], []

    def compactar(itens: list[dict]) -> bytes:
        serializado = json.dumps(
            itens, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        return gzip.compress(serializado, compresslevel=9)

    for documento in documentos:
        candidato = lote + [documento]
        if lote and (
            len(candidato) > MAXIMO_DOCUMENTOS_LOTE
            or len(compactar(candidato)) > MAXIMO_BYTES_LOTE
        ):
            lotes.append(compactar(lote))
            lote = [documento]
        else:
            lote = candidato
    if lote:
        lotes.append(compactar(lote))
    arquivos_lotes = []
    for indice, conteudo in enumerate(lotes, start=1):
        caminho_lote = destino / f"fontes-juridicas-{indice:02d}.json.gz"
        caminho_lote.write_bytes(conteudo)
        arquivos_lotes.append(str(caminho_lote))
    return {
        "arquivos_lidos": len(arquivos),
        "fontes_incluidas": len(documentos),
        "trechos": sum(len(item["trechos"]) for item in documentos),
        "sem_texto": len(sem_texto),
        "sem_texto_arquivos": sem_texto,
        "falhas": falhas,
        "lotes": arquivos_lotes,
        "bytes_compactados": sum(len(item) for item in lotes),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fontes", nargs="+", type=Path)
    parser.add_argument(
        "--destino",
        type=Path,
        default=Path("output/base_juridica_carga"),
    )
    parser.add_argument("--relatorio", type=Path)
    argumentos = parser.parse_args()
    resumo = gerar(argumentos.fontes, argumentos.destino)
    if argumentos.relatorio:
        argumentos.relatorio.parent.mkdir(parents=True, exist_ok=True)
        argumentos.relatorio.write_text(
            json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8",
        )
    print(json.dumps({"resumo": resumo}, ensure_ascii=True, indent=2))
    return 1 if resumo["falhas"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
