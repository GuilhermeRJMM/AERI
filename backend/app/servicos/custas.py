import io
import re
import unicodedata

import pymupdf
from fastapi import HTTPException
from pypdf import PdfReader


MODALIDADES = {"PENHOR", "ALIENACAO_FIDUCIARIA"}
CERTIDOES_FORA_DO_INFORMAR_CUSTAS = (
    "CERTIDAO VINTENARIA",
    "DOCUMENTO ARQUIVADO",
    "PACTO ANTENUPCIAL",
)
RESULTADOS = {"PENDENTE", "POSITIVA", "NEGATIVA"}
STATUS_CUSTAS = {
    "FAZER_PESQUISA",
    "BUSCA_REALIZADA",
    "DUPLICADO_DEVOLVIDO",
    "PAGO_PROCESSANDO",
    "CUSTAS_INFORMADAS",
    "RESPONDIDO",
    "SEM_PAGAMENTO",
    "CUSTAS_ERRADAS",
}
STATUS_FINAIS = {"DUPLICADO_DEVOLVIDO", "RESPONDIDO", "SEM_PAGAMENTO"}


def _rotulo_importacao(item: dict) -> str:
    alienacao = item.get("modalidade") == "ALIENACAO_FIDUCIARIA"
    modalidade = "Alienação Fiduciária" if alienacao else "Penhor"
    resultados = (
        {"POSITIVA": "Positiva", "NEGATIVA": "Negativa", "PENDENTE": "Pendente"}
        if alienacao else
        {"POSITIVA": "Positivo", "NEGATIVA": "Negativo", "PENDENTE": "Pendente"}
    )
    return f"{modalidade} {resultados.get(item.get('resultado'), 'Pendente')}"


def gerar_relatorio_custas_pdf(itens: list[dict]) -> bytes:
    """Gera o relatório mínimo do módulo, sem expor os demais dados pessoais."""
    if not itens:
        raise ValueError("Não há pedidos para exportar.")
    documento = pymupdf.open()
    try:
        pagina = documento.new_page(width=595, height=842)
        y = 58
        for item in itens:
            if y + 52 > 790:
                pagina = documento.new_page(width=595, height=842)
                y = 58
            pagina.insert_text((50, y), f"Número do pedido: {item['pedido']}", fontname="helv", fontsize=12, color=(0, 0, 0))
            pagina.insert_text((50, y + 19), f"Importação: {_rotulo_importacao(item)}", fontname="helv", fontsize=12, color=(0, 0, 0))
            y += 57
        documento.set_metadata({"title": "Relatório - Informar Custas", "author": "AERI"})
        return documento.tobytes(garbage=4, deflate=True)
    finally:
        documento.close()


def _sem_acentos(valor: str) -> str:
    return "".join(
        caractere for caractere in unicodedata.normalize("NFKD", valor)
        if not unicodedata.combining(caractere)
    ).upper()


def _limpar_espacos(valor: str) -> str:
    return re.sub(r"\s+", " ", valor or "").strip(" ,;:-")


def _formatar_documento(valor: str) -> str:
    digitos = re.sub(r"\D", "", valor or "")
    if len(digitos) == 11:
        return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    if len(digitos) == 14:
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"
    return _limpar_espacos(valor) or "NÃO CONSTA"


def _extrair_modalidade(texto: str) -> str | None:
    normalizado = _sem_acentos(texto)
    if re.search(r"\bALIENACAO(?:\s+FIDUCIARIA)?\b", normalizado):
        return "ALIENACAO_FIDUCIARIA"
    if re.search(r"\bPENHOR\b", normalizado):
        return "PENHOR"
    return None


def _extrair_produto(texto: str) -> str:
    normalizado = _sem_acentos(texto)
    produtos = (
        ("SOJA", r"\bSOJA(?:\s+EM\s+GRAOS)?\b"),
        ("MILHO", r"\bMILHO\b"),
        ("SORGO", r"\bSORGO\b"),
        ("ALGODÃO", r"\bALGODAO\b"),
        ("CAFÉ", r"\bCAFE\b"),
        ("FEIJÃO", r"\bFEIJAO\b"),
        ("ARROZ", r"\bARROZ\b"),
        ("TRIGO", r"\bTRIGO\b"),
        ("ESTUFAS", r"\bESTUFAS?\b"),
    )
    for rotulo, padrao in produtos:
        if re.search(padrao, normalizado):
            return rotulo
    captura = re.search(
        r"(?:CULTURA|PRODUTO|COMMODITY|COMMODITIE)\s*:?\s*([A-ZÀ-Ü ]{2,40}?)(?=\s*(?:,|;|\.|SAFRA|$))",
        texto,
        re.IGNORECASE,
    )
    return _limpar_espacos(captura.group(1)).upper() if captura else "NÃO CONSTA"


