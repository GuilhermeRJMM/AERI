import re
import unicodedata


# backend/app/regras.py

REGRAS = {
    "AÇÕES/EXISTÊNCIA": {"categoria": "PUBLICIDADE", "impacta": False},
    "ALIENAÇÃO FIDUCIÁRIA": {"categoria": "ÔNUS", "impacta": True},
    "ANTICRESE": {"categoria": "ÔNUS", "impacta": True},
    "ARROLAMENTO DE BENS": {"categoria": "PUBLICIDADE", "impacta": False},
    "ARRESTO E SEQUESTRO": {"categoria": "ÔNUS", "impacta": True},
    "AÇÃO PREMONITÓRIA": {"categoria": "PUBLICIDADE", "impacta": False},
    "ASSUNÇÃO DE DÍVIDA": {"categoria": "ÔNUS", "impacta": True},
    "ASSUNÇÃO DE OBRIGAÇÃO": {"categoria": "ÔNUS", "impacta": True},
    "ASSUNÇÃO DE OBRIGAÇÕES": {"categoria": "ÔNUS", "impacta": True},
    "CAUÇÃO": {"categoria": "ÔNUS", "impacta": True},
    "CITAÇÃO DE AÇÕES": {"categoria": "PUBLICIDADE", "impacta": False},
    "REIPERSECUTÓRIAS": {"categoria": "PUBLICIDADE", "impacta": False},
    "CLÁUSULA RESOLUTIVA": {"categoria": "PUBLICIDADE", "impacta": False},
    "CLÁUSULAS RESTRITIVAS": {"categoria": "PUBLICIDADE", "impacta": False},
    "CLÁUSULA RESTRITIVA": {"categoria": "PUBLICIDADE", "impacta": False},
    "FIDEICOMISSO": {"categoria": "ÔNUS", "impacta": True},
    "IMPENHORABILIDADE": {"categoria": "PUBLICIDADE", "impacta": False},
    "INALIENABILIDADE": {"categoria": "PUBLICIDADE", "impacta": False},
    "INCOMUNICABILIDADE": {"categoria": "PUBLICIDADE", "impacta": False},
    "COMPROMISSO DE COMPRA E VENDA": {"categoria": "ÔNUS", "impacta": True},
    "CONCESSÃO DE DIREITO": {"categoria": "ÔNUS", "impacta": True},
    "CONCESSÃO DE USO": {"categoria": "ÔNUS", "impacta": True},
    "ABERTURA DE CRÉDITO": {"categoria": "ÔNUS", "impacta": True},
    "CONTRATO DE LOCAÇÃO": {"categoria": "PUBLICIDADE", "impacta": False},
    "CÉDULA DE CRÉDITO": {"categoria": "ÔNUS", "impacta": True},
    "CÉDULA DE PRODUTO RURAL": {"categoria": "ÔNUS", "impacta": True},
    "CÉDULA RURAL": {"categoria": "ÔNUS", "impacta": True},
    "CÉDULAS HIPOTECÁRIAS": {"categoria": "ÔNUS", "impacta": True},
    "CONVENÇÃO DE CONDOMÍNIO": {"categoria": "PUBLICIDADE", "impacta": False},
    "DEBENTURES": {"categoria": "ÔNUS", "impacta": True},
    "EMPRÉSTIMOS POR OBRIGAÇÕES": {"categoria": "ÔNUS", "impacta": True},
    "DIREITO DE SUPERFÍCIE": {"categoria": "ÔNUS", "impacta": True},
    "ENFITEUSE": {"categoria": "ÔNUS", "impacta": True},
    "EXECUÇÃO": {"categoria": "PUBLICIDADE", "impacta": False},
    "INDISPONIBILIDADE": {"categoria": "PUBLICIDADE", "impacta": False},
    "BEM DE FAMÍLIA": {"categoria": "PUBLICIDADE", "impacta": False},
    "USUFRUTO": {"categoria": "ÔNUS", "impacta": True},
    "NOTA DE CRÉDITO": {"categoria": "ÔNUS", "impacta": True},
    "UTILIZAÇÃO COMPULSÓRIA": {"categoria": "ÔNUS", "impacta": True},
    "PARCERIA AGRÍCOLA": {"categoria": "PUBLICIDADE", "impacta": False},
    "PENHORA": {"categoria": "ÔNUS", "impacta": True},
    "PENHOR": {"categoria": "ÔNUS", "impacta": True},
    "RENDAS CONSTITUÍDAS": {"categoria": "ÔNUS", "impacta": True},
    "RENOVAÇÃO SIMPLIFICADA": {"categoria": "ÔNUS", "impacta": True},
    "RETROVENDA": {"categoria": "PUBLICIDADE", "impacta": False},
    "SERVIDÃO": {"categoria": "ÔNUS", "impacta": True},
    "SUB-ROGAÇÃO": {"categoria": "ÔNUS", "impacta": True},
    "TERMO DE SECURITIZAÇÃO": {"categoria": "ÔNUS", "impacta": True},
    "TRASLADO DE HIPOTECA": {"categoria": "ÔNUS", "impacta": True},
    "VÍNCULO": {"categoria": "PUBLICIDADE", "impacta": False},
    "PACTO COMISSÓRIO": {"categoria": "PUBLICIDADE", "impacta": False},

    # --- ATOS COMUNS (Para o sistema achar primeiro e ignorar o resto do texto) ---
    "VENDA E COMPRA": {"categoria": "IGNORAR", "impacta": False},
    "COMPRA E VENDA": {"categoria": "IGNORAR", "impacta": False},
    "ADJUDICAÃ‡ÃƒO": {"categoria": "IGNORAR", "impacta": False},
    "DOAÇÃO": {"categoria": "IGNORAR", "impacta": False},
    "INVENTÁRIO/PARTILHA": {"categoria": "IGNORAR", "impacta": False},
    "INVENTÁRIO": {"categoria": "IGNORAR", "impacta": False},
    "PARTILHA": {"categoria": "IGNORAR", "impacta": False},
    "EDIFICAÇÃO": {"categoria": "IGNORAR", "impacta": False},
    "DESIGNAÇÃO CADASTRAL": {"categoria": "IGNORAR", "impacta": False},
    "DESMEMBRAMENTO": {"categoria": "IGNORAR", "impacta": False},
    "REMEMBRAMENTO": {"categoria": "IGNORAR", "impacta": False},
    "CONSTRUÇÃO": {"categoria": "IGNORAR", "impacta": False},
}

