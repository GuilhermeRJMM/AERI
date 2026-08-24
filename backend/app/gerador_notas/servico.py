"""Motor do Gerador de Notas incorporado ao AERI.

O catálogo, os dispositivos legais e o molde foram importados do repositório
``Criador-de-Notas``. O serviço é deliberadamente determinístico: o operador
escolhe as exigências e o motor apenas combina os textos previamente
cadastrados, sem produzir fundamentação nova.
"""

from __future__ import annotations

import html
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from . import documento
from .catalogo import BASE
from .redator import Item, Redator


MOLDE = BASE / "modelo" / "molde-nota.docx"


@lru_cache(maxsize=1)
def redator() -> Redator:
    return Redator()


def sem_acento(texto: str) -> str:
    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caractere) != "Mn"
    ).lower()


def catalogo_para_tela() -> dict:
    motor = redator()
    cru = json.loads((BASE / "dados" / "exigencias.json").read_text(encoding="utf-8"))
    exigencias = sorted(
        motor.cat.exigencias.values(),
        key=lambda exigencia: (exigencia["assunto"], exigencia["rotulo"]),
    )
    return {
        # No AERI a validação também é somente leitura: alterações jurídicas
        # precisam entrar no repositório-fonte e passar pelos validadores.
        "somente_leitura": True,
        "especies": [
            {"id": identificador, "rotulo": especie["rotulo"]}
            for identificador, especie in motor.modelo["especies"].items()
        ],
        "campos": cru.get("campos", {}),
        "exigencias": [
            {
                "id": exigencia["id"],
                "rotulo": exigencia["rotulo"],
                "assunto": exigencia["assunto"],
                "defeito": exigencia["defeito"],
                "campos": exigencia.get("campos", []),
                "obrigatorios": motor.campos_obrigatorios(exigencia),
                "exemplos": exigencia.get("exemplos", {}),
                "revisado": bool(exigencia.get("revisado")),
                "impossibilidade": bool(exigencia.get("impossibilidade")),
                "precedentes": len(exigencia.get("precedentes", [])),
                "fundamentos": len(exigencia.get("fundamentos", [])),
            }
            for exigencia in exigencias
        ],
    }


@lru_cache(maxsize=1)
def indice_artigos() -> dict:
    caminho = BASE / "dados" / "artigos.json"
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}


@lru_cache(maxsize=1)
def legislacao() -> list[dict]:
    normas = json.loads((BASE / "dados" / "normas.json").read_text(encoding="utf-8"))["normas"]
    indice = indice_artigos()
    saida = [
        {
            "id": norma["id"],
            "nome": norma["nome"],
            "referencia": norma.get("referencia", ""),
            "esfera": norma.get("esfera", ""),
            "arquivo": norma["fonte"] + ".pdf",
            "tem_pdf": True,
            "artigos": len(indice.get(norma["id"], [])),
        }
        for norma in normas
    ]
    return sorted(saida, key=lambda item: item["nome"])


def procurar_artigos(norma: str, termo: str, limite: int = 25) -> list[dict]:
    termo = (termo or "").strip()[:160]
    lista = indice_artigos().get(norma, [])
    if not termo:
        return [
            {"artigo": artigo["artigo"], "texto": artigo["texto"][:400]}
            for artigo in lista[:limite]
        ]

    numero = re.fullmatch(r"(?:art\.?\s*)?(\d{1,4}(?:\s*-\s*[A-Za-z]{1,3})?)", termo, re.I)
    if numero:
        alvo = "art. " + re.sub(r"\s*-\s*", "-", numero.group(1)).upper()
        achados = [artigo for artigo in lista if artigo["artigo"].lower() == alvo.lower()]
        achados += [
            artigo
            for artigo in lista
            if artigo["artigo"].lower().startswith(alvo.lower()) and artigo not in achados
        ]
        return [
            {"artigo": artigo["artigo"], "texto": artigo["texto"][:1500]}
            for artigo in achados[:limite]
        ]

    palavras = [sem_acento(palavra) for palavra in termo.split() if len(palavra) > 2]
    pontuados = []
    for artigo in lista:
        texto = sem_acento(artigo["texto"])
        presentes = [palavra for palavra in palavras if palavra in texto]
        if presentes:
            pontuados.append((len(presentes), -min(texto.index(palavra) for palavra in presentes), artigo))
    pontuados.sort(key=lambda item: (-item[0], -item[1]))
    return [
        {"artigo": artigo["artigo"], "texto": artigo["texto"][:600]}
        for _, _, artigo in pontuados[:limite]
    ]


@lru_cache(maxsize=1)
def revisao() -> list[dict]:
    motor = redator()
    cru = json.loads((BASE / "dados" / "exigencias.json").read_text(encoding="utf-8"))
    exemplos = {
        campo: configuracao.get("exemplo", campo)
        for campo, configuracao in cru.get("campos", {}).items()
    }
    saida = []
    for exigencia in sorted(
        motor.cat.exigencias.values(),
        key=lambda item: (item["assunto"], item["rotulo"]),
    ):
        proprios = exigencia.get("exemplos", {})
        valores = {
            campo: proprios.get(campo, exemplos.get(campo, campo))
            for campo in exigencia.get("campos", [])
        }
        blocos = motor._exigencia(Item(exigencia["id"], valores), 1)
        texto = "".join(
            f"<strong><u>{html.escape(parte)}</u></strong>"
            if "negrito" in marcas
            else html.escape(parte)
            for parte, marcas in blocos[0].partes
        )
        fundamentos = [
            {
                "norma": motor.cat.nome_norma(fundamento["norma"]),
                "artigo": fundamento["artigo"],
                "texto": motor.cat.texto_dispositivo(
                    fundamento["norma"],
                    fundamento["artigo"],
                    fundamento.get("partes"),
                ),
            }
            for fundamento in exigencia.get("fundamentos", [])
        ]
        precedentes = [
            {
                "identificacao": motor.cat.precedente(identificador)["identificacao"],
                "tipo": motor.cat.precedente(identificador)["tipo"],
                "texto": motor.cat.precedente(identificador)["texto"],
                "fonte": motor.cat.precedente(identificador)["fonte"],
            }
            for identificador in exigencia.get("precedentes", [])
        ]
        saida.append(
            {
                "id": exigencia["id"],
                "rotulo": exigencia["rotulo"],
                "texto": texto,
                "revisado": bool(exigencia.get("revisado")),
                "fundamentos": fundamentos,
                "precedentes": precedentes,
                "impossibilidade": bool(exigencia.get("impossibilidade")),
                "pendente": exigencia.get("fundamentacao_pendente"),
            }
        )
    return saida


def previa(dados: dict) -> dict:
    motor = redator()
    cru = json.loads((BASE / "dados" / "exigencias.json").read_text(encoding="utf-8"))
    rotulos = {campo: item.get("rotulo", campo) for campo, item in cru.get("campos", {}).items()}
    itens, faltando = [], []
    for item in dados.get("itens", []):
        exigencia = motor.cat.exigencia(item["exigencia"])
        obrigatorios = set(motor.campos_obrigatorios(exigencia))
        valores = {}
        for campo in exigencia.get("campos", []):
            valor = str(item.get("valores", {}).get(campo) or "").strip()
            if not valor and campo in obrigatorios:
                valor = f"«{rotulos.get(campo, campo)}»"
                faltando.append(rotulos.get(campo, campo))
            valores[campo] = valor
        itens.append(Item(item["exigencia"], valores))

    if not itens:
        return {"html": "", "faltando": []}

    titulo = str(dados.get("titulo") or "").strip() or "«título apresentado»"
    blocos = motor.redige(
        dados.get("especie", "devolutiva"),
        titulo,
        itens,
        judicial=bool(dados.get("judicial", False)),
    )
    partes = []
    for bloco in blocos:
        if bloco.papel in {"vazio", "vazio_fund"}:
            partes.append('<div class="p-vazio"></div>')
            continue
        corpo = f'<span class="numero">{bloco.numero}.</span> ' if bloco.papel == "exigencia" else ""
        for texto, marcas in bloco.partes:
            trecho = html.escape(texto).replace("«", '<span class="falta">«').replace("»", "»</span>")
            if "negrito" in marcas and "sublinhado" in marcas:
                trecho = f"<strong><u>{trecho}</u></strong>"
            elif "negrito" in marcas:
                trecho = f"<strong>{trecho}</strong>"
            corpo += trecho
        partes.append(f'<div class="p-{bloco.papel}">{corpo}</div>')
    return {"html": "".join(partes), "faltando": sorted(set(faltando))}


def nome_arquivo(protocolo: str, especie: str) -> str:
    protocolo = re.sub(r"[^0-9A-Za-z._-]+", "-", protocolo.strip())[:80].strip("-._")
    especie = re.sub(r"[^0-9A-Za-zÀ-ÿ._-]+", "-", especie.strip())[:80].strip("-._")
    prefixo = f"{protocolo} - " if protocolo else ""
    return f"{prefixo}{especie.capitalize()}.docx"


def gerar_documento(dados: dict) -> tuple[str, bytes, list[str]]:
    motor = redator()
    itens = [
        Item(str(item["exigencia"]), item.get("valores", {}))
        for item in dados["itens"]
    ]
    blocos = motor.redige(
        dados["especie"],
        dados["titulo"],
        itens,
        judicial=bool(dados.get("judicial", False)),
    )
    nome = nome_arquivo(str(dados.get("protocolo", "")), dados["especie"])
    conteudo = documento.em_bytes(blocos, MOLDE)
    return nome, conteudo, motor.nao_revisadas(itens)
