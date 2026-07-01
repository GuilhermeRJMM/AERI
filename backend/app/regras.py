# backend/app/regras.py

REGRAS = {
    "AÇÕES/EXISTÊNCIA": {"categoria": "RESTRIÇÃO", "impacta": True},
    "ALIENAÇÃO FIDUCIÁRIA": {"categoria": "ÔNUS", "impacta": True},
    "ANTICRESE": {"categoria": "ÔNUS", "impacta": True},
    "ARROLAMENTO DE BENS": {"categoria": "PUBLICIDADE", "impacta": False},
    "ARRESTO E SEQUESTRO": {"categoria": "ÔNUS", "impacta": True},
    "AÇÃO PREMONITÓRIA": {"categoria": "PUBLICIDADE", "impacta": False},
    "ASSUNÇÃO": {"categoria": "ÔNUS", "impacta": True},
    "CAUÇÃO": {"categoria": "ÔNUS", "impacta": True},
    "CITAÇÃO DE AÇÕES": {"categoria": "RESTRIÇÃO", "impacta": True},
    "REIPERSECUTÓRIAS": {"categoria": "RESTRIÇÃO", "impacta": True},
    "CLÁUSULA RESOLUTIVA": {"categoria": "RESTRIÇÃO", "impacta": True},
    "CLÁUSULAS RESTRITIVAS": {"categoria": "RESTRIÇÃO", "impacta": True},
    "CLÁUSULA RESTRITIVA": {"categoria": "RESTRIÇÃO", "impacta": True},
    "FIDEICOMISSO": {"categoria": "ÔNUS", "impacta": True},
    "IMPENHORABILIDADE": {"categoria": "RESTRIÇÃO", "impacta": True},
    "INALIENABILIDADE": {"categoria": "RESTRIÇÃO", "impacta": True},
    "INCOMUNICABILIDADE": {"categoria": "RESTRIÇÃO", "impacta": True},
    "COMPROMISSO DE COMPRA E VENDA": {"categoria": "ÔNUS", "impacta": True},
    "CONCESSÃO DE DIREITO": {"categoria": "ÔNUS", "impacta": True},
    "CONCESSÃO DE USO": {"categoria": "ÔNUS", "impacta": True},
    "ABERTURA DE CRÉDITO": {"categoria": "ÔNUS", "impacta": True},
    "CONTRATO DE LOCAÇÃO": {"categoria": "RESTRIÇÃO", "impacta": True},
    "CÉDULA DE CRÉDITO": {"categoria": "ÔNUS", "impacta": True},
    "CÉDULA DE PRODUTO RURAL": {"categoria": "ÔNUS", "impacta": True},
    "CÉDULA RURAL": {"categoria": "ÔNUS", "impacta": True},
    "CÉDULAS HIPOTECÁRIAS": {"categoria": "ÔNUS", "impacta": True},
    "CONVENÇÃO DE CONDOMÍNIO": {"categoria": "RESTRIÇÃO", "impacta": True},
    "DEBENTURES": {"categoria": "ÔNUS", "impacta": True},
    "EMPRÉSTIMOS POR OBRIGAÇÕES": {"categoria": "ÔNUS", "impacta": True},
    "DIREITO DE SUPERFÍCIE": {"categoria": "ÔNUS", "impacta": True},
    "ENFITEUSE": {"categoria": "ÔNUS", "impacta": True},
    "EXECUÇÃO": {"categoria": "RESTRIÇÃO", "impacta": True},
    "INDISPONIBILIDADE": {"categoria": "RESTRIÇÃO", "impacta": True},
    "BEM DE FAMÍLIA": {"categoria": "RESTRIÇÃO", "impacta": True},
    "USUFRUTO": {"categoria": "ÔNUS", "impacta": True},
    "NOTA DE CRÉDITO": {"categoria": "ÔNUS", "impacta": True},
    "UTILIZAÇÃO COMPULSÓRIA": {"categoria": "ÔNUS", "impacta": True},
    "PARCERIA AGRÍCOLA": {"categoria": "RESTRIÇÃO", "impacta": True},
    "PENHORA": {"categoria": "ÔNUS", "impacta": True},
    "PENHOR": {"categoria": "ÔNUS", "impacta": True},
    "RENDAS CONSTITUÍDAS": {"categoria": "ÔNUS", "impacta": True},
    "RENOVAÇÃO SIMPLIFICADA": {"categoria": "ÔNUS", "impacta": True},
    "RETROVENDA": {"categoria": "RESTRIÇÃO", "impacta": True},
    "SERVIDÃO": {"categoria": "ÔNUS", "impacta": True},
    "SUB-ROGAÇÃO": {"categoria": "ÔNUS", "impacta": True},
    "TERMO DE SECURITIZAÇÃO": {"categoria": "ÔNUS", "impacta": True},
    "TRASLADO DE HIPOTECA": {"categoria": "ÔNUS", "impacta": True},
    "VÍNCULO": {"categoria": "RESTRIÇÃO", "impacta": True},
    "PACTO COMISSÓRIO": {"categoria": "RESTRIÇÃO", "impacta": True},

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
    "IMÓVEL DE LOCALIZAÇÃO", "PENHOR RURAL/IMÓVEL DE LOCALIZAÇÃO"
]

def classificar(texto):
    texto = texto.upper()

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