PALAVRAS_CANCELAMENTO = [
    "CANCELAMENTO", "FICA CANCELADA", "FICA CANCELADO", 
    "FIQUE CANCELADA", "FIQUE CANCELADO", "BAIXA",
    "CANCELADA POR", "CANCELADO POR",
    "LIBERADO DO GRAVAME", "LIBERADA DO GRAVAME",
    "LIBERAÇÃO DO GRAVAME",
    "EXTINÇÃO DE DÍVIDA ORIGINÁRIA", "DÍVIDA ORIGINÁRIA FOI CONSIDERADA EXTINTA"
]

PALAVRAS_IGNORAR_FORTE = [
    "INSCRIÇÃO NO CAR", "CADASTRO AMBIENTAL RURAL", 
    "CCIR", "CERTIFICADO DE CADASTRO", 
    "ENDEREÇAMENTO POSTAL", "CEP"
]

PALAVRAS_PUBLICIDADE_FORTE = [
    "IMÓVEL DE LOCALIZAÇÃO", "PENHOR RURAL/IMÓVEL DE LOCALIZAÇÃO",
    "RESTRIÇÕES URBANÍSTICAS", "RESTRIÇÃO URBANÍSTICA",
]

TIPOS_ONUS = [
    ("TRASLADO DE HIPOTECA", "HIPOTECA"),
    ("CEDULA RURAL HIPOTECARIA", "HIPOTECA"),
    ("CEDULA HIPOTECARIA", "HIPOTECA"),
    ("CEDULAS HIPOTECARIAS", "HIPOTECA"),
    ("GARANTIA HIPOTECARIA", "HIPOTECA"),
    ("HIPOTECA", "HIPOTECA"),
    ("ALIENACAO FIDUCIARIA", "ALIENAÇÃO FIDUCIÁRIA"),
    ("ANTICRESE", "ANTICRESE"),
    ("ARRESTO E SEQUESTRO", "ARRESTO E SEQUESTRO"),
    ("ASSUNCAO DE DIVIDA", "ASSUNÇÃO DE DÍVIDA"),
    ("ASSUNCAO DE OBRIGACOES", "ASSUNÇÃO DE OBRIGAÇÕES"),
    ("ASSUNCAO DE OBRIGACAO", "ASSUNÇÃO DE OBRIGAÇÃO"),
    ("CAUCAO", "CAUÇÃO"),
    ("FIDEICOMISSO", "FIDEICOMISSO"),
    ("COMPROMISSO DE COMPRA E VENDA", "COMPROMISSO DE COMPRA E VENDA"),
    ("CONCESSAO DE DIREITO", "CONCESSÃO DE DIREITO"),
    ("CONCESSAO DE USO", "CONCESSÃO DE USO"),
    ("ABERTURA DE CREDITO", "ABERTURA DE CRÉDITO"),
    ("CEDULA DE PRODUTO RURAL", "CÉDULA DE PRODUTO RURAL"),
    ("CEDULA DE CREDITO", "CÉDULA DE CRÉDITO"),
    ("CEDULA RURAL", "CÉDULA RURAL"),
    ("DEBENTURES", "DEBENTURES"),
    ("EMPRESTIMOS POR OBRIGACOES", "EMPRÉSTIMOS POR OBRIGAÇÕES"),
    ("DIREITO DE SUPERFICIE", "DIREITO DE SUPERFÍCIE"),
    ("ENFITEUSE", "ENFITEUSE"),
    ("USUFRUTO", "USUFRUTO"),
    ("NOTA DE CREDITO", "NOTA DE CRÉDITO"),
    ("UTILIZACAO COMPULSORIA", "UTILIZAÇÃO COMPULSÓRIA"),
    ("PENHORA", "PENHORA"),
    ("PENHOR", "PENHOR"),
    ("RENDAS CONSTITUIDAS", "RENDAS CONSTITUÍDAS"),
    ("RENOVACAO SIMPLIFICADA", "RENOVAÇÃO SIMPLIFICADA"),
    ("SERVIDAO", "SERVIDÃO"),
    ("SUB-ROGACAO", "SUB-ROGAÇÃO"),
    ("TERMO DE SECURITIZACAO", "TERMO DE SECURITIZAÇÃO"),
]


