"""A camada entre o HTTP e o núcleo.

Existe para que o servidor local (`app.py`) e as funções serverless da Vercel
(`api/*.py`) compartilhem exatamente a mesma lógica. Nada de regra registral
mora aqui — só a tradução de ficha para JSON e de volta.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import fields, is_dataclass
from pathlib import Path

from . import documento as doc
from . import extrator, minuta, ocr
from .ficha import (Contrato, Credora, Documento, Ficha, Financiamento, Juros,
                    Matricula, Pessoa, Procuracao, Valores)

TAMANHO_MAXIMO = 60 * 1024 * 1024      # PDF digitalizado passa fácil de 15 MB


def hospedado() -> bool:
    """True quando roda na Vercel; False quando roda na máquina da serventia.

    A tela precisa saber: "o contrato não sai daqui" só é verdade num dos casos,
    e dizer isso quando não é seria mentir para quem confere."""
    return bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))


# --------------------------------------------------------------- ficha -> json
def para_json(valor):
    if is_dataclass(valor):
        return {c.name: para_json(getattr(valor, c.name)) for c in fields(valor)}
    if isinstance(valor, list):
        return [para_json(v) for v in valor]
    if isinstance(valor, dict):
        return {k: para_json(v) for k, v in valor.items()}
    return valor


# --------------------------------------------------------------- json -> ficha
def _pessoa_de(dados: dict) -> Pessoa:
    if not dados:
        return Pessoa()
    doc_dados = dados.get("documento") or {}
    pessoa = Pessoa(
        nome=dados.get("nome", ""),
        profissao=dados.get("profissao", ""),
        documento=Documento(tipo=doc_dados.get("tipo", ""),
                            numero=doc_dados.get("numero", ""),
                            orgao=doc_dados.get("orgao", "")),
        cpf=dados.get("cpf", ""),
        endereco=dados.get("endereco", ""),
        nascimento=dados.get("nascimento", ""),
        sexo=dados.get("sexo", ""),
        estado_civil=dados.get("estado_civil", ""),
        regime_bens=dados.get("regime_bens", ""),
        marco_lei=dados.get("marco_lei", ""))
    if dados.get("conjuge"):
        pessoa.conjuge = _pessoa_de(dados["conjuge"])
        pessoa.conjuge.anuente = bool(dados["conjuge"].get("anuente"))
    return pessoa


def ficha_de(dados: dict) -> Ficha:
    """Reconstrói a ficha depois que o conferente editou os campos na tela."""
    ficha = Ficha()

    c = dados.get("contrato") or {}
    ficha.contrato = Contrato(**{k: c.get(k, "") for k in
                                 ("numero", "data", "modelo", "descricao",
                                  "modalidade", "item_outorga", "item_reajuste")})

    ficha.vendedores = [_pessoa_de(p) for p in dados.get("vendedores") or []]
    ficha.compradores = [_pessoa_de(p) for p in dados.get("compradores") or []]

    credora = dados.get("credora") or {}
    ficha.credora = Credora(
        representante=(_pessoa_de(credora["representante"])
                       if credora.get("representante") else None),
        procuracoes=[Procuracao(**{k: p.get(k, "") for k in
                                   ("especie", "data", "folhas", "livro", "serventia")})
                     for p in credora.get("procuracoes") or []])

    v = dados.get("valores") or {}
    ficha.valores = Valores(**{k: float(v.get(k) or 0) for k in
                               ("total", "recursos_proprios", "fgts",
                                "desconto_fgts", "financiamento")})

    f = dados.get("financiamento") or {}
    j = f.get("juros") or {}
    ficha.financiamento = Financiamento(
        divida=float(f.get("divida") or 0),
        garantia=float(f.get("garantia") or 0),
        amortizacao=f.get("amortizacao", ""),
        prazo_meses=str(f.get("prazo_meses") or ""),
        juros=Juros(nominal_ao_ano=j.get("nominal_ao_ano", ""),
                    efetiva_ao_ano=j.get("efetiva_ao_ano", ""),
                    efetiva_ao_mes=j.get("efetiva_ao_mes", "")),
        encargo_mensal_total=float(f.get("encargo_mensal_total") or 0),
        primeiro_vencimento=f.get("primeiro_vencimento", ""))

    m = dados.get("matricula") or {}
    ficha.matricula = Matricula(numero=m.get("numero", ""),
                                origem=m.get("origem", ""),
                                proximo_ato=m.get("proximo_ato", ""))

    ficha.origens = dados.get("origens") or {}
    ficha.brutos = dados.get("brutos") or {}
    return ficha


# --------------------------------------------------------------------- geração
def atos(ficha: Ficha) -> dict:
    saida = {}
    for chave, gerador in (("venda", minuta.venda_e_compra),
                           ("alienacao", minuta.alienacao_fiduciaria)):
        ato = gerador(ficha)
        saida[chave] = {
            "texto": ato.texto,
            "pendencias": [{"campo": p.campo, "motivo": p.motivo,
                            "grau": p.grau, "sugestao": p.sugestao}
                           for p in ato.pendencias],
        }
    return saida


def extrai_do_pdf(dados: bytes) -> dict:
    """Recebe os bytes do PDF e devolve a resposta pronta para a tela.

    O arquivo temporário é apagado no `finally`: nem no servidor local nem na
    função serverless o contrato fica em disco depois da resposta.
    """
    if dados[:5] != b"%PDF-":
        raise ValueError("o arquivo enviado não é um PDF.")
    if len(dados) > TAMANHO_MAXIMO:
        raise ValueError(f"arquivo maior que {TAMANHO_MAXIMO // (1024 * 1024)} MB.")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as arquivo:
        arquivo.write(dados)
        caminho = Path(arquivo.name)
    try:
        info = doc.abre(caminho)
        # O extrator decide sozinho se lê o texto ou se chama o OCR — aqui não
        # se repete essa escolha, para os dois caminhos não divergirem.
        ficha = extrator.extrai(caminho)
    finally:
        caminho.unlink(missing_ok=True)

    lida = ficha.origens.get("_natureza", "digitalizado")
    leu_por_ocr = "OCR" in lida
    # A tela diz qual motor leu: Tesseract e o do Windows erram coisas
    # diferentes, e quem confere precisa saber contra o que está conferindo.
    natureza = lida.replace("digitalizado, lido por OCR", "digitalizado · OCR")

    return {
        "natureza": natureza,
        "paginas": info.paginas,
        "ocr": leu_por_ocr,
        "hospedado": hospedado(),
        "ficha": para_json(ficha),
        "atos": atos(ficha),
    }


def gera_de_json(dados: dict) -> dict:
    return {"atos": atos(ficha_de(dados.get("ficha") or {}))}


# ------------------------------------------------------------ conferência prévia
def _exigencias_em_json(conferencia) -> list[dict]:
    return [{"numero": e.numero, "titulo": e.titulo, "detalhe": e.detalhe,
             "fundamento": e.fundamento, "grau": e.grau}
            for e in conferencia.numera()]


def confere_com_matricula(dados_matricula: bytes, ficha_em_json: dict) -> dict:
    """Lê a matrícula e confronta com o contrato já extraído.

    A matrícula entra separada do contrato de propósito: ela chega depois, e o
    conferente pode querer trocá-la sem reprocessar o contrato inteiro — que,
    sendo digitalizado, custa meio minuto de OCR.
    """
    from . import matricula as mt
    from . import qualificacao as qu

    if dados_matricula[:5] != b"%PDF-":
        raise ValueError("o arquivo da matrícula não é um PDF.")
    # O mesmo teto do contrato. Faltava aqui: a matrícula entrava sem limite,
    # e o servidor local guarda o arquivo inteiro em memória.
    if len(dados_matricula) > TAMANHO_MAXIMO:
        raise ValueError(f"matrícula maior que "
                         f"{TAMANHO_MAXIMO // (1024 * 1024)} MB.")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as arquivo:
        arquivo.write(dados_matricula)
        caminho = Path(arquivo.name)
    try:
        folio = mt.le(doc.abre(caminho).texto)
    finally:
        caminho.unlink(missing_ok=True)

    conferencia = qu.confere(ficha_de(ficha_em_json or {}), folio)

    return {
        "matricula": {
            "numero": folio.numero,
            "area": folio.area,
            "cep": folio.cep,
            "designacao_cadastral": folio.designacao_cadastral,
            "encerrada": folio.encerrada,
            "proprietarios": folio.proprietarios,
            "atos": [{"rotulo": a.rotulo, "titulo": a.titulo, "data": a.data}
                     for a in folio.atos],
            "onus": [a.rotulo for a in folio.onus_vigentes],
        },
        "exigencias": _exigencias_em_json(conferencia),
    }


def confere_de_texto(texto: str, ficha_em_json: dict) -> dict:
    """Mesma conferência, a partir do texto colado da matrícula."""
    from . import matricula as mt
    from . import qualificacao as qu

    folio = mt.le(texto or "")
    if not folio.numero and not folio.atos:
        raise ValueError("não reconheci uma matrícula no texto enviado.")

    conferencia = qu.confere(ficha_de(ficha_em_json or {}), folio)
    return {
        "matricula": {
            "numero": folio.numero, "area": folio.area, "cep": folio.cep,
            "designacao_cadastral": folio.designacao_cadastral,
            "encerrada": folio.encerrada, "proprietarios": folio.proprietarios,
            "atos": [{"rotulo": a.rotulo, "titulo": a.titulo, "data": a.data}
                     for a in folio.atos],
            "onus": [a.rotulo for a in folio.onus_vigentes],
        },
        "exigencias": _exigencias_em_json(conferencia),
    }
