"""Comparações de valores, sem alterar a grafia dos documentos originais."""
import re
from decimal import Decimal, InvalidOperation


def designativo(valor):
    """04 = 4; 09-A = 9-A, mas 9-A != 9-B e quadra C != D."""
    return re.sub(r'^0+(?=\d)', '', re.sub(r'\s+', '', str(valor)).upper())


def area_m2(valor):
    """Área explícita em m²/m2/ha, calculada com decimal exato."""
    m = re.fullmatch(r'\s*(\d[\d.,]*)\s*(m[²2]|ha)\s*', str(valor), re.I)
    if not m:
        return None
    numero, unidade = m.groups()
    if ',' in numero:
        if not re.fullmatch(r'(?:\d+|\d{1,3}(?:\.\d{3})+),\d+', numero):
            return None
        numero = numero.replace('.', '').replace(',', '.')
    elif re.fullmatch(r'\d{1,3}(?:\.\d{3})+', numero):
        numero = numero.replace('.', '')
    elif not re.fullmatch(r'\d+(?:\.\d+)?', numero):
        return None
    try:
        return Decimal(numero) * (10000 if unidade.lower() == 'ha' else 1)
    except InvalidOperation:
        return None


def areas_iguais(a, b):
    x, y = area_m2(a), area_m2(b)
    return x is not None and y is not None and x == y
