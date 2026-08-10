import io
import re
import unicodedata
from collections import OrderedDict

from pypdf import PdfReader

from backend.app.parser import separar_atos


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto.upper())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto).strip()


REGRAS_COMUNICAR = (
    (("VENDA E COMPRA", "COMPRA E VENDA"), "Mudança de titularidade"),
    (("INVENTARIO", "PARTILHA", "ARROLAMENTO"), "Mudança de titularidade por sucessão"),
    (("INCORPORACAO DE PATRIMONIO",), "Mudança de titularidade"),
    (("DIVISAO AMIGAVEL", "DIVISAO DE IMOVEL"), "Divisão ou parcelamento"),
    (("DESMEMBRAMENTO", "PARCELAMENTO", "LOTEAMENTO"), "Parcelamento ou desmembramento"),
    (("GEORREFERENCIAMENTO",), "Alteração territorial ou desmembramento"),
    (("FUSAO", "UNIFICACAO", "REMEMBRAMENTO"), "Fusão ou remembramento"),
    (("RETIFICACAO DE AREA",), "Retificação de área"),
    (("RESERVA LEGAL", "PATRIMONIO NATURAL", "RPPN"), "Limitação ambiental"),
    (("REFORMA AGRARIA",), "Modificação territorial ou de titularidade"),
)

REGRAS_REVISAR = (
    (("RETIFICACAO ADMINISTRATIVA", "RETIFICACAO EX-OFFICIO"), "Confirmar o objeto da retificação"),
    (("AVERBACAO",), "Tipo genérico: conferir o conteúdo do ato"),
)


def classificar_ato(ato: str) -> tuple[str, str]:
    normalizado = _normalizar(ato)
    for termos, motivo in REGRAS_COMUNICAR:
        if any(termo in normalizado for termo in termos):
            return "COMUNICAR", motivo
    for termos, motivo in REGRAS_REVISAR:
        if any(termo in normalizado for termo in termos):
            return "REVISAR", motivo
    return "FORA_DAS_HIPOTESES", "Não corresponde às hipóteses fornecidas"


ANDAMENTO_CANCELADO_DECURSO = "FINALIZADO DECURSO DE PRAZO"
ANDAMENTO_FINALIZADO = "FINALIZADO"


def _numero_inteiro(valor: object) -> int | None:
    try:
        numero = int(str(valor).replace(".", "").strip())
    except (TypeError, ValueError):
        return None
    return numero if numero >= 0 else None


def _codigo_ato_tri7(item: dict) -> str | None:
    registrado = item.get("atos_registrados") or {}
    tipo = _normalizar(str(registrado.get("ato_tipo") or ""))
    numero = _numero_inteiro(registrado.get("ato_numero"))
    if numero is None or tipo not in {"A", "AV", "R", "M"}:
        return None
    prefixo = "AV" if tipo in {"A", "AV"} else tipo
    return f"{prefixo}.{numero}"


def _formatar_numero_registro(numero: int) -> str:
    return f"{numero:,}".replace(",", ".")


def referencias_matriculas_tri7(protocolo_json: dict) -> set[int]:
    referencias = set()
    for item in protocolo_json.get("itens_do_pedido") or []:
        dados_imovel = item.get("dados_imovel") or {}
        tipo_registro = _normalizar(str(dados_imovel.get("tipo_registro") or ""))
        numero = _numero_inteiro(dados_imovel.get("numero_registro"))
        if tipo_registro == "M" and numero and _codigo_ato_tri7(item):
            referencias.add(numero)
    return referencias


def protocolo_finalizado_sem_cancelamento(protocolo_json: dict) -> bool:
    tipos = {
        _normalizar(str(item.get("andamento_tipo") or ""))
        for item in (protocolo_json.get("andamentos") or [])
        if isinstance(item, dict)
    }
    return ANDAMENTO_FINALIZADO in tipos and ANDAMENTO_CANCELADO_DECURSO not in tipos


def _texto_menciona_protocolo(texto: str, numero_protocolo: int | None) -> bool:
    if numero_protocolo is None:
        return False
    esperado = str(numero_protocolo)
    for match in re.finditer(
        r"\bPROTOCOLO\b[^\d]{0,30}(\d[\d.\s]{0,15})",
        _normalizar(texto),
    ):
        if re.sub(r"\D", "", match.group(1)) == esperado:
            return True
    return False


def _codigos_confirmados_no_texto(texto: str, numero_protocolo: int | None) -> set[str]:
    confirmados = set()
    for ato in separar_atos(texto):
        codigo = re.fullmatch(r"(R|AV)\.0*(\d+)", ato.get("codigo") or "", re.IGNORECASE)
        if codigo and _texto_menciona_protocolo(ato.get("texto") or "", numero_protocolo):
            confirmados.add(f"{codigo.group(1).upper()}.{int(codigo.group(2))}")
    return confirmados


