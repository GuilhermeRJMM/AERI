"""Leitura de escrituras públicas e montagem dos rascunhos registrais.

O módulo de Minutas recebe duas famílias de títulos: os contratos CAIXA, já
tratados pelo núcleo histórico, e as escrituras públicas.  Esta unidade cuida
somente da segunda família.  O traslado continua sendo a fonte dos dados da
operação; a matrícula informa o estado atual e o catálogo da Tri7 fornece o
modelo institucional aplicável.

Nenhum rascunho é enviado à Tri7.  Ele fica identificado como rascunho até a
conferência humana do instrumento e do fólio.
"""

from __future__ import annotations

import copy
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.app.contratos_nucleo import matricula as leitor
from backend.app.contratos_nucleo.comparacao import areas_iguais, designativo
from backend.app.gerador_notas import documento as documento_docx
from backend.app.gerador_notas.redator import Bloco
from backend.app.gerador_notas.servico import MOLDE
from backend.app.servicos.analise_matricula import analisar_matricula


VERSAO = "20260909-escrituras-v2-itbi-ged"

ROTULOS_TRANSMITENTES = (
    "VENDEDOR", "VENDEDORA", "VENDEDORES", "VENDEDORAS",
    "DOADOR", "DOADORA", "DOADORES", "DOADORAS",
    "CEDENTE", "CEDENTES", "PERMUTANTE", "PERMUTANTES",
)
ROTULOS_ADQUIRENTES = (
    "COMPRADOR", "COMPRADORA", "COMPRADORES", "COMPRADORAS",
    "DONATÁRIO", "DONATÁRIA", "DONATÁRIOS", "DONATÁRIAS",
    "CESSIONÁRIO", "CESSIONÁRIA", "CESSIONÁRIOS", "CESSIONÁRIAS",
    "HERDEIRO", "HERDEIRA", "HERDEIROS", "HERDEIRAS",
    "ADJUDICATÁRIO", "ADJUDICATÁRIA", "ADJUDICATÁRIOS", "ADJUDICATÁRIAS",
    "PERMUTANTE", "PERMUTANTES",
)

NOMES_ESPECIES = {
    "VENDA_COMPRA": "Venda e compra",
    "DOACAO": "Doação",
    "INVENTARIO_PARTILHA": "Inventário e partilha",
    "PERMUTA": "Permuta",
    "CESSAO": "Cessão",
    "ADJUDICACAO": "Adjudicação",
    "OUTRA": "Escritura pública",
}

BUSCA_MODELO = {
    "VENDA_COMPRA": "VENDA E COMPRA - ESCRITURA 1º OFÍCIO",
    "DOACAO": "DOAÇÃO (PADRÃO)",
    "INVENTARIO_PARTILHA": "INVENTÁRIO/PARTILHA - EXTRAJUDICIAL",
    "PERMUTA": "PERMUTA",
    "CESSAO": "CESSÃO",
    "ADJUDICACAO": "ADJUDICAÇÃO (INVENTÁRIO)",
    "OUTRA": "",
}


def _sem_acento(valor: object) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", str(valor or ""))
        if not unicodedata.combining(c)
    )


def _chave(valor: object) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", _sem_acento(valor))).strip().upper()


def documentos_itbi_disponiveis(documentos: list[dict], *, exceto: object = None) -> list[dict]:
    """Devolve somente anexos que o usuário pode escolher como fonte de ITBI."""
    ignorado = str(exceto or "")
    saida = []
    for documento in documentos or []:
        if not isinstance(documento, dict):
            continue
        identificador = str(documento.get("ged_documento_id") or "")
        descricao = " ".join(str(documento.get(campo) or "") for campo in (
            "tipo_documento", "categoria", "descricao",
        ))
        chave = _chave(descricao)
        if not identificador or identificador == ignorado or "ITBI" not in chave:
            continue
        saida.append({
            "ged_documento_id": identificador,
            "tipo_documento": str(documento.get("tipo_documento") or "Guia de ITBI"),
            "categoria": str(documento.get("categoria") or ""),
            "descricao": str(documento.get("descricao") or ""),
            "versao": documento.get("versao"),
            "status_atual": str(documento.get("status_atual") or ""),
        })
    return saida


def eh_escritura_publica(texto: str) -> bool:
    chave = _chave(texto[:12_000])
    return "ESCRITURA PUBLICA" in chave or (
        "TRASLADO" in chave and "LIVRO DE ESCRITURA" in chave
    )


def classificar_especie(texto: str) -> str:
    cabecalho = _chave(texto[:12_000])
    if "INVENTARIO" in cabecalho or "PARTILHA" in cabecalho:
        return "INVENTARIO_PARTILHA"
    if "ADJUDICACAO" in cabecalho:
        return "ADJUDICACAO"
    if "DOACAO" in cabecalho:
        return "DOACAO"
    if "PERMUTA" in cabecalho:
        return "PERMUTA"
    if "CESSAO" in cabecalho:
        return "CESSAO"
    if "VENDA E COMPRA" in cabecalho or "COMPRA E VENDA" in cabecalho:
        return "VENDA_COMPRA"
    return "OUTRA"


def _limpar_texto(texto: str) -> str:
    """Retira rodapés repetidos sem corrigir fatos lidos pelo OCR."""
    ignorar = re.compile(
        r"^(?:Traslado|REP[ÚU]BLICA FEDERATIVA DO BRASIL|ESTADO DE GOI[ÁA]S|"
        r"Tabeli[aã]o e Registrador:|CNS:|Pedido:|Protocolo:|contato@|@|"
        r"Selo Digital|\(?64\)?\s*\d|P[áa]gina\s+\d)", re.I
    )
    linhas = []
    for linha in str(texto or "").replace("\r", "").splitlines():
        linha = re.sub(r"\s+", " ", linha).strip()
        if not linha or ignorar.search(linha):
            continue
        if re.fullmatch(r"[A-Za-z0-9\-]{0,2}", linha):
            continue
        linhas.append(linha)
    limpo = " ".join(linhas)
    limpo = re.sub(r"\bn\s*[.º°]?\s*0\b", "n.º", limpo, flags=re.I)
    limpo = re.sub(r"\s+", " ", limpo).strip()
    return limpo


def _primeiro(padrao: str, texto: str, flags=re.I | re.S) -> str:
    achado = re.search(padrao, texto, flags)
    return achado.group(1).strip(" ,;.-") if achado else ""


def _data_titulo(texto: str) -> str:
    valor = _primeiro(r"\bSAIBAM\b.{0,500}?\((\d{2}/\d{2}/\d{4})\)", texto)
    return valor.replace("/", ".")


def _cabecalho_livro_folhas(texto: str) -> tuple[str, str]:
    achado = re.search(
        r"Livro\s+de\s+Escritura\s+n?[.º°o]*\s*(\d+)\s*,\s*Folha\s+n?[.º°o]*\s*([^\n]+)",
        texto, re.I,
    )
    if not achado:
        return "", ""
    folhas = re.split(r"\bESCRITURA\b", achado.group(2), maxsplit=1, flags=re.I)[0]
    return achado.group(1).strip(), folhas.strip(" ,;.-")


def _tipo_do_titulo(texto: str, especie: str) -> str:
    titulo = _primeiro(r"\b(ESCRITURA\s+P[ÚU]BLICA\s+DE\s+[^\n]{3,100})", texto[:8_000])
    titulo = re.split(r"\bQUE\s+OUTORG", titulo, maxsplit=1, flags=re.I)[0].strip()
    return titulo or f"ESCRITURA PÚBLICA DE {NOMES_ESPECIES[especie].upper()}"


def _bloco_partes(texto: str, transmitentes: bool) -> str:
    # O cabeçalho repete "como vendedor/comprador" sem qualificação. Se o
    # regex partir dali, ele atravessa a escritura inteira e mistura CPF das
    # duas partes. A qualificação válida começa depois de "comparecem".
    ocorrencias = list(re.finditer(r"\bcomparecem\b", texto, re.I))
    if ocorrencias:
        texto = texto[ocorrencias[-1].start():]
    rotulos = ROTULOS_TRANSMITENTES if transmitentes else ROTULOS_ADQUIRENTES
    seguintes = ROTULOS_ADQUIRENTES if transmitentes else ()
    inicio = "|".join(map(re.escape, rotulos))
    if transmitentes:
        fim = "|".join(map(re.escape, seguintes))
        padrao = rf"\bcomo\s+(?:{inicio})\s*:\s*(.*?)(?=;?\s*e,?\s*como\s+(?:{fim})\s*:|\bReconhe[çc]o\b)"
    else:
        padrao = rf"\bcomo\s+(?:{inicio})\s*:\s*(.*?)(?=\bReconhe[çc]o\b|\bEnt[aã]o,?\s+(?:o|a|os|as)\b)"
    achados = list(re.finditer(padrao, texto, re.I | re.S))
    if not achados:
        return ""
    # A primeira ocorrência costuma ser o resumo do cabeçalho. A última é a
    # qualificação completa iniciada por "comparecem, como".
    valor = achados[-1].group(1)
    return re.sub(r"\s+", " ", valor).strip(" ,;.-")


def _nomes_do_resumo(texto: str, transmitentes: bool) -> str:
    antes = re.split(r"\bSAIBAM\b", texto, maxsplit=1, flags=re.I)[0]
    rotulos = ROTULOS_TRANSMITENTES if transmitentes else ROTULOS_ADQUIRENTES
    inicio = "|".join(map(re.escape, rotulos))
    if transmitentes:
        fim = "|".join(map(re.escape, ROTULOS_ADQUIRENTES))
        padrao = rf"(?:{inicio})\s*:\s*(.*?)(?=;?\s*E,?\s*COMO\s+(?:{fim})\s*:)"
    else:
        padrao = rf"(?:{inicio})\s*:\s*(.*?)(?=,?\s*NA\s+FORMA\s+ABAIXO|\.)"
    return re.sub(r"\s+", " ", _primeiro(padrao, antes)).strip()


