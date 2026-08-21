"""Indexa normas locais na base jurídica do AERI.

Uso seguro (a URL do banco deve estar no ambiente, nunca na linha de comando):
    python -m scripts.indexar_fontes_juridicas "C:\\Normas" --usuario ADMIN
    python -m scripts.indexar_fontes_juridicas pacote.zip --simular
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from backend.app.database import conectar, preparar_banco
from backend.app.servicos.fontes_juridicas import (
    TIPOS_SUPORTADOS,
    preparar_documento,
    salvar_documento_cursor,
)


MAXIMO_ARQUIVOS_ZIP = 1_000
MAXIMO_BYTES_DESCOMPACTADOS = 750_000_000
MAXIMO_BYTES_ARQUIVO = 150_000_000


def _extrair_zip_seguro(caminho: Path, destino: Path) -> None:
    with zipfile.ZipFile(caminho) as pacote:
        membros = [item for item in pacote.infolist() if not item.is_dir()]
        if len(membros) > MAXIMO_ARQUIVOS_ZIP:
            raise ValueError(f"Pacote excede {MAXIMO_ARQUIVOS_ZIP} arquivos.")
        total = sum(item.file_size for item in membros)
        if total > MAXIMO_BYTES_DESCOMPACTADOS:
            raise ValueError("Pacote excede o limite de 750 MB descompactados.")
        raiz = destino.resolve()
        for membro in membros:
            if membro.file_size > MAXIMO_BYTES_ARQUIVO:
                raise ValueError(f"Arquivo muito grande no pacote: {membro.filename}")
            alvo = (destino / membro.filename).resolve()
            if raiz not in alvo.parents:
                raise ValueError(f"Caminho inseguro no pacote: {membro.filename}")
            alvo.parent.mkdir(parents=True, exist_ok=True)
            with pacote.open(membro) as origem, alvo.open("wb") as saida:
                shutil.copyfileobj(origem, saida)


def _arquivos_suportados(caminho: Path) -> list[Path]:
    if caminho.is_file() and caminho.suffix.lower() in TIPOS_SUPORTADOS:
        return [caminho]
    if caminho.is_dir():
        return sorted(
            item for item in caminho.rglob("*")
            if item.is_file()
            and item.suffix.lower() in TIPOS_SUPORTADOS
            and not item.name.startswith("~$")
        )
    return []


def _fontes_entrada(caminhos: list[Path], temporario: Path) -> list[Path]:
    fontes = []
    for indice, caminho in enumerate(caminhos):
        if not caminho.exists():
            raise FileNotFoundError(f"Fonte não encontrada: {caminho}")
        if caminho.suffix.lower() == ".zip":
            destino = temporario / f"pacote-{indice + 1}"
            destino.mkdir(parents=True, exist_ok=True)
            _extrair_zip_seguro(caminho, destino)
            fontes.extend(_arquivos_suportados(destino))
        else:
            fontes.extend(_arquivos_suportados(caminho))
    unicos = {}
    for fonte in fontes:
        unicos[str(fonte.resolve()).lower()] = fonte
    return list(unicos.values())


def executar(caminhos: list[Path], usuario: str, simular: bool = False) -> dict:
    resumo = {
        "arquivos": 0,
        "indexados": 0,
        "ja_indexados": 0,
        "sem_texto": 0,
        "parciais": 0,
        "trechos": 0,
        "sem_texto_arquivos": [],
        "parciais_arquivos": [],
        "falhas": [],
    }
    with tempfile.TemporaryDirectory(prefix="aeri-fontes-") as pasta:
        fontes = _fontes_entrada(caminhos, Path(pasta))
        resumo["arquivos"] = len(fontes)
        if not simular:
            preparar_banco()
        for indice, fonte in enumerate(fontes, start=1):
            try:
                documento = preparar_documento(fonte)
                resumo["trechos"] += len(documento["trechos"])
                if not documento["texto_extraido"]:
                    resumo["sem_texto"] += 1
                    resumo["sem_texto_arquivos"].append(fonte.name)
                elif documento["qualidade_extracao"] == "PARCIAL":
                    resumo["parciais"] += 1
                    resumo["parciais_arquivos"].append(fonte.name)
                if simular:
                    estado = "SIMULADO"
                else:
                    with conectar() as conexao:
                        with conexao.cursor() as cursor:
                            retorno = salvar_documento_cursor(cursor, documento, usuario)
                        conexao.commit()
                    estado = retorno["estado"]
                    resumo["indexados" if estado == "INDEXADO" else "ja_indexados"] += 1
                print(json.dumps({
                    "progresso": f"{indice}/{len(fontes)}",
                    "arquivo": fonte.name,
                    "estado": estado,
                    "paginas": documento["total_paginas"],
                    "trechos": len(documento["trechos"]),
                    "qualidade": documento["qualidade_extracao"],
                }, ensure_ascii=False), flush=True)
            except Exception as erro:  # uma fonte defeituosa não interrompe todo o lote
                falha = {"arquivo": fonte.name, "erro": str(erro)[:500]}
                resumo["falhas"].append(falha)
                print(json.dumps({"estado": "FALHA", **falha}, ensure_ascii=False), flush=True)
    return resumo


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Indexa normas na base jurídica do AERI.")
    parser.add_argument("fontes", nargs="+", type=Path, help="Arquivos, pastas ou pacotes ZIP.")
    parser.add_argument("--usuario", default="IMPORTADOR_LOCAL", help="Responsável registrado na auditoria.")
    parser.add_argument("--simular", action="store_true", help="Extrai e mede sem gravar no banco.")
    parser.add_argument("--relatorio", type=Path, help="Salva o resumo JSON neste arquivo.")
    argumentos = parser.parse_args()
    if not argumentos.simular and not (os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")):
        parser.error("Configure POSTGRES_URL ou DATABASE_URL no ambiente.")
    resumo = executar(argumentos.fontes, argumentos.usuario[:80], argumentos.simular)
    if argumentos.relatorio:
        argumentos.relatorio.parent.mkdir(parents=True, exist_ok=True)
        argumentos.relatorio.write_text(
            json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8",
        )
    print(json.dumps({"resumo": resumo}, ensure_ascii=False, indent=2))
    return 1 if resumo["falhas"] else 0


if __name__ == "__main__":
    sys.exit(main())
