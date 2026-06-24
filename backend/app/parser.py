import re

def separar_atos(texto):
    # Agora exige que o R/AV esteja no início de uma linha ou do texto
    # Ignora os traços "---" e espaços que os escreventes colocam antes
    padrao = r'(?:^|\n)[ \t\-]*((?:R|AV)[\.\-]\s*\d+[\.\-].*?)(?=(?:\n[ \t\-]*(?:R|AV)[\.\-]\s*\d+[\.\-])|\Z)'
    
    encontrados = re.findall(padrao, texto, flags=re.DOTALL | re.IGNORECASE)

    atos = []

    for bloco in encontrados:
        codigo_match = re.search(r'((?:R|AV)[\.\-]\s*\d+)', bloco, re.IGNORECASE)
        
        if codigo_match:
            codigo = codigo_match.group(1).upper().replace('-', '.').replace(' ', '')
        else:
            codigo = "SEM_CODIGO"

        atos.append({
            "codigo": codigo,
            "texto": bloco.strip()
        })

    return atos