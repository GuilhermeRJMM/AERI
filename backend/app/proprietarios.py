import re
import unicodedata

def limpar_nome(nome):
    nome = ''.join(c for c in unicodedata.normalize('NFD', nome) if unicodedata.category(c) != 'Mn')
    nome = nome.upper().strip()
    nome = re.sub(r'^(O\s+)?ESPOLIO DE\s+', '', nome)
    nome = re.sub(r'^SUCESSORES DE\s+', '', nome)
    return nome

def padronizar_chave(cpf, nome):
    cpf_limpo = re.sub(r'\D', '', cpf)
    if len(cpf_limpo) >= 11:
        return cpf_limpo[:11] 
    elif len(cpf_limpo) >= 9: 
        return cpf_limpo
    return limpar_nome(nome)

def parse_percent(texto):
    m1 = re.search(r'IMÓVEL\s*:\s*(\d+(?:,\d+)?)%', texto, re.IGNORECASE)
    if m1: return float(m1.group(1).replace(',', '.'))
    
    m2 = re.search(r'proporção de\s*(\d+(?:,\d+)?)%', texto, re.IGNORECASE)
    if m2: return float(m2.group(1).replace(',', '.'))
        
    if re.search(r'(totalidade|integralidade|100%|o imóvel constante|o imóvel objeto)', texto, re.IGNORECASE):
        return 100.0
        
    return 100.0