def _sem_acentos(texto):
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")

def identificar_tipo_onus(texto):
    texto_sem_acentos = _sem_acentos(texto.upper())
    texto_sem_acentos = re.sub(r"\s+", " ", texto_sem_acentos)

    for padrao, tipo in TIPOS_ONUS:
        if padrao in texto_sem_acentos:
            return tipo

    return None

def extrair_grau_hipoteca(texto):
    texto_sem_acentos = _sem_acentos(texto.upper()).upper()
    texto_sem_acentos = re.sub(r"\s+", " ", texto_sem_acentos)

    grau_numerico = re.search(r"\b(\d{1,2})\s*[OA]?\s*GRAU\b", texto_sem_acentos)
    if grau_numerico:
        return int(grau_numerico.group(1))

    ordinais = {
        "PRIMEIR": 1,
        "SEGUND": 2,
        "TERCEIR": 3,
        "QUART": 4,
        "QUINT": 5,
        "SEXT": 6,
        "SETIM": 7,
        "OITAV": 8,
        "NON": 9,
        "DECIM": 10,
    }

    grau_extenso = re.search(
        r"\b(PRIMEIR[AO]|SEGUND[AO]|TERCEIR[AO]|QUART[AO]|QUINT[AO]|SEXT[AO]|SETIM[AO]|OITAV[AO]|NON[AO]|DECIM[AO])\s+GRAU\b",
        texto_sem_acentos,
    )
    if not grau_extenso:
        grau_extenso = re.search(
            r"\b(PRIMEIR[AO]|SEGUND[AO]|TERCEIR[AO]|QUART[AO]|QUINT[AO]|SEXT[AO]|SETIM[AO]|OITAV[AO]|NON[AO]|DECIM[AO])(?:\s+E\s+ESPECIAL)?\s+HIPOTECA\b",
            texto_sem_acentos,
        )

    if grau_extenso:
        radical = grau_extenso.group(1)[:-1]
        return ordinais.get(radical)

    return None

def formatar_grau_onus(grau):
    return f"{grau}º grau" if grau else None

