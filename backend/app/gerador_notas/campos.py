"""Números de matrícula: validação explícita, sem concatenar identificadores."""
import re

NUMERICOS={'matricula','matricula_confrontante'}
MULTIPLOS={'matriculas_confrontantes'}


def numero(valor):
    if valor is None or valor=='':
        return ''
    if not isinstance(valor,str):
        raise ValueError('Preencha o número da matrícula somente com algarismos.')
    valor=valor.strip()
    # Compatibilidade com o formato antigo de milhar; nunca apagar letras ou
    # separadores arbitrários para não unir duas matrículas em uma terceira.
    if re.fullmatch(r'[0-9]{1,3}(?:\.[0-9]{3})+',valor):
        valor=valor.replace('.','')
    if not re.fullmatch(r'[0-9]{1,12}',valor) or int(valor)==0:
        raise ValueError('Preencha o número da matrícula somente com algarismos.')
    return valor


def preparar_campos(dados):
    def formatado(valor):
        n=numero(valor)
        return format(int(n),',').replace(',','.') if n else ''
    itens=[]
    for item in dados.get('itens',[]):
        valores=dict(item.get('valores',{}))
        for campo in NUMERICOS & valores.keys():
            valores[campo]=formatado(valores[campo])
        for campo in MULTIPLOS & valores.keys():
            valor=valores[campo]
            if isinstance(valor,str):
                # Compatibilidade com documentos antigos; cada segmento é validado.
                valor=re.split(r'\s+e\s+|\s*[,;]\s*',valor.strip()) if valor.strip() else []
            if not isinstance(valor,list) or len(valor)>40:
                raise ValueError('Informe cada matrícula em uma entrada numérica separada.')
            numeros=[formatado(v) for v in valor if v!='']
            valores[campo]=' e '.join(dict.fromkeys(numeros))
        itens.append({**item,'valores':valores})
    return {**dados,'itens':itens}