def _extrair_safra(texto: str) -> str:
    normalizado = _sem_acentos(texto)
    produto_intercalado = r"(?:(?:SOJA(?:\s+EM\s+GRAOS)?|MILHO|SORGO|ALGODAO|CAFE|FEIJAO|ARROZ|TRIGO)\s+)?"
    captura = re.search(
        rf"\bSAFRA\s*:?\s*{produto_intercalado}(\d{{2,4}})\s*(?:[/\-]|\s)\s*(\d{{2,4}})\b",
        normalizado,
    )
    if not captura:
        return "NÃO CONSTA"
    inicio, fim = captura.groups()
    inicio_num = int(inicio)
    if len(inicio) == 2:
        inicio_num += 2000
    fim_num = int(fim)
    if len(fim) == 2:
        fim_num += (inicio_num // 100) * 100
        if fim_num < inicio_num:
            fim_num += 100
    return f"{inicio_num:04d}/{fim_num:04d}"


def _segmentar_pedidos(texto: str) -> list[str]:
    inicios = [item.start() for item in re.finditer(r"(?=\bP\d{11}D\b)", texto, re.IGNORECASE)]
    if not inicios:
        return []
    blocos = []
    for indice, inicio in enumerate(inicios):
        fim = inicios[indice + 1] if indice + 1 < len(inicios) else len(texto)
        bloco = texto[inicio:fim]
        if re.search(r"\bS\d{11}D\b", bloco, re.IGNORECASE):
            blocos.append(bloco)
    return blocos


def extrair_pedidos_texto(texto: str) -> dict:
    itens_por_pedido: dict[str, dict] = {}
    ignorados = 0
    alertas = []

    for bloco in _segmentar_pedidos(texto):
        protocolo = re.search(r"\b(S\d{11}D)\b", bloco, re.IGNORECASE)
        bloco_normalizado = _sem_acentos(bloco)
        if any(tipo in bloco_normalizado for tipo in CERTIDOES_FORA_DO_INFORMAR_CUSTAS):
            ignorados += 1
            continue

        modalidade = _extrair_modalidade(bloco)
        if not modalidade and "LIVRO 3 - GARANTIAS" in bloco_normalizado:
            modalidade = "PENHOR"
        relacionado = modalidade and (
            "LIVRO 3" in bloco_normalizado
            or "SAFRA" in bloco_normalizado
            or "GRAO" in bloco_normalizado
        )
        if not protocolo or not relacionado:
            ignorados += 1
            continue

        pedido = protocolo.group(1).upper()
        nome = re.search(
            r"Nome\s*/\s*Raz[aã]o\s*:\s*(.+?)\s*,?\s*CPF\s*/\s*CNPJ\s*:",
            bloco,
            re.IGNORECASE | re.DOTALL,
        )
        documento = re.search(
            r"CPF\s*/\s*CNPJ\s*:\s*([0-9./-]+)",
            bloco,
            re.IGNORECASE,
        )
        produto = _extrair_produto(bloco)
        safra = _extrair_safra(bloco)
        if produto == "ESTUFAS" and safra == "NÃO CONSTA":
            safra = "NÃO SE APLICA"
        item = {
            "pedido": pedido,
            "nome": _limpar_espacos(nome.group(1)) if nome else "NÃO CONSTA",
            "documento": _formatar_documento(documento.group(1) if documento else ""),
            "modalidade": modalidade,
            "produto": produto,
            "safra": safra,
        }
        ausentes = [campo for campo in ("nome", "documento", "produto", "safra") if item[campo] == "NÃO CONSTA"]
        if ausentes:
            alertas.append({"pedido": pedido, "campos": ausentes})
        itens_por_pedido[pedido] = item

    return {
        "itens": list(itens_por_pedido.values()),
        "total": len(itens_por_pedido),
        "ignorados": ignorados,
        "alertas": alertas,
    }


def extrair_pedidos_pdf(pdf_bytes: bytes) -> dict:
    try:
        leitor = PdfReader(io.BytesIO(pdf_bytes))
        texto = "\n".join(pagina.extract_text() or "" for pagina in leitor.pages)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Não foi possível ler o relatório PDF.") from exc
    if not texto.strip():
        raise HTTPException(status_code=422, detail="O PDF não possui texto pesquisável.")
    resultado = extrair_pedidos_texto(texto)
    if not resultado["itens"]:
        raise HTTPException(status_code=422, detail="Nenhum pedido de penhor ou alienação de grãos foi encontrado.")
    return resultado


def validar_item_custas(dados: dict) -> dict:
    status = str(dados.get("status", "FAZER_PESQUISA")).strip().upper()
    resultado = str(dados.get("resultado", "PENDENTE")).strip().upper()
    modalidade = str(dados.get("modalidade", "")).strip().upper()
    if status not in STATUS_CUSTAS or resultado not in RESULTADOS or modalidade not in MODALIDADES:
        raise HTTPException(status_code=422, detail="Status, resultado ou modalidade inválidos.")
    registro = _limpar_espacos(str(dados.get("numeroRegistro", "")))[:200]
    if resultado == "POSITIVA" and not registro:
        raise HTTPException(status_code=422, detail="Informe o número do registro para uma pesquisa positiva.")
    return {
        "nome": _limpar_espacos(str(dados.get("nome", "")))[:180] or "NÃO CONSTA",
        "documento": _formatar_documento(str(dados.get("documento", "")))[:20],
        "modalidade": modalidade,
        "produto": _limpar_espacos(str(dados.get("produto", "")))[:80].upper() or "NÃO CONSTA",
        "safra": _limpar_espacos(str(dados.get("safra", "")))[:20].upper() or "NÃO CONSTA",
        "resultado": resultado,
        "numero_registro": registro,
        "status": status,
    }


def custas_json(item: dict) -> dict:
    return {
        "id": str(item["id"]),
        "pedido": item["pedido"],
        "nome": item["nome"],
        "documento": item["documento"],
        "modalidade": item["modalidade"],
        "produto": item["produto"],
        "safra": item["safra"],
        "resultado": item["resultado"],
        "numeroRegistro": item["numero_registro"],
        "status": item["status"],
        "finalizado": item["finalizado"],
        "atualizadoEm": item["atualizado_em"].isoformat(),
    }
