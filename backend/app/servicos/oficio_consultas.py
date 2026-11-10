"""Contrato de consulta externa: não altera o cadastro nem a conferência de INs."""
import re
from datetime import date, datetime, timedelta, timezone

MAX_CORPO = 1_000_000
CAMPOS_ITEM = {'protocolo', 'prenotacao', 'status', 'dataStatus', 'dataPedido', 'prazoPurga'}
CAMPOS_CAPTURA = {'versao', 'fonte', 'cartorio', 'consultadoEm', 'completo', 'total', 'paginas', 'itens'}


def texto_seguro(valor, limite, *, vazio=False):
    if (not isinstance(valor, str) or len(valor) > limite
            or (not vazio and not valor.strip())
            or re.search(r'[\x00-\x1f\x7f<>]', valor)):
        raise ValueError('Texto inválido na consulta.')


def validar_captura(dados, cartorio, *, agora=None):
    """Recusa recortes parciais, campos extras e outra serventia; sem correções silenciosas."""
    agora = agora or datetime.now(timezone.utc)
    if (not isinstance(dados, dict) or set(dados) != CAMPOS_CAPTURA
            or not isinstance(cartorio, str) or not re.fullmatch(r'[1-9][0-9]{0,9}', cartorio)
            or dados['cartorio'] != cartorio or dados['fonte'] != 'oficioeletronico.com.br'
            or type(dados['versao']) is not int or dados['versao'] != 1
            or dados['completo'] is not True):
        raise ValueError('Origem, versão ou cartório da consulta inválido.')
    try:
        instante = datetime.fromisoformat(dados['consultadoEm'])
        if (instante.tzinfo is None or instante < agora - timedelta(hours=24)
                or instante > agora + timedelta(minutes=10)):
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError('Faça uma nova consulta: data ausente, futura ou antiga.') from None
    itens, paginas, total = dados['itens'], dados['paginas'], dados['total']
    if (type(total) is not int or not 1 <= total <= 2000 or not isinstance(itens, list)
            or len(itens) != total or not isinstance(paginas, list) or not 1 <= len(paginas) <= 100):
        raise ValueError('Quantidade de itens ou páginas inválida.')
    soma = 0
    for numero, pagina in enumerate(paginas, 1):
        if (not isinstance(pagina, dict) or set(pagina) != {'pagina', 'itens'}
                or type(pagina['pagina']) is not int or pagina['pagina'] != numero
                or type(pagina['itens']) is not int or not 1 <= pagina['itens'] <= 10
                or (numero < len(paginas) and pagina['itens'] != 10)):
            raise ValueError('Paginação incompleta ou fora de sequência.')
        soma += pagina['itens']
    if soma != total:
        raise ValueError('Total da paginação diverge dos itens.')
    vistos = set()
    for item in itens:
        if not isinstance(item, dict) or set(item) != CAMPOS_ITEM:
            raise ValueError('Campos inesperados na consulta.')
        protocolo = item['protocolo']
        if (not isinstance(protocolo, str) or not re.fullmatch(r'IN[0-9]{8}[A-Z]', protocolo)
                or protocolo in vistos):
            raise ValueError('Protocolo inválido ou duplicado.')
        vistos.add(protocolo)
        if not isinstance(item['prenotacao'], str) or not re.fullmatch(r'[0-9]{0,12}', item['prenotacao']):
            raise ValueError('Prenotação inválida.')
        texto_seguro(item['status'], 180)
        texto_seguro(item['prazoPurga'], 80, vazio=True)
        for campo in ('dataStatus', 'dataPedido'):
            valor = item[campo]
            if valor is not None:
                if not isinstance(valor, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', valor):
                    raise ValueError('Data inválida.')
                date.fromisoformat(valor)
    return dados
