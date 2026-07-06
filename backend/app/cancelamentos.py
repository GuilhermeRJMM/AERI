import re


def _codigo_normalizado(tipo: str, numero: str) -> str:
    return f"{tipo.upper()}.{int(numero)}"


def _codigo_exibicao(tipo: str, numero: str) -> str:
    return f"{tipo.upper()}.{int(numero):02d}"


def _codigo_ato_exibicao(codigo: str) -> str:
    match = re.search(r'(R|AV)[\.\-]\s*0*(\d+)', codigo, re.IGNORECASE)
    return _codigo_exibicao(match.group(1), match.group(2)) if match else codigo


def _registrar_alvo_cancelado(ato_cancelamento, codigo: str) -> None:
    if not hasattr(ato_cancelamento, "cancela_atos"):
        ato_cancelamento.cancela_atos = []
    if codigo not in ato_cancelamento.cancela_atos:
        ato_cancelamento.cancela_atos.append(codigo)


def aplicar_cancelamentos(atos):
    indice = {}
    
    for ato in atos:
        indice[ato.codigo] = ato
        
        match = re.search(r'(R|AV)[\.\-]\s*0*(\d+)', ato.codigo, re.IGNORECASE)
        if match:
            chave_normalizada = _codigo_normalizado(match.group(1), match.group(2))
            indice[chave_normalizada] = ato

    for posicao, ato in enumerate(atos):
        if ato.categoria == "CANCELAMENTO":
            texto = ato.descricao.upper()
            cancelou_alvo_explicito = False
            
            alvos = re.finditer(r'(R|AV)[\.\-]\s*0*(\d+)', texto)
            
            for alvo in alvos:
                tipo = alvo.group(1).upper()
                numero = alvo.group(2)
                chave_buscada = _codigo_normalizado(tipo, numero)
                
                # TENTATIVA 1: Busca exata (Ex: Procura R.4 e acha R.4)
                if chave_buscada in indice and indice[chave_buscada].codigo != ato.codigo:
                    ato_alvo = indice[chave_buscada]
                    ato_alvo.status = "CANCELADO"
                    ato_alvo.cancelado_por = ato.codigo
                    ato_alvo.impacta_resultado = False
                    _registrar_alvo_cancelado(ato, _codigo_ato_exibicao(ato_alvo.codigo))
                    cancelou_alvo_explicito = True
                else:
                    # TENTATIVA 2: Busca por erro de digitação (Inverte R e AV)
                    tipo_inverso = "AV" if tipo == "R" else "R"
                    chave_inversa = f"{tipo_inverso}.{numero}"
                    chave_inversa = _codigo_normalizado(tipo_inverso, numero)
                    
                    if chave_inversa in indice and indice[chave_inversa].codigo != ato.codigo:
                        ato_alvo = indice[chave_inversa]
                        ato_alvo.status = "CANCELADO"
                        ato_alvo.cancelado_por = ato.codigo
                        ato_alvo.impacta_resultado = False
                        _registrar_alvo_cancelado(ato, _codigo_ato_exibicao(ato_alvo.codigo))
                        cancelou_alvo_explicito = True

            # Nos leilões fiduciários negativos, a matrícula pode declarar a
            # extinção da dívida sem repetir o número do registro da garantia.
            # Nesse caso, o alvo é a alienação fiduciária ativa mais recente.
            if (
                not cancelou_alvo_explicito
                and "LEIL" in texto
                and "NEGATIV" in texto
                and "DÍVIDA ORIGINÁRIA" in texto
                and "EXTINT" in texto
            ):
                for ato_anterior in reversed(atos[:posicao]):
                    if (
                        ato_anterior.status == "ATIVO"
                        and "ALIENAÇÃO FIDUCIÁRIA" in ato_anterior.descricao.upper()
                        and ato_anterior.categoria == "ÔNUS"
                    ):
                        ato_anterior.status = "CANCELADO"
                        ato_anterior.cancelado_por = ato.codigo
                        ato_anterior.impacta_resultado = False
                        _registrar_alvo_cancelado(ato, _codigo_ato_exibicao(ato_anterior.codigo))
                        break

    return atos
