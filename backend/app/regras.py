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
    "ASSUNÇÃO": {"categoria": "ÔNUS", "impacta": True},
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
    "DOAÇÃO": {"categoria": "IGNORAR", "impacta": False},
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


def _sem_acentos(texto):
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")

def classificar(texto):
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

    for chave, dados in REGRAS.items():
        idx = texto.find(chave)
        if idx != -1 and idx < menor_indice:
            menor_indice = idx
            melhor_categoria = dados["categoria"]
            melhor_impacta = dados["impacta"]

    return (melhor_categoria, melhor_impacta)