def extrair_bloco(texto, tipo):
    if tipo == "ADQUIRENTE":
        m = re.search(r'ADQUIRENTE[S]?\s*:(.*?)(?:IMÓVEL\s*:|ORIGEM\s*:|FORMA DO TÍTULO)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip()

        m = re.search(r'DONAT[AÁ]RIO[S]?\s*:(.*?)(?=\bOBJETO\s*:|\bORIGEM\s*:|\bFORMA DO TÍTULO)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip()

        m = re.search(r'adquirido por\s+(.*?)(?:;\s*por compra|;\s*pelo preço|em pagamento)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip()

        m = re.search(r'coube\s+a[os]?\s+(.*?)(?:;\s*em pagamento|,\s*em pagamento|;\s*a totalidade|;\s*por aquisi[çc][ãa]o|,\s*por aquisi[çc][ãa]o|;\s*conforme|,\s*conforme)', texto, re.I | re.DOTALL)
        if m:
            t = m.group(1).strip()
            t = re.sub(r'^(?:o\s+|a\s+|os\s+|as\s+)?(?:único\s+)?(?:herdeiro[s]?|cessionário[s]?|filho[s]?|viúva)?\s*(?:e\s+cessionári[oa]s?)?\s*[:\-]?\s*', '', t, flags=re.I).strip()
            return t

    elif tipo == "TRANSMITENTE":
        m = re.search(r'TRANSMITENTE[S]?\s*:(.*?)(?:ADQUIRENTE[S]?\s*:|IMÓVEL\s*:)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip()

        m = re.search(r'DOADOR[ES]?\s*:(.*?)(?=\bINTERVENIENTE\s*:|\bDONAT[AÁ]RIO\s*:|\bOBJETO\s*:)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip()

        m = re.search(r'por compra feita a[os]?\s+(.*?)(?:;|pelo preço)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip()

        m = re.search(r'deixados por falecimento\s+(?:de\s+)?(.*?)(?:,|\s+julgado)', texto, re.I | re.DOTALL)
        if m: return m.group(1).strip()

    return ""

def extrair_pessoas(texto_bloco):
    pessoas = []
    if not texto_bloco: return pessoas

    partes_conjuge = re.split(r'\s+e\s+(?:seu\s+c[oô]njuge|sua\s+mulher|seu\s+marido)\s+', texto_bloco, flags=re.I)
    if len(partes_conjuge) == 2:
        for parte in partes_conjuge:
            parte = parte.strip()
            nome_match = re.match(r'^([^,]+)', parte)
            cpf_match = re.search(r'(?:CPF|CIC)[^\d]*([\d]{3}\.[\d]{3}\.[\d]{3}-[\d]{2})', parte, re.I)
            if not cpf_match:
                cpf_match = re.search(r'(?:CPF|CIC|MF)[^\d]*([\d\.\-]{9,18})', parte, re.I)
            nome = nome_match.group(1).strip() if nome_match else "DESCONHECIDO"
            cpf = cpf_match.group(1).strip() if cpf_match else "CPF NÃO INFORMADO"
            pessoas.append({"nome": nome, "cpf": cpf})
        return pessoas

    partes = re.split(r'(?:^|\s+|;)(?:\d{1,3}|[IVX]+)[\)\-]\s+', texto_bloco)
    partes = [p.strip() for p in partes if p.strip()]
    if not partes:
        partes = [texto_bloco]

    for parte in partes:
        nome_match = re.match(r'^([^,]+)', parte)
        cpf_match = re.search(r'(?:CPF|CIC|MF)[^\d]*([\d\.\-]{9,18})', parte, re.I)

        nome = nome_match.group(1).strip() if nome_match else "DESCONHECIDO"
        cpf = cpf_match.group(1).strip() if cpf_match else "CPF NÃO INFORMADO"

        pessoas.append({"nome": nome, "cpf": cpf})

        conj_match = re.search(
            r'comunh[ãa]o\s+universal[^,]*,\s+com\s+([A-ZÀ-Úa-zà-ú][^,]+),.*?(?:CPF|CIC)[^\d]*([\d\.\-]{9,18})',
            parte, re.I | re.DOTALL
        )
        if conj_match:
            pessoas.append({"nome": conj_match.group(1).strip(), "cpf": conj_match.group(2).strip()})

    return pessoas

def extrair_proprietario_inicial(texto_cabecalho):
    m = re.search(r'PROPRIET[AÁ]RI[OA]S?\s*:\s*(.*?)(?=\bORIGEM\b|\bT[IÍ]TULO AQUISITIVO\b|\bREGISTRO ANTERIOR\b|\bO referido [ée] verdade\b|\*NOTA\b|\bProtocolo\b|\bMATR[IÍ]CULA\b)', texto_cabecalho, re.I | re.DOTALL)
    if m:
        return extrair_pessoas(m.group(1).strip())
    return []

def calcular_cadeia_dominial(atos, texto_integral=""):
    estado = {}
    
    # 1. CARREGA O SALDO INICIAL (Ato 0)
    if texto_integral:
        partes = re.split(r'(?:R|AV)[\.\-]\s*0*1\b', texto_integral, maxsplit=1, flags=re.I)
        cabecalho = partes[0]
        
        iniciais = extrair_proprietario_inicial(cabecalho)
        if iniciais:
            fração = 100.0 / len(iniciais)
            for p in iniciais:
                chave = padronizar_chave(p["cpf"], p["nome"])
                estado[chave] = {"nome": p["nome"], "cpf_original": p["cpf"], "proporcao": fração}

    # 2. PROCESSA OS ATOS DE TRANSFERÊNCIA
    atos_transmissao = ["VENDA E COMPRA", "COMPRA E VENDA", "INVENTÁRIO", "PARTILHA", "SOBREPARTILHA", "DOAÇÃO"]
    
    for ato in atos:
        if not any(x in ato.descricao.upper() for x in atos_transmissao):
            continue
        
        percentual_ato = parse_percent(ato.descricao)
        
        bloco_adq = extrair_bloco(ato.descricao, "ADQUIRENTE")
        bloco_transm = extrair_bloco(ato.descricao, "TRANSMITENTE")
        
        adquirentes = extrair_pessoas(bloco_adq)
        transmitentes = extrair_pessoas(bloco_transm)
        
        if not adquirentes:
            continue
            
        percent_por_adq = percentual_ato / len(adquirentes)
        
        # --- SAÍDA DOS TRANSMITENTES (Subtração Matemática com Mega Brain 🧠) ---
        if transmitentes:
            percent_por_transm = percentual_ato / len(transmitentes)
            for t in transmitentes:
                chave_t = padronizar_chave(t["cpf"], t["nome"])
                
                debitou = False
                
                # TENTATIVA 1: Match Exato (CPFs ou Nomes Idênticos)
                for chave_estado in list(estado.keys()):
                    if chave_t == chave_estado:
                        estado[chave_estado]["proporcao"] -= percent_por_transm
                        if estado[chave_estado]["proporcao"] < 0.01:
                            del estado[chave_estado]
                        debitou = True
                        break
                        
                # TENTATIVA 2: Match Parcial Fuzzy (Ex: "José" contido em "José e Francisca")
                if not debitou:
                    for chave_estado in list(estado.keys()):
                        if chave_estado in chave_t or chave_t in chave_estado:
                            estado[chave_estado]["proporcao"] -= percent_por_transm
                            if estado[chave_estado]["proporcao"] < 0.01:
                                del estado[chave_estado]
                            debitou = True
                            break
                
                # TENTATIVA 3: Wipe-out de Segurança (Limpa a conta se for venda 100% com termos genéricos)
                if not debitou and percentual_ato >= 99.0 and len(transmitentes) == 1:
                    termos_genericos = ["MESMOS", "PROPRIETARIOS", "CASAL", "HERDEIROS", "FALECIMENTO", "OUTROS", " E "]
                    if any(termo in chave_t for termo in termos_genericos):
                        estado.clear() # Zera a conta de todo mundo para o novo dono assumir
        
        # --- ENTRADA DOS ADQUIRENTES (Crédito) ---
        for a in adquirentes:
            chave_a = padronizar_chave(a["cpf"], a["nome"])
            if chave_a not in estado:
                estado[chave_a] = {"nome": a["nome"], "cpf_original": a["cpf"], "proporcao": 0.0}
            estado[chave_a]["proporcao"] += percent_por_adq
            
    # 3. FORMATA A SAÍDA
    resultado = []
    for chave, dados in estado.items():
        if dados["proporcao"] > 0.01:
            prop_formatada = f"{dados['proporcao']:.2f}%".replace('.', ',')
            if prop_formatada.endswith(",00%"):
                prop_formatada = prop_formatada.replace(",00%", "%")
                
            resultado.append({
                "nome": dados["nome"],
                "cpf": dados["cpf_original"],
                "proporcao": prop_formatada
            })
            
    return resultado