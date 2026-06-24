import re

def aplicar_cancelamentos(atos):
    indice = {}
    
    for ato in atos:
        indice[ato.codigo] = ato
        
        match = re.search(r'(R|AV)[\.\-]\s*0*(\d+)', ato.codigo, re.IGNORECASE)
        if match:
            chave_normalizada = f"{match.group(1).upper()}.{match.group(2)}"
            indice[chave_normalizada] = ato

    for ato in atos:
        if ato.categoria == "CANCELAMENTO":
            texto = ato.descricao.upper()
            
            alvos = re.finditer(r'(R|AV)[\.\-]\s*0*(\d+)', texto)
            
            for alvo in alvos:
                tipo = alvo.group(1).upper()
                numero = alvo.group(2)
                chave_buscada = f"{tipo}.{numero}"
                
                # TENTATIVA 1: Busca exata (Ex: Procura R.4 e acha R.4)
                if chave_buscada in indice and indice[chave_buscada].codigo != ato.codigo:
                    ato_alvo = indice[chave_buscada]
                    ato_alvo.status = "CANCELADO"
                    ato_alvo.cancelado_por = ato.codigo
                    ato_alvo.impacta_resultado = False
                else:
                    # TENTATIVA 2: Busca por erro de digitação (Inverte R e AV)
                    tipo_inverso = "AV" if tipo == "R" else "R"
                    chave_inversa = f"{tipo_inverso}.{numero}"
                    
                    if chave_inversa in indice and indice[chave_inversa].codigo != ato.codigo:
                        ato_alvo = indice[chave_inversa]
                        ato_alvo.status = "CANCELADO"
                        ato_alvo.cancelado_por = ato.codigo
                        ato_alvo.impacta_resultado = False

    return atos