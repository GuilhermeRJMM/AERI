import io
import re
import unicodedata
from datetime import date

from pypdf import PdfReader


# 3 dígitos + ponto + 3 dígitos, sem ser parte de um número maior (evita
# casar com trechos do CNPJ do rodapé, ex.: "20.639.962" contém "639.962").
PADRAO_NUMERO_PROTOCOLO = re.compile(r"(?<!\d\.)\b(\d{3}\.\d{3})\b(?!/\d)")
PADRAO_DATA = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
PADRAO_SEM_EFEITO = re.compile(r"\(Sem Efeito\)", re.IGNORECASE)
PADRAO_PRENOTADO = re.compile(r"\bPrenotado\b", re.IGNORECASE)
# Cabeçalho de uma referência de ato no "Resumo dos Atos": R.13 -, Av.6 -,
# Mat.0 -, Reg.0 - (inclui "Reg. Auxiliar").
PADRAO_ATO_REF = re.compile(r"\b(?:R|Av|Mat|Reg)\.\s*\d+\s*-\s*", re.IGNORECASE)

PADRAO_DATA_PLACEHOLDER = re.compile(r"\bxx[./]\d{2}[./]\d{4}\b|\b\d{2}[./]xx[./]\d{4}\b", re.IGNORECASE)
PADRAO_VALOR_EM_BRANCO = re.compile(r"R\$\s*;|R\$\s*\.")
PADRAO_SELO_EM_BRANCO = re.compile(r"\bSelo:\s*\.")
PADRAO_FECHO_EM_BRANCO = re.compile(r"-\s*[A-ZÀ-Ü]{2},\s*de\s+de\.", re.IGNORECASE)

STATUS_VALIDOS = ("PRENOTADO", "REGISTRADO", "SEM_EFEITO", "INDEFINIDO")


def _colapsar_espacos(valor: str) -> str:
    return re.sub(r"\s+", " ", valor or "").strip()


def _normalizar(valor: str) -> str:
    sem_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", valor or "") if not unicodedata.combining(c)
    )
    return _colapsar_espacos(sem_acentos).upper()


def _texto_valido(valor: object) -> bool:
    return isinstance(valor, str) and valor.strip() != ""


def classificar_status(bloco: str) -> str:
    # "(Sem Efeito)" e a presença de uma referência de ato (R./Av./Mat./Reg.)
    # são evidências concretas; checadas antes de "Prenotado" para não cair
    # nesse rótulo por vazamento de texto de uma linha vizinha.
    if PADRAO_SEM_EFEITO.search(bloco):
        return "SEM_EFEITO"
    if PADRAO_ATO_REF.search(bloco):
        return "REGISTRADO"
    if PADRAO_PRENOTADO.search(bloco):
        return "PRENOTADO"
    return "INDEFINIDO"


def _parse_bloco(numero_bruto: str, bloco: str) -> dict:
    sem_numero = bloco[len(numero_bruto):]
    match_data = PADRAO_DATA.search(sem_numero)
    if match_data:
        nome = _colapsar_espacos(sem_numero[: match_data.start()])
        resto = sem_numero[match_data.end():]
        data_iso = f"{match_data.group(3)}-{match_data.group(2)}-{match_data.group(1)}"
    else:
        nome = _colapsar_espacos(sem_numero)
        resto = ""
        data_iso = None
    return {
        "numero": numero_bruto.replace(".", ""),
        "numeroFormatado": numero_bruto,
        "data": data_iso,
        "nomeApresentante": nome or "NÃO CONSTA",
        "status": classificar_status(bloco),
        "resumoBruto": _colapsar_espacos(resto)[:600],
    }


def extrair_protocolos_pdf(pdf_bytes: bytes) -> list[dict]:
    """Extrai as linhas do Livro de Protocolos (PDF exportado da Tri7).

    Não distingue as duas seções da folha (expediente do dia vs. protocolos
    de dias anteriores que tiveram ato praticado nesta data) — quando o
    mesmo número aparece duas vezes (ex.: prenotado na 1ª seção e já
    registrado na 2ª), fica valendo a última ocorrência no texto, que reflete
    o estado mais atual.
    """
    leitor = PdfReader(io.BytesIO(pdf_bytes))
    if not leitor.pages:
        raise ValueError("O PDF não possui páginas legíveis.")
    texto = "\n".join(pagina.extract_text() or "" for pagina in leitor.pages)

    matches = list(PADRAO_NUMERO_PROTOCOLO.finditer(texto))
    if not matches:
        raise ValueError("Nenhum protocolo foi identificado neste PDF.")

    linhas: list[dict] = []
    indices_por_numero: dict[str, int] = {}
    for indice, match in enumerate(matches):
        inicio = match.start()
        fim = matches[indice + 1].start() if indice + 1 < len(matches) else len(texto)
        item = _parse_bloco(match.group(1), texto[inicio:fim])
        anterior = indices_por_numero.get(item["numero"])
        if anterior is not None:
            linhas[anterior] = item
        else:
            indices_por_numero[item["numero"]] = len(linhas)
            linhas.append(item)
    return linhas


def _itens_com_ato(protocolo_json: dict) -> list[dict]:
    # Busca e Prenotação são itens administrativos (ato_tipo/ato_numero
    # nulos) — não são um registro/averbação de verdade, então não fazem
    # sentido conferir contra o Dados do Título.
    itens = []
    for item in protocolo_json.get("itens_do_pedido") or []:
        registrado = item.get("atos_registrados") or {}
        if registrado.get("ato_tipo") is not None and registrado.get("ato_numero") is not None:
            itens.append(item)
    return itens