def classificar(texto, regras_aprendidas=None):
    texto = texto.upper()
    texto_sem_acentos = _sem_acentos(texto)
    texto_sem_acentos_compacto = re.sub(r"\s+", " ", texto_sem_acentos)

    # Aditivo que apenas retifica/ratifica condiÃ§Ãµes da dÃ­vida, como
    # vencimento e forma de pagamento, nÃ£o constitui novo Ã´nus. A garantia
    # anterior continua sendo controlada pelo ato original jÃ¡ registrado.
    if (
        "ADITIVO" in texto_sem_acentos
        and "RATIFIC" in texto_sem_acentos
        and "VENCIMENTO" in texto_sem_acentos
        and "FORMA DE PAGAMENTO" in texto_sem_acentos
        and "GARANTIAS NELA CONSTITUIDAS" in texto_sem_acentos
        and not any(expressao in texto_sem_acentos_compacto for expressao in (
            "OBJETO DA GARANTIA",
            "OBJETOS DA GARANTIA",
            "EM HIPOTECA",
            "EM ALIENACAO FIDUCIARIA",
            "DADO EM HIPOTECA",
            "DADA EM HIPOTECA",
            "PROPRIEDADE FIDUCIARIA",
        ))
    ):
        return ("IGNORAR", False)

    if (
        "ALIENACAO FIDUCIARIA" in texto_sem_acentos
        and not any(p in texto for p in PALAVRAS_CANCELAMENTO)
        and (
            "OBJETO DA GARANTIA" in texto
            or "CREDOR/ FIDUCIARIO" in texto_sem_acentos
            or "CREDORA/FIDUCIARIA" in texto_sem_acentos
            or "PROPRIEDADE FIDUCIARIA" in texto_sem_acentos
            or "EM ALIENACAO FIDUCIARIA" in texto_sem_acentos
        )
    ):
        return ("ÔNUS", True)

    if (
        "HIPOTECA" in texto_sem_acentos
        and not any(p in texto for p in PALAVRAS_CANCELAMENTO)
        and not (
            "LIBERACAO E SUBSTITUICAO DA AREA HIPOTECADA" in texto_sem_acentos
            or (
                "LIBERADA DA GARANTIA HIPOTECARIA" in texto_sem_acentos
                and "PERMANECENDO HIPOTECADO" in texto_sem_acentos
                and ("DERAM EM GARANTIA" in texto_sem_acentos or "SUBSTITUICAO" in texto_sem_acentos)
            )
        )
        and (
            "DADO EM" in texto_sem_acentos_compacto
            or "DADA EM" in texto_sem_acentos_compacto
            or "EM HIPOTECA" in texto_sem_acentos_compacto
            or re.search(r"\bEM\s+(?:\d{1,2}[AO]?\s+)?(?:E\s+ESPECIAL\s+)?HIPOTECA\b", texto_sem_acentos_compacto)
            or "GARANTIAS HIPOTECARIA" in texto_sem_acentos_compacto
            or "GARANTIA HIPOTECARIA" in texto_sem_acentos_compacto
            or "CEDULA RURAL HIPOTECARIA" in texto_sem_acentos_compacto
            or "CEDULA HIPOTECARIA" in texto_sem_acentos_compacto
        )
    ):
        return ("ÔNUS", True)

    # A liberação parcial com substituição de garantia não cria novo ônus
    # e também não extingue a hipoteca anterior, que permanece ativa sobre
    # o remanescente até um cancelamento posterior expresso.
    if (
        "LIBERAÇÃO E SUBSTITUIÇÃO DA ÁREA HIPOTECADA" in texto
        or (
            "LIBERADA DA GARANTIA HIPOTECÁRIA" in texto
            and "PERMANECENDO HIPOTECADO" in texto
            and ("DERAM EM GARANTIA" in texto or "SUBSTITUIÇÃO" in texto)
        )
    ):
        return ("IGNORAR", False)
    
    for p in PALAVRAS_IGNORAR_FORTE:
        if p in texto:
            return ("IGNORAR", False)

    melhor_categoria = "DESCONHECIDO"
    melhor_impacta = False
    menor_indice = len(texto)

    for p in PALAVRAS_CANCELAMENTO:
        idx = texto.find(p)
        if idx != -1 and idx < menor_indice:
            menor_indice = idx
            melhor_categoria = "CANCELAMENTO"
            melhor_impacta = False

    for p in PALAVRAS_PUBLICIDADE_FORTE:
        idx = texto.find(p)
        if idx != -1 and idx < menor_indice:
            menor_indice = idx
            melhor_categoria = "PUBLICIDADE"
            melhor_impacta = False

    for regra in regras_aprendidas or []:
        chave = regra.get("expressao_normalizada") or regra.get("expressao")
        if not chave:
            continue
        chave = _sem_acentos(str(chave).upper())
        chave = re.sub(r"\s+", " ", chave).strip()
        idx = texto_sem_acentos_compacto.find(chave)
        if idx != -1 and idx < menor_indice:
            menor_indice = idx
            melhor_categoria = regra["categoria"]
            melhor_impacta = bool(regra["impacta_resultado"])

    for chave, dados in REGRAS.items():
        idx = texto.find(chave)
        if idx != -1 and idx < menor_indice:
            menor_indice = idx
            melhor_categoria = dados["categoria"]
            melhor_impacta = dados["impacta"]

    return (melhor_categoria, melhor_impacta)