def _documentos_partes(qualificacao: str) -> list[str]:
    if not qualificacao:
        return []
    # O documento formatado é uma âncora mais segura que "n.º": o OCR costuma
    # ler esse marcador como "n.0" e isso não pode comer o zero inicial do CPF.
    cnpjs = re.findall(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b", qualificacao)
    if cnpjs and re.search(r"pessoa\s+jur[íi]dica", qualificacao, re.I):
        return [cnpjs[0].rstrip(".,;")]
    return re.findall(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", qualificacao)


def _matriculas(texto: str) -> list[str]:
    resultados = []
    padroes = (
        r"objeto\s+da\s+matr[íi]cula\s+(?:n[úu]mero|n?[.º°o]*)?\s*([\d.]{1,12})",
        r"matriculad[oa]\s+sob\s+(?:o\s+)?(?:n[úu]mero|n?[.º°o]*)?\s*([\d.]{1,12})",
    )
    for padrao in padroes:
        for valor in re.findall(padrao, texto, re.I):
            numero = re.sub(r"\D", "", valor)
            if numero and numero not in resultados:
                resultados.append(numero)
    return resultados[:30]


def _objeto(texto: str) -> str:
    return _primeiro(
        r"\bOBJETO\s*:\s*(.*?)(?=\b(?:2|II)\s*[)\-]+\s*(?:PROCED|ORIGEM)|\bPROCED[ÊE]NCIA/ORIGEM\s*:)",
        texto,
    )


def _cep_imovel(objeto: str) -> str:
    valores = re.findall(r"\bCEP\s*n?[.º°o]*\s*(\d{2}\.?\d{3}-?\d{3})", objeto, re.I)
    return valores[-1] if valores else ""


def _cci_imovel(texto: str) -> str:
    trecho = _primeiro(r"\bOBJETO\s*:\s*(.*?)(?=\b3\s*[)\-]|\bDISPONIBILIDADE\s*:)", texto)
    return _primeiro(
        r"(?:CCI|c[óo]digo\s+(?:de\s+)?cadastro\s+(?:municipal|do\s+im[óo]vel)|"
        r"designa[çc][aã]o\s+cadastral)\s*n?[.º°o:]*\s*([\d.-]+)", trecho,
    )


def _valor_operacao(texto: str) -> str:
    trecho = _primeiro(
        r"\b(?:4\s*[)\-]\s*)?(?:PRE[ÇC]O\s+E\s+PAGAMENTO|VALOR)\s*:\s*(.*?)(?=\b5\s*[)\-]|\bTRANSMISS[ÃA]O|\bDOCUMENTOS\s+APRESENTADOS)",
        texto,
    )
    return _primeiro(r"R\$\s*([\d.]+,\d{2})", trecho)


def _itbi(texto: str) -> dict:
    trecho = _primeiro(
        r"IMPOSTO\s+SOBRE\s+A\s+TRANSMISS[ÃA]O\s+DE\s+BENS\s+IM[ÓO]VEIS\s*-?\s*ITBI\s*[:•.]\s*(.*?)(?=\b8\s*[)\-]|\bADVERT[ÊE]NCIAS|\bDECLARA[ÇC][ÕO]ES)",
        texto,
    )
    return {
        "base_calculo": _primeiro(r"Base\s+de\s+C[áa]lculo[^:]*:\s*R\$\s*([\d.]+,\d{2})", trecho),
        "data_quitacao": _primeiro(r"(?:Data\s+de\s+)?Recolhimento\s*:\s*(\d{2}/\d{2}/\d{4})", trecho).replace("/", "."),
        "duam": _primeiro(r"D[UI]AM\s*:\s*([\d./-]+)", trecho),
        "guia": _primeiro(r"Guia(?:\s+de\s+Informa[çc][aã]o\s+do\s+ITBI)?\s*n?[.º°o]*\s*([\d./-]+)", trecho),
        "valor_recolhido": _primeiro(r"Valor\s+(?:Pago|Recolhido)\s*:\s*R\$\s*([\d.]+,\d{2})", trecho),
    }


def _primeiro_de(padroes: tuple[str, ...], texto: str) -> str:
    for padrao in padroes:
        achado = re.search(padrao, texto, re.I | re.S)
        if achado:
            return re.sub(r"\s+", " ", achado.group(1)).strip(" .;:-")
    return ""


def extrair_guia_itbi(documento: dict) -> dict:
    """Extrai somente dados fiscais comprovados pelo anexo selecionado.

    O valor do negócio e a área servem para conferência, mas nunca são
    promovidos silenciosamente a base de cálculo. Guia sem avaliação ou sem
    DUAM continua incompleta, como ocorre no protocolo 185.925.
    """
    texto = str((documento or {}).get("texto") or "")
    if "ITBI" not in _chave(texto):
        raise ValueError("O documento selecionado não foi reconhecido como guia de ITBI.")

    valor = r"([\d.]+,\d{2})"
    numero = r"([\d./-]{2,30})"
    campos = {
        "guia": _primeiro_de((
            rf"Guia\s+de\s+(?:Informa[^\n:]{{0,35}}|Lan[^\n:]{{0,45}})\s+n\s*[.º°o]*\s*{numero}",
            rf"Guia\s+n\s*[.º°o]*\s*{numero}",
        ), texto),
        "base_calculo": _primeiro_de((
            rf"Base\s+de\s+C[^\n:]{{0,35}}:\s*R\$\s*{valor}",
            rf"Im[oó]vel\s+Avaliado\s+em\s*R\$\s*{valor}",
        ), texto),
        "duam": _primeiro_de((
            rf"D[UI]AM\s+n\s*[.º°o]*\s*{numero}",
            rf"D[UI]AM\s*:\s*{numero}",
        ), texto),
        "valor_recolhido": _primeiro_de((
            rf"Valor\s+(?:Recolhido|Pago)\s*:\s*R\$\s*{valor}",
            rf"VALOR\s+A\s+RECOLHER\s*:\s*R\$\s*{valor}",
        ), texto),
        "data_quitacao": _primeiro_de((
            r"(?:quitad[ao]|recolhimento)\s+(?:em|:)\s*(\d{2}/\d{2}/\d{4})",
            r"Data\s+de\s+(?:Pagamento|Quita[çc][aã]o)\s*:\s*(\d{2}/\d{2}/\d{4})",
        ), texto).replace("/", "."),
    }
    conferencia = {
        "matricula": _primeiro_de((
            r"Matr[íi�]cula\s+n\s*[.º°o�]*\s*([\d.]+)",
            r"N[uú�]mero\s+do\s+registro\s*:\s*(?:Matr[íi�]cula\s+n\s*[.º°o�]*\s*)?([\d.]+)",
        ), texto),
        "valor_negocio": _primeiro_de((
            rf"Valor\s+do\s+Neg[oó�]cio\s+Jur[íi�]dico\s*:.{{0,80}}?R\$\s*{valor}",
        ), texto),
        "area": _primeiro_de((
            r"[ÁA�]rea\s+total\s*\(ha/m[²2�]\)\s*:.{0,180}?\b([\d.,]+\s*(?:ha|m[²2�]))",
        ), texto),
        "parte_ideal": _primeiro_de((
            r"Parte\s+Ideal\s*:.{0,180}?\b([\d.,]+\s*%)",
        ), texto),
    }
    vazios = [
        rotulo for campo, rotulo in (
            ("guia", "número da guia"), ("base_calculo", "base de cálculo"),
            ("duam", "DUAM"), ("valor_recolhido", "valor do imposto"),
            ("data_quitacao", "data de quitação"),
        ) if not campos[campo]
    ]
    alertas = []
    if vazios:
        alertas.append(
            "O anexo não comprova " + ", ".join(vazios) +
            "; esses campos permanecerão para conferência na Tri7."
        )
    return {
        "campos": campos,
        "conferencia": conferencia,
        "alertas": alertas,
        "sha256": str(documento.get("sha256") or ""),
        "ocr": bool(documento.get("ocr")),
    }


def anexar_guia_itbi(payload: dict, resultado: dict, metadados: dict) -> dict:
    """Vincula a guia escolhida sem trocar dados do título por valores vazios."""
    if payload.get("tipoDocumento") != "ESCRITURA_PUBLICA":
        raise ValueError("A guia de ITBI complementar está disponível para escrituras públicas.")
    ficha = payload.get("ficha") or {}
    matriculas = {
        re.sub(r"\D", "", str(numero)) for numero in ficha.get("matriculas", [])
        if re.sub(r"\D", "", str(numero))
    }
    matricula_guia = re.sub(
        r"\D", "", str((resultado.get("conferencia") or {}).get("matricula") or "")
    )
    if matricula_guia and matriculas and matricula_guia not in matriculas:
        raise ValueError("A matrícula informada na guia de ITBI não corresponde à escritura selecionada.")

    campos = resultado.get("campos") or {}
    destino = ficha.setdefault("valores", {}).setdefault("itbi", {})
    original = payload.setdefault("fichaOriginal", copy.deepcopy(ficha))
    destino_original = original.setdefault("valores", {}).setdefault("itbi", {})
    aplicados = {}
    for campo in ("data_quitacao", "base_calculo", "duam", "guia", "valor_recolhido"):
        valor = str(campos.get(campo) or "").strip()
        if valor:
            destino[campo] = valor
            destino_original[campo] = valor
            aplicados[campo] = valor

    alertas = list(resultado.get("alertas") or [])
    valor_guia = str((resultado.get("conferencia") or {}).get("valor_negocio") or "")
    valor_titulo = str(ficha.get("valores", {}).get("operacao") or "")
    numeros = lambda valor: re.sub(r"\D", "", valor or "").lstrip("0")
    if valor_guia and valor_titulo and numeros(valor_guia) != numeros(valor_titulo):
        alertas.append(
            f"O valor do negócio na guia (R${valor_guia}) diverge do título (R${valor_titulo})."
        )

    complemento = payload.setdefault("documentosComplementares", {})
    complemento["itbiSelecionado"] = {
        "ged_documento_id": str(metadados.get("ged_documento_id") or ""),
        "tipo_documento": str(metadados.get("tipo_documento") or "Guia de ITBI"),
        "descricao": str(metadados.get("descricao") or ""),
        "status_atual": str(metadados.get("status_atual") or ""),
        "camposAplicados": aplicados,
        "conferencia": resultado.get("conferencia") or {},
        "alertas": alertas,
        "sha256": str(resultado.get("sha256") or ""),
    }
    # Qualquer conferência anterior ficou desatualizada depois da nova fonte.
    for chave in ("confronto", "decisoes", "minutas", "minutasFinais", "fichaGerada", "requerimentos"):
        payload.pop(chave, None)
    payload["minutasPrevia"] = gerar_minutas(payload, ficha)
    return payload


def extrair(documento: dict) -> dict:
    original = documento["texto"]
    texto = _limpar_texto(original)
    especie = classificar_especie(texto)
    livro, folhas = _cabecalho_livro_folhas(original)
    transmitentes = _bloco_partes(texto, True)
    adquirentes = _bloco_partes(texto, False)
    objeto = _objeto(texto)
    matriculas = _matriculas(texto)
    ficha = {
        "titulo": {
            "especie": NOMES_ESPECIES[especie],
            "descricao": _tipo_do_titulo(original, especie),
            "data": _data_titulo(texto),
            "livro": livro,
            "folhas": folhas,
            "serventia": "Cartório do 1º Ofício de Notas e Registro de Imóveis da Comarca de Morrinhos-GO",
        },
        "matriculas": matriculas,
        "transmitentes": {
            "nomes": _nomes_do_resumo(texto, True),
            "qualificacao": transmitentes,
            "documentos": _documentos_partes(transmitentes),
        },
        "adquirentes": {
            "nomes": _nomes_do_resumo(texto, False),
            "qualificacao": adquirentes,
            "documentos": _documentos_partes(adquirentes),
        },
        "imovel": {
            "descricao": objeto,
            "cep": _cep_imovel(objeto),
            "cci": _cci_imovel(texto),
        },
        "valores": {
            "operacao": _valor_operacao(texto),
            "itbi": _itbi(texto),
        },
        "pedidos": {
            "cancelamento_alienacao": bool(re.search(
                r"(?:requer\w*.{0,180}?cancel\w*.{0,80}?aliena[çc][aã]o\s+fiduci[áa]ria|"
                r"autoriza[çc][aã]o\s+para\s+cancelamento\s+da\s+propriedade\s+fiduci[áa]ria)",
                texto, re.I | re.S,
            )),
        },
        "origens": {"_natureza": "escritura pública digitalizada · OCR" if documento.get("ocr") else "escritura pública nato-digital"},
        "brutos": {"imovel": objeto},
    }
    alertas = []
    if not matriculas:
        alertas.append({"campo": "Matrícula", "motivo": "Número não identificado com segurança no traslado."})
    if not livro or not folhas or not ficha["titulo"]["data"]:
        alertas.append({"campo": "Forma do título", "motivo": "Confira data, livro e folhas da escritura."})
    if not transmitentes or not adquirentes:
        alertas.append({"campo": "Partes", "motivo": "A qualificação completa de uma das partes não foi delimitada automaticamente."})
    if documento.get("ocr"):
        alertas.append({"campo": "Traslado", "motivo": "Documento lido por OCR local: confira nomes, documentos, valores, datas, livro e folhas no original."})
    evidencias = {
        "titulo": {"paginas": [1], "origem": "Cabeçalho da escritura"},
        "transmitentes": {"paginas": [1], "origem": "Qualificação do traslado"},
        "adquirentes": {"paginas": [1], "origem": "Qualificação do traslado"},
        "imovel": {"paginas": [], "origem": "Cláusula OBJETO"},
        "valores": {"paginas": [], "origem": "Preço, pagamento e ITBI"},
    }
    return {
        "documento": documento,
        "tipoDocumento": "ESCRITURA_PUBLICA",
        "especie": especie,
        "fichaOriginal": copy.deepcopy(ficha),
        "ficha": ficha,
        "gruposFicha": [
            ["titulo", "Título público"], ["transmitentes", "Transmitentes"],
            ["adquirentes", "Adquirentes"], ["matriculas", "Matrículas"],
            ["imovel", "Imóvel descrito"], ["valores", "Valores e ITBI"],
        ],
        "alertasExtracao": alertas,
        "evidencias": evidencias,
        "modeloTri7Busca": BUSCA_MODELO[especie],
    }


def _valor_imovel(analise: dict, rotulo: str) -> str:
    alvo = _chave(rotulo)
    for grupo in analise.get("imovel", {}).values():
        if not isinstance(grupo, list):
            continue
        for item in grupo:
            if isinstance(item, dict) and _chave(item.get("rotulo")) == alvo:
                valor = str(item.get("valor") or "")
                return "" if valor == "NÃO CONSTA" else valor
    return ""


def _documentos_normalizados(valores) -> set[str]:
    return {re.sub(r"\D", "", str(v)) for v in valores or [] if len(re.sub(r"\D", "", str(v))) in {11, 14}}


def _nomes_compativeis(declarado: str, atuais: list[dict]) -> bool:
    chave = _chave(declarado).replace(" E SEU CONJUGE", "")
    if not chave:
        return False
    return any(_chave(item.get("nome")) in chave or chave in _chave(item.get("nome")) for item in atuais)


def confrontar(payload: dict, texto_matricula: str, numero: str, regras=None) -> dict:
    analise = analisar_matricula(
        texto_matricula, regras_aprendidas=regras, numero_matricula=str(numero)
    )
    folio = leitor.le(texto_matricula)
    ficha = payload["ficha"]
    comparacoes = []

    def linha(campo, titulo, matricula, compativel, permite=False):
        comparacoes.append({
            "campo": campo,
            "contrato": titulo or "NÃO CONSTA",
            "matricula": matricula or "NÃO CONSTA",
            "situacao": "COMPATIVEL" if compativel else "REVISAR",
            "permiteMatricula": bool(permite and matricula),
            "somenteConferencia": not permite,
        })

    nums = [re.sub(r"\D", "", str(v)) for v in ficha.get("matriculas", [])]
    linha("matriculas.0", nums[0] if nums else "", numero, numero in nums, True)

    atuais = analise.get("proprietarios_atuais", [])
    docs_titulo = _documentos_normalizados(ficha.get("transmitentes", {}).get("documentos"))
    docs_folio = _documentos_normalizados(
        p.get("cpf_cnpj") or p.get("cpf") for p in atuais
    )
    compativel_partes = bool(docs_titulo & docs_folio) if docs_titulo and docs_folio else _nomes_compativeis(
        ficha.get("transmitentes", {}).get("nomes", ""), atuais
    )
    linha(
        "transmitentes.nomes",
        ficha.get("transmitentes", {}).get("nomes", ""),
        "; ".join(p.get("nome", "") for p in atuais),
        compativel_partes,
    )

    objeto = leitor.le("IMÓVEL: " + ficha.get("imovel", {}).get("descricao", ""))
    for campo, titulo, matricula in (
        ("imovel.area", objeto.area, folio.area),
        ("imovel.lote", objeto.lote_quadra[0], folio.lote_quadra[0]),
        ("imovel.quadra", objeto.lote_quadra[1], folio.lote_quadra[1]),
    ):
        if campo == "imovel.area":
            compativel = areas_iguais(titulo, matricula)
        elif campo in {"imovel.lote", "imovel.quadra"}:
            compativel = bool(titulo and matricula and designativo(titulo) == designativo(matricula))
        else:
            compativel = bool(titulo and matricula and _chave(titulo) == _chave(matricula))
        linha(campo, titulo, matricula, compativel)

    cep_titulo = ficha.get("imovel", {}).get("cep", "")
    cci_titulo = ficha.get("imovel", {}).get("cci", "")
    cep_folio = _valor_imovel(analise, "CEP") or folio.cep
    cci_folio = _valor_imovel(analise, "Cadastro municipal / CCI") or folio.designacao_cadastral

    def igual_numero(a, b):
        return bool(a and b and re.sub(r"\D", "", a) == re.sub(r"\D", "", b))

    if cep_titulo:
        linha("imovel.cep", cep_titulo, cep_folio, igual_numero(cep_titulo, cep_folio))
    if cci_titulo:
        linha("imovel.cci", cci_titulo, cci_folio, igual_numero(cci_titulo, cci_folio))

    transmissoes = [ato for ato in folio.atos if ato.eh_transmissao]
    origem = f"O {transmissoes[-1].rotulo} desta matrícula" if transmissoes else "Abertura da presente matrícula"
    alienacoes = [
        ato for ato in folio.onus_vigentes
        if "ALIENACAO FIDUCIARIA" in _chave(ato.titulo)
    ]
    auxiliares = {
        "cep": bool(cep_titulo and not igual_numero(cep_titulo, cep_folio)),
        "cci": bool(cci_titulo and not igual_numero(cci_titulo, cci_folio)),
        "cancelamento_alienacao": bool(
            ficha.get("pedidos", {}).get("cancelamento_alienacao") and alienacoes
        ),
        "alienacao_ato": alienacoes[-1].rotulo if alienacoes else "",
    }
    exigencias = []
    if auxiliares["cep"]:
        exigencias.append({"numero": len(exigencias)+1, "titulo": "Averbação do CEP", "detalhe": "O traslado informa CEP que ainda não consta, ou diverge, no texto atual da matrícula.", "fundamento": "Art. 440-AV, parágrafo único, do Provimento CNJ n.º 149/2023.", "grau": "ATENCAO"})
    if auxiliares["cci"]:
        exigencias.append({"numero": len(exigencias)+1, "titulo": "Atualização da designação cadastral", "detalhe": "O traslado informa CCI que ainda não consta, ou diverge, no texto atual da matrícula.", "fundamento": "Art. 176, §1º, II, 3, b, c/c art. 246 da Lei n.º 6.015/1973.", "grau": "ATENCAO"})
    if auxiliares["cancelamento_alienacao"]:
        exigencias.append({"numero": len(exigencias)+1, "titulo": "Cancelamento de alienação fiduciária", "detalhe": f"O título contém pedido/autorização de cancelamento e a matrícula mantém {auxiliares['alienacao_ato']} ativo.", "fundamento": "Art. 250, III, da Lei n.º 6.015/1973.", "grau": "ATENCAO"})

    return {
        "numero": str(numero), "versaoRegras": VERSAO, "analise": analise,
        "comparacoes": comparacoes, "exigencias": exigencias,
        "contexto": {"origem": origem, "cepAtual": cep_folio, "cciAtual": cci_folio},
        "auxiliares": auxiliares,
    }


def normalizar_ficha(ficha: dict) -> dict:
    if not isinstance(ficha, dict):
        raise ValueError("Ficha da escritura inválida.")
    # Mantém somente estrutura JSON e impõe limites antes de cifrar/persistir.
    def limpar(valor, profundidade=0):
        if profundidade > 8:
            raise ValueError("Ficha da escritura excede a profundidade permitida.")
        if isinstance(valor, dict):
            if len(valor) > 100:
                raise ValueError("Ficha da escritura possui campos demais.")
            return {str(k)[:100]: limpar(v, profundidade+1) for k, v in valor.items()}
        if isinstance(valor, list):
            if len(valor) > 100:
                raise ValueError("Ficha da escritura possui itens demais.")
            return [limpar(v, profundidade+1) for v in valor]
        if isinstance(valor, bool) or valor is None:
            return valor
        if isinstance(valor, (int, float)):
            return valor
        if isinstance(valor, str):
            if len(valor) > 100_000:
                raise ValueError("Campo textual da escritura excede o limite.")
            return valor
        raise ValueError("Ficha da escritura contém um valor inválido.")
    return limpar(ficha)


def aplicar_decisoes(payload: dict, ficha: dict, decisoes: dict, conferida: bool):
    nova = normalizar_ficha(ficha)
    if nova != payload.get("ficha"):
        raise ValueError("A ficha foi editada. Confronte a matrícula novamente antes de gerar.")
    if conferida is not True or not isinstance(decisoes, dict):
        raise ValueError("Confirme a conferência da extração.")
    aplicadas = []
    for comparacao in payload["confronto"]["comparacoes"]:
        decisao = decisoes.get(comparacao["campo"])
        if decisao is None and comparacao["situacao"] == "COMPATIVEL":
            continue
        if not isinstance(decisao, dict) or decisao.get("acao") not in {"CONTRATO", "MATRICULA", "MANUAL"}:
            raise ValueError(f"Registre uma decisão para o campo pendente: {comparacao['campo']}.")
        justificativa = decisao.get("justificativa")
        if not isinstance(justificativa, str) or not justificativa.strip() or len(justificativa) > 2000:
            raise ValueError(f"Informe a justificativa da decisão: {comparacao['campo']}.")
        # Em escritura, a matrícula nunca substitui silenciosamente os dados do
        # novo título. A escolha serve como decisão documentada da conferência.
        aplicadas.append({"campo": comparacao["campo"], **decisao, "somenteConferencia": True})
    return nova, aplicadas


def _forma_titulo(ficha: dict) -> str:
    titulo = ficha.get("titulo", {})
    return (
        f"{titulo.get('descricao') or 'Escritura Pública'}, lavrada em "
        f"{titulo.get('data') or '[[data da escritura]]'}, às fls. "
        f"{titulo.get('folhas') or '[[folhas]]'}, Livro "
        f"{titulo.get('livro') or '[[livro]]'}, pelo "
        f"{titulo.get('serventia') or '[[serventia]]'}"
    )


def _nota_itbi(ficha: dict, *, anexo_ged: bool = False) -> str:
    itbi = ficha.get("valores", {}).get("itbi", {})
    data = itbi.get("data_quitacao") or "de  de"
    base = itbi.get("base_calculo") or "Valor•avaliacao•imovel•itbi«a»"
    duam = itbi.get("duam") or "Numero•duam•itbi«a»"
    guia = itbi.get("guia") or "Numero•protocolo•itbi«a»"
    valor = itbi.get("valor_recolhido") or "Valor•recolhido•itbi«a»"
    completos = all(itbi.get(c) for c in (
        "data_quitacao", "base_calculo", "duam", "guia", "valor_recolhido"
    ))
    if anexo_ged and completos:
        return (
            "foram apresentadas a Guia de Lançamento e Pagamento do Imposto "
            f"Sobre Transmissão de Bens Imóveis de n.º {guia}, constando avaliação "
            f"do imóvel em R${base}; e, Certidão de Quitação de DUAM n.º {duam}, "
            f"no valor de R${valor}, quitada em {data}"
        )
    return (
        "Constou da escritura o recolhimento do Imposto Sobre a Transmissão de "
        f"Bens Imóveis ITBI em data de {data}; Base de cálculo: R${base}; "
        f"Duam: {duam}; Guia n.º {guia}; Valor recolhido: R${valor}"
    )


def _minuta_principal(ficha: dict, confronto: dict, modelo: dict | None,
                      *, itbi_ged: bool = False) -> dict:
    especie = ficha.get("titulo", {}).get("especie", "Escritura pública")
    if _chave(especie) not in {"VENDA E COMPRA", "COMPRA E VENDA"}:
        texto_modelo = str((modelo or {}).get("texto") or "").strip()
        texto = texto_modelo or (
            f"{especie.upper()}. [[O modelo desta espécie deve ser selecionado e "
            "completado na Tri7 após a conferência do traslado e da matrícula.]]"
        )
        return {"texto": texto, "pendencias": [{"campo": "modelo", "motivo": "Confira e complete os campos variáveis do modelo da Tri7.", "grau": "CONFIRIR", "sugestao": ""}]}

    numero = _numero_formatado(confronto.get("numero") or (ficha.get("matriculas") or [""])[0])
    data_ato = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d.%m.%Y")
    forma = _forma_titulo(ficha)
    texto = (
        f"Tipo•ato•ficha«a».Numero•ato•f«a»-{numero} - Data: {data_ato}. "
        "Protocolo n.º Numero•ordem•prot«a», de ... VENDA E COMPRA. "
        "TRANSMITENTE(S): Qualificacao•vendedor•i«a»; SE PJ (preencher os campos "
        "referentes à representação) no ato representada por REPRESENTANTES_CTRL_Q«m», "
        "nos termos do (Contrato Social ou xx Alteração do Contrato Social) datado de "
        "xx.xx.xxxx«m», devidamente registrado na JUCEG em xx.xx.xxxx«m», sob o n.º "
        "xxxxxxxxxx«m», Nire xxxxxxxxx«m»; (Se houver procurador: nos termos da "
        "Procuração lavrada em xx.xx.xxxx«m», às fls.xxx«m», Livro xxx«m», pelo "
        "Cartório xxxxxxxxxxxxxxx«m»). ADQUIRENTE(S): Qualificacao•proprietario•i«a»; "
        "SE PJ (preencher os campos referentes à representação) no ato representada por "
        "REPRESENTANTES_CTRL_Q«m», nos termos do (Contrato Social ou xx Alteração do "
        "Contrato Social) datado de xx.xx.xxxx«m», devidamente registrado na JUCEG em "
        "xx.xx.xxxx«m», sob o n.º xxxxxxxxxx«m», Nire xxxxxxxxx«m»; (Se houver "
        "procurador: nos termos da Procuração lavrada em xx.xx.xxxx«m», às fls.xxx«m», "
        "Livro xxx«m», pelo Cartório xxxxxxxxxxxxxxx«m»). IMÓVEL: xx«m»% do imóvel "
        "descrito na matrícula, (SE RURAL ACRESCENTAR: equivalente a xx,xxxx«m»ha). "
        "ORIGEM: (SELECIONAR: Origem - Ctrl+T)«m». "
        f"FORMA DO TÍTULO: {forma}. "
        "VALOR: (SELECIONAR: Forma de Pagamento - Ctrl+T)«m». "
        f"*NOTAS: I)- {_nota_itbi(ficha, anexo_ged=itbi_ged)}; "
        "II)- (SE RURAL ACRESCENTAR: (SELECIONAR: Notas-Livro 02 - ITR - Ctrl+T)«m»); "
        "e, III)- (SELECIONAR: Notas-Livro 02 - Abono Recolhimento - Ctrl+T)«m». "
        "DOU FÉ. Selo: . Cotação do ato: emolumentos: R$; ISSQN: R$; taxa judiciária: "
        "R$; ; Total: R$. Morrinhos-GO, de  de. Oficial: /xxxxx/xxxxx/"
    )
    pendencias = []
    if any(marcador in texto for marcador in ("xx«,", "xx«", "Numero•", "Valor•", "SELECIONAR:")):
        pendencias.append({"campo": "minuta principal", "motivo": "Há seleções e campos variáveis que precisam ser completados na Tri7.", "grau": "CONFERIR", "sugestao": ""})
    return {"texto": texto, "pendencias": pendencias}


def _numero_formatado(numero: object) -> str:
    digitos = re.sub(r"\D", "", str(numero or ""))
    return f"{int(digitos):,}".replace(",", ".") if digitos else "xx.xxx«m»"


def _minuta_cep(ficha: dict, numero="") -> dict:
    cep = ficha.get("imovel", {}).get("cep") or "xx.xxx-xxx«m»"
    return {"texto": (
        f"Tipo•ato•ficha«a».Numero•ato•f«a»-{_numero_formatado(numero)} - Data: {datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%d.%m.%Y')}. "
        "Protocolo n.º Numero•ordem•prot«a», de ... CÓDIGO DE ENDEREÇAMENTO POSTAL. "
        "Nos termos do requerimento firmado pelo(a) interessado(a) em data de "
        f"xx.xx.xxxx«m», procede-se a esta averbação com base no art.440-AV, parágrafo único, do Provimento n.º 149/2023 do Conselho Nacional de Justiça, para constar que o imóvel objeto da presente matrícula possui o seguinte Código de Endereçamento Postal - CEP n.º {cep}. DOU FÉ."
    ), "pendencias": []}


def _minuta_cci(ficha: dict, numero="") -> dict:
    cci = ficha.get("imovel", {}).get("cci") or "xxx.xxx«m»"
    return {"texto": (
        f"Tipo•ato•ficha«a».Numero•ato•f«a»-{_numero_formatado(numero)} - Data: {datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%d.%m.%Y')}. "
        "Protocolo n.º Numero•ordem•prot«a», de ... ATUALIZAÇÃO DE DESIGNAÇÃO CADASTRAL DO IMÓVEL. "
        "Nos termos do requerimento do(a) interessado(a) datado de xx.xx.xxxx«m», que se fez acompanhar de Boletim Cadastro Imobiliário - BCI expedido em xx.xx.xxxx«m» pelo Município de Morrinhos-GO, através da Secretaria Municipal de Fazenda e Administração, procede-se a esta averbação com base no art.176, §1º, inciso II, item 3, alínea “b”, c/c art.246 da Lei Federal n.º 6.015/1973, para constar que o imóvel objeto da presente matrícula atualmente possui o seguinte código cadastral na Prefeitura Municipal de Morrinhos-GO: "
        f"CCI n.º {cci}. DOU FÉ."
    ), "pendencias": []}


def _minuta_cancelamento(ficha: dict, confronto: dict) -> dict:
    ato = confronto.get("auxiliares", {}).get("alienacao_ato") or "R.xx«m»"
    return {"texto": (
        f"Tipo•ato•ficha«a».Numero•ato•f«a»-{_numero_formatado(confronto.get('numero'))} - Data: {datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%d.%m.%Y')}. "
        "Protocolo n.º Numero•ordem•prot«a», de ... CANCELAMENTO DE ALIENAÇÃO FIDUCIÁRIA. "
        "Nos termos do Contrato xxxxxxxxxxxxxxxxxxxxx«m» n.º xxxxxxxxxxxxx«m», datado de xx.xx.xxxx«m», onde consta, em seu item xx«m», a Autorização para Cancelamento da Propriedade Fiduciária, concedida pela credora xxxxxxxxx«m», CNPJ/MF n.º xx.xxx.xxx/xxxx-xx«m», através de sua(eu) representante legal xxxxxxxxxxxxx«m» - Gerente xxxxxx«m» - Matr. xxxxxx-x«m», e de acordo com o disposto no art. 250, III, da Lei Federal n.º 6.015/1973, procede-se a presente averbação para constar que fica CANCELADA A ALIENAÇÃO FIDUCIÁRIA constante do "
        f"{ato} desta matrícula. DOU FÉ."
    ), "pendencias": [{"campo": "cancelamento", "motivo": "Confira autorização, credora, representantes, contrato, item e data no documento apresentado.", "grau": "CONFERIR", "sugestao": ""}]}


def gerar_minutas(payload: dict, ficha: dict | None = None) -> dict:
    ficha = normalizar_ficha(ficha or payload.get("ficha") or {})
    confronto = payload.get("confronto") or {}
    modelo = payload.get("modeloTri7")
    itbi_ged = bool((payload.get("documentosComplementares") or {}).get("itbiSelecionado"))
    saida = {"principal": _minuta_principal(ficha, confronto, modelo, itbi_ged=itbi_ged)}
    auxiliares = confronto.get("auxiliares", {})
    if auxiliares.get("cep"):
        saida["cep"] = _minuta_cep(ficha, confronto.get("numero"))
    if auxiliares.get("cci"):
        saida["cci"] = _minuta_cci(ficha, confronto.get("numero"))
    if auxiliares.get("cancelamento_alienacao"):
        saida["cancelamento_alienacao"] = _minuta_cancelamento(ficha, confronto)
    return saida


def preparar_auxiliares_contrato(payload: dict) -> None:
    """Converte pendências já apuradas no contrato em rascunhos auxiliares.

    Não procura palavras soltas na matrícula. CEP/CCI vêm das exigências do
    confronto; cancelamento exige simultaneamente autorização no documento e
    alienação fiduciária ativa na análise registral.
    """
    confronto = payload.get("confronto") or {}
    titulos = " ".join(_chave(item.get("titulo")) for item in confronto.get("exigencias", []))
    texto = str((payload.get("documento") or {}).get("texto") or "")
    atos = (confronto.get("analise") or {}).get("atos") or []
    alienacoes = [
        ato for ato in atos if isinstance(ato, dict) and ato.get("status") == "ATIVO"
        and "ALIENACAO FIDUCIARIA" in _chave(
            ato.get("tipo_onus") or ato.get("categoria") or ato.get("descricao"))
    ]
    autorizacao = bool(re.search(
        r"(?:autoriza[çc][aã]o|autoriza\w*|requer\w*).{0,220}?"
        r"cancel\w*.{0,120}?aliena[çc][aã]o\s+fiduci[áa]ria",
        texto, re.I | re.S,
    ))
    bruto = str((payload.get("ficha") or {}).get("brutos", {}).get("imovel") or "")
    auxiliares = {
        "cep": "CEP NAO AVERBADO" in titulos,
        "cci": "DESIGNACAO CADASTRAL NAO AVERBADA" in titulos,
        "cancelamento_alienacao": bool(autorizacao and alienacoes),
        "alienacao_ato": str((alienacoes[-1] if alienacoes else {}).get("codigo") or ""),
        "cep_valor": _cep_imovel(bruto),
        "cci_valor": _cci_imovel("OBJETO: " + bruto + " DISPONIBILIDADE:"),
    }
    confronto["auxiliares"] = auxiliares
    payload["requerimentos"] = requerimentos_disponiveis(payload)


def gerar_minutas_auxiliares(payload: dict) -> dict:
    auxiliares = (payload.get("confronto") or {}).get("auxiliares", {})
    ficha = {
        "imovel": {
            "cep": auxiliares.get("cep_valor") or "",
            "cci": auxiliares.get("cci_valor") or "",
        }
    }
    saida = {}
    if auxiliares.get("cep"):
        saida["cep"] = _minuta_cep(ficha, (payload.get("confronto") or {}).get("numero"))
    if auxiliares.get("cci"):
        saida["cci"] = _minuta_cci(ficha, (payload.get("confronto") or {}).get("numero"))
    if auxiliares.get("cancelamento_alienacao"):
        saida["cancelamento_alienacao"] = _minuta_cancelamento(ficha, payload["confronto"])
    return saida


def requerimentos_disponiveis(payload: dict) -> list[dict]:
    auxiliares = (payload.get("confronto") or {}).get("auxiliares", {})
    cep, cci = bool(auxiliares.get("cep")), bool(auxiliares.get("cci"))
    if cep and cci:
        return [{"tipo": "cep-cci", "rotulo": "Baixar requerimento de CEP e CCI"}]
    saida = []
    if cep:
        saida.append({"tipo": "cep", "rotulo": "Baixar requerimento de CEP"})
    if cci:
        saida.append({"tipo": "cci", "rotulo": "Baixar requerimento de CCI"})
    return saida


def _paragrafo(texto: str, *, negrito=False) -> Bloco:
    return Bloco("corpo", [(texto, {"negrito"} if negrito else set())])


def gerar_requerimento_docx(payload: dict, tipo: str) -> tuple[str, bytes]:
    if tipo not in {"cep", "cci", "cep-cci"}:
        raise ValueError("Tipo de requerimento inválido.")
    permitidos = {item["tipo"] for item in requerimentos_disponiveis(payload)}
    if tipo not in permitidos:
        raise ValueError("Este requerimento não corresponde às pendências atuais.")
    ficha = payload.get("fichaGerada") or payload.get("ficha") or {}
    matriculas = ficha.get("matriculas") or [ficha.get("matricula", {}).get("numero")]
    matricula = str(matriculas[0]) if matriculas and matriculas[0] else str((payload.get("confronto") or {}).get("numero") or "[[MATRÍCULA]]")
    auxiliares = (payload.get("confronto") or {}).get("auxiliares", {})
    cep = ficha.get("imovel", {}).get("cep") or auxiliares.get("cep_valor") or "[[CEP]]"
    cci = ficha.get("imovel", {}).get("cci") or auxiliares.get("cci_valor") or "[[CCI]]"
    if payload.get("tipoDocumento") == "ESCRITURA_PUBLICA":
        interessado = ficha.get("transmitentes", {}).get("qualificacao") or "[[QUALIFICAÇÃO DO(A) INTERESSADO(A)]]"
        nome = ficha.get("transmitentes", {}).get("nomes") or "[[NOME DO(A) INTERESSADO(A)]]"
    else:
        partes = ficha.get("vendedores") or ficha.get("compradores") or []
        primeira = partes[0] if partes else {}
        nome = primeira.get("nome") or primeira.get("razao_social") or "[[NOME DO(A) INTERESSADO(A)]]"
        interessado = nome + ", [[QUALIFICAÇÃO DO(A) INTERESSADO(A)]]"
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y")

    pedidos = []
    if tipo in {"cep", "cep-cci"}:
        pedidos.append(f"a averbação do Código de Endereçamento Postal - CEP n.º {cep}")
    if tipo in {"cci", "cep-cci"}:
        pedidos.append(f"a atualização da designação cadastral do imóvel para CCI n.º {cci}")
    pedido = pedidos[0] if len(pedidos) == 1 else pedidos[0] + "; e, " + pedidos[1]
    texto = (
        f"{interessado}; vem à presença de V.S.ª requerer {pedido}, à margem da "
        f"matrícula n.º {matricula} desta Serventia Registral, conforme documentação anexa."
    )
    blocos = [
        _paragrafo("ILUSTRÍSSIMO SENHOR OFICIAL DO CARTÓRIO DO 1.º OFÍCIO DE NOTAS E DE REGISTRO DE IMÓVEIS DA COMARCA DE MORRINHOS-GO", negrito=True),
        Bloco("vazio", [("", set())]),
        _paragrafo(texto),
        _paragrafo("Nesta oportunidade, autoriza o Oficial da atribuição de Registro de Imóveis a proceder, na matrícula indicada, às demais averbações necessárias ao regular seguimento do serviço solicitado."),
        _paragrafo("Em observância ao art. 4.º, § 2.º, do Provimento CNJ n.º 61/2017, declara que desconhece ou não possui os dados de qualificação não fornecidos neste requerimento."),
        Bloco("vazio", [("", set())]),
        _paragrafo("Nestes termos, pede deferimento."),
        _paragrafo(f"Morrinhos-GO, {hoje}."),
        Bloco("vazio", [("", set())]),
        _paragrafo("________________________________________"),
        _paragrafo(nome, negrito=True),
        _paragrafo("Reconhecimento de firma (se houver):"),
    ]
    nome_arquivo = f"Requerimento {tipo.upper().replace('-', ' e ')} - Matrícula {matricula}.docx"
    return nome_arquivo, documento_docx.em_bytes(blocos, MOLDE)


def enriquecer_modelo_tri7(payload: dict, cliente) -> None:
    busca = str(payload.get("modeloTri7Busca") or "").strip()
    if not busca:
        return
    candidatos = cliente.buscar_minutas(descricao=busca)
    if not candidatos:
        return
    chave_busca = _chave(busca)
    escolhido = min(
        candidatos,
        key=lambda item: (0 if _chave(item.get("descricao")) == chave_busca else 1, len(str(item.get("descricao") or ""))),
    )
    texto = cliente.buscar_texto_minuta(escolhido["minuta_id"])["texto"]
    payload["modeloTri7"] = {
        "minutaId": escolhido["minuta_id"],
        "descricao": escolhido.get("descricao") or busca,
        "texto": texto,
    }