def _regra_natureza_bate_com_titulo(protocolo_json: dict) -> list[dict]:
    protocolo = protocolo_json.get("protocolo") or {}
    descricao_titulo = protocolo.get("descricao_titulo")
    if not _texto_valido(descricao_titulo):
        return [{
            "regra": "NATUREZA_TITULO",
            "gravidade": "GRAVE",
            "descricao": "O protocolo não possui descrição do título (descricao_titulo em branco).",
        }]

    itens_com_ato = _itens_com_ato(protocolo_json)
    if not itens_com_ato:
        return [{
            "regra": "NATUREZA_TITULO",
            "gravidade": "GRAVE",
            "descricao": "Nenhum item com registro/averbação foi encontrado para conferir contra o título.",
        }]

    titulo_normalizado = _normalizar(str(descricao_titulo))
    ocorrencias = []
    for item in itens_com_ato:
        registrado = item["atos_registrados"]
        rotulo = f"{registrado.get('ato_tipo')}.{registrado.get('ato_numero')}"
        natureza = item.get("natureza_formal_descricao")
        if not _texto_valido(natureza):
            ocorrencias.append({
                "regra": "NATUREZA_TITULO",
                "gravidade": "GRAVE",
                "descricao": f"{rotulo}: não possui Natureza Formal do Título preenchida.",
            })
            continue
        natureza_normalizada = _normalizar(str(natureza))
        # Comparação por conteúdo (não igualdade exata): descricao_titulo
        # costuma ser o nome completo do instrumento e pode conter a
        # natureza formal como parte do texto (ex.: "ESCRITURA ... E DAÇÃO
        # EM PAGAMENTO" contém "DAÇÃO EM PAGAMENTO"). Quando nenhum dos dois
        # aparece dentro do outro, os dois textos não têm relação nenhuma —
        # sinal de que a natureza formal escolhida no item não corresponde
        # ao título do protocolo.
        if natureza_normalizada not in titulo_normalizado and titulo_normalizado not in natureza_normalizada:
            ocorrencias.append({
                "regra": "NATUREZA_TITULO",
                "gravidade": "GRAVE",
                "descricao": (
                    f"{rotulo}: Dados do Título ('{descricao_titulo}') não corresponde à "
                    f"Natureza Formal ('{natureza}')."
                ),
            })
    return ocorrencias


def _regra_busca_com_matricula(protocolo_json: dict) -> list[dict]:
    ocorrencias = []
    for item in protocolo_json.get("itens_do_pedido") or []:
        if _normalizar(str(item.get("natureza_formal_descricao") or "")) != "BUSCA":
            continue
        numero_registro = (item.get("dados_imovel") or {}).get("numero_registro")
        if numero_registro:
            ocorrencias.append({
                "regra": "BUSCA_COM_MATRICULA",
                "gravidade": "GRAVE",
                "descricao": f"Item de Busca retornou matrícula/registro nº {numero_registro} vinculado.",
            })
    return ocorrencias


def _regra_ordem_e_texto_dos_atos(protocolo_json: dict) -> list[dict]:
    ocorrencias = []
    atos: list[tuple[int, str]] = []
    for item in protocolo_json.get("itens_do_pedido") or []:
        registrado = item.get("atos_registrados") or {}
        numero, tipo = registrado.get("ato_numero"), registrado.get("ato_tipo")
        if numero is None or tipo is None:
            continue
        atos.append((int(numero), str(tipo)))
        texto = registrado.get("texto") or ""
        rotulo = f"{tipo}.{numero}"
        if PADRAO_DATA_PLACEHOLDER.search(texto):
            ocorrencias.append({
                "regra": "CAMPO_EM_BRANCO",
                "gravidade": "GRAVE",
                "descricao": f"{rotulo}: data do ato ainda não preenchida (consta 'xx' no lugar do dia/mês).",
            })
        if PADRAO_FECHO_EM_BRANCO.search(texto):
            ocorrencias.append({
                "regra": "CAMPO_EM_BRANCO",
                "gravidade": "GRAVE",
                "descricao": f"{rotulo}: data de fechamento do ato (dia/mês) em branco.",
            })
        if PADRAO_VALOR_EM_BRANCO.search(texto) or PADRAO_SELO_EM_BRANCO.search(texto):
            ocorrencias.append({
                "regra": "CAMPO_EM_BRANCO",
                "gravidade": "ATENCAO",
                "descricao": f"{rotulo}: selo e/ou cotação (emolumentos/ISSQN/taxa/total) aparentam estar em branco.",
            })
    for anterior, atual in zip(atos, atos[1:]):
        if atual[0] < anterior[0]:
            ocorrencias.append({
                "regra": "ORDEM_NUMERICA",
                "gravidade": "GRAVE",
                "descricao": f"Ordem fora de sequência: {anterior[1]}.{anterior[0]} seguido de {atual[1]}.{atual[0]}.",
            })
    return ocorrencias


def _regra_data_um_dia_antes(item_pdf: dict, data_esperada: date) -> list[dict]:
    if item_pdf.get("status") != "REGISTRADO" or not item_pdf.get("data"):
        return []
    data_linha = date.fromisoformat(item_pdf["data"])
    if data_linha != data_esperada:
        return [{
            "regra": "DATA_DIVERGENTE",
            "gravidade": "GRAVE",
            "descricao": (
                f"Data do registro ({data_linha.strftime('%d/%m/%Y')}) diferente da esperada "
                f"({data_esperada.strftime('%d/%m/%Y')})."
            ),
        }]
    return []


def conferir_protocolo(item_pdf: dict, protocolo_json: dict, data_esperada: date) -> list[dict]:
    return [
        *_regra_natureza_bate_com_titulo(protocolo_json),
        *_regra_busca_com_matricula(protocolo_json),
        *_regra_ordem_e_texto_dos_atos(protocolo_json),
        *_regra_data_um_dia_antes(item_pdf, data_esperada),
    ]