def resumir_protocolo_tri7(
    protocolo_json: dict,
    textos_matriculas: dict[int, str] | None = None,
    falhas_textos: set[int] | None = None,
) -> dict:
    """Extrai somente a situação e os atos necessários ao módulo INCRA.

    Pessoas, documentos e textos recebidos da Tri7 não entram no retorno.
    """
    textos_matriculas = textos_matriculas or {}
    falhas_textos = falhas_textos or set()
    protocolo = protocolo_json.get("protocolo") or {}
    numero_protocolo = _numero_inteiro(protocolo.get("protocolo_numero"))
    candidatos = OrderedDict()
    for item in protocolo_json.get("itens_do_pedido") or []:
        dados_imovel = item.get("dados_imovel") or {}
        tipo_registro = _normalizar(str(dados_imovel.get("tipo_registro") or ""))
        numero = _numero_inteiro(dados_imovel.get("numero_registro"))
        codigo = _codigo_ato_tri7(item)
        if tipo_registro != "M" or numero is None or numero == 0 or not codigo:
            continue
        atos = candidatos.setdefault(numero, [])
        if codigo not in atos:
            atos.append(codigo)

    andamentos = [
        item for item in (protocolo_json.get("andamentos") or [])
        if isinstance(item, dict)
    ]
    cancelamentos = [
        item for item in andamentos
        if _normalizar(str(item.get("andamento_tipo") or "")) == ANDAMENTO_CANCELADO_DECURSO
    ]
    cancelado = bool(cancelamentos)
    confiar_atos_tri7 = protocolo_finalizado_sem_cancelamento(protocolo_json)

    matriculas = OrderedDict()
    nao_confirmados = 0
    for numero, codigos in candidatos.items():
        texto = textos_matriculas.get(numero, "")
        codigos_texto = _codigos_confirmados_no_texto(texto, numero_protocolo) if texto else set()
        confirmados = []
        for codigo in codigos:
            praticado = confiar_atos_tri7 or codigo in codigos_texto
            if codigo == "M.0" and not confiar_atos_tri7:
                praticado = bool(texto) and _texto_menciona_protocolo(texto, numero_protocolo)
            if praticado:
                confirmados.append(codigo)
            else:
                nao_confirmados += 1
        if confirmados:
            matriculas[numero] = confirmados

    ultimo_andamento = max(
        andamentos,
        key=lambda item: str(item.get("data_hora") or ""),
        default=None,
    )
    matriculas_json = [
        {"numero": str(numero), "numeroFormatado": _formatar_numero_registro(numero), "atos": atos}
        for numero, atos in matriculas.items()
    ]

    if cancelado:
        situacao, rotulo = "CANCELADO_DECURSO_PRAZO", "Cancelado — decurso de prazo"
    elif matriculas_json:
        situacao, rotulo = "PRATICADO", "Atos praticados"
    else:
        situacao, rotulo = "SEM_ATO", "Sem ato identificado"

    alerta = None
    if cancelado and matriculas_json:
        alerta = "O protocolo está cancelado por decurso de prazo, mas possui atos confirmados no texto; revisar."
    elif falhas_textos:
        alerta = "Não foi possível confirmar todos os atos no texto atual das matrículas."
    elif not cancelado and nao_confirmados:
        alerta = "A Tri7 vinculou atos ao protocolo que não foram localizados no texto atual; revisar."

    return {
        "situacaoTri7": situacao,
        "situacaoTri7Rotulo": rotulo,
        "cancelado": cancelado,
        "matriculas": matriculas_json,
        "ultimoAndamento": (
            {
                "tipo": str(ultimo_andamento.get("andamento_tipo") or ""),
                "dataHora": ultimo_andamento.get("data_hora"),
            }
            if ultimo_andamento else None
        ),
        "atosVinculadosNaoConfirmados": nao_confirmados,
        "alertaTri7": alerta,
        "erroTri7": None,
    }


def extrair_protocolos(pdf_bytes: bytes) -> dict:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    if not reader.pages:
        raise ValueError("O PDF não possui páginas legíveis.")

    texto = "\n".join((pagina.extract_text() or "") for pagina in reader.pages)
    padrao = re.compile(
        r"Ato\s+Praticado:\s*\n?[^\n]*?/[^\n]*?\n"
        r"(?P<ato>.*?)\s*Protocolo:\s*(?P<protocolo>\d+)",
        re.IGNORECASE | re.DOTALL,
    )

    agrupados = OrderedDict()
    lancamentos = 0
    for match in padrao.finditer(texto):
        protocolo = match.group("protocolo")
        ato = re.sub(r"\s+", " ", match.group("ato")).strip(" -:;")
        if not ato:
            continue
        lancamentos += 1
        chave = (protocolo, _normalizar(ato))
        if chave not in agrupados:
            status, motivo = classificar_ato(ato)
            agrupados[chave] = {
                "protocolo": protocolo, "ato": ato, "status": status,
                "motivo": motivo, "ocorrencias": 0,
            }
        agrupados[chave]["ocorrencias"] += 1

    if not agrupados:
        raise ValueError("Nenhum protocolo com tipo de ato foi identificado neste PDF.")

    itens = sorted(agrupados.values(), key=lambda item: (int(item["protocolo"]), item["ato"]))
    status_validos = ("COMUNICAR", "REVISAR", "FORA_DAS_HIPOTESES")
    return {
        "paginas": len(reader.pages),
        "lancamentos": lancamentos,
        "protocolos_unicos": len({item["protocolo"] for item in itens}),
        "itens": itens,
        "contagens": {s: sum(1 for item in itens if item["status"] == s) for s in status_validos},
    }
