"""Complemento somente leitura: fontes identificadas, sem praticar atos na Tri7."""
import html
import re
from datetime import date
from hashlib import sha256

from backend.app.analise.onus import processar_atos
from backend.app.servicos import documentos_intimacao as doc
from backend.app.servicos.tri7 import cliente_tri7, ErroTri7


def _normal(v):
    return doc._nome_para_comparacao(str(v))


def _registro(v):
    m = re.fullmatch(r'R[.\s-]*0*(\d+)', str(v).strip(), re.I)
    return f'R.{int(m[1]):02d}' if m else ''


def _data(v):
    texto = _normal(v)
    m = re.search(r'\b(\d{2})[./](\d{2})[./](\d{4})\b', texto)
    if not m:
        meses = 'janeiro fevereiro marco abril maio junho julho agosto setembro outubro novembro dezembro'.split()
        extenso = re.search(r'\b(\d{1,2}) de (\w+) de (\d{4})\b', texto)
        if not extenso or extenso[2] not in meses:
            return ''
        partes = (int(extenso[3]), meses.index(extenso[2])+1, int(extenso[1]))
    else:
        partes = (int(m[3]), int(m[2]), int(m[1]))
    try:
        return date(*partes).strftime('%d/%m/%Y')
    except ValueError:
        return ''


def _contrato_no_ato(numero, texto):
    procurado = doc._digitos(numero)
    tokens = re.findall(r'\b\d[\d./-]{3,45}\d\b', texto)
    iguais = [t for t in tokens if doc._digitos(t) == procurado or
              len(procurado) >= 10 and len(doc._digitos(t)) == len(procurado)+1 and doc._digitos(t).startswith(procurado)]
    if iguais:
        return iguais[0]
    # Grupo/cota não é o número do contrato de adesão: manter a referência original.
    grupo = re.fullmatch(r'(\d+)\s*/\s*(\d+)', str(numero))
    if grupo:
        for cota, g in re.findall(r'Cota\s+n[.º°o\s]*\s*(\d+)\s+do\s+Grupo\s+n[.º°o\s]*\s*(\d+)', texto, re.I):
            if int(grupo[1]) == int(g) and int(grupo[2]) == int(cota):
                return numero
    return ''


def _fonte(dados, campo, valor, origem):
    dados.setdefault('origens', {}).setdefault(campo, {})[origem] = valor


def _atribuir(dados, campo, valor, origem):
    if not valor:
        return
    anterior = dados.get(campo, '')
    _fonte(dados, campo, valor, origem)
    if any(i.get('campo') == campo for i in dados['inconsistencias']):
        return
    if anterior and _normal(anterior) != _normal(valor):
        dados['inconsistencias'].append(dict(campo=campo, fontes={'anexos':anterior, origem:valor}))
        dados[campo] = ''
    else:
        dados[campo] = valor


def _complementar_matricula(dados, resposta):
    numero = doc._digitos(dados['matricula'])
    if doc._digitos(str(resposta.get('numero_matricula', ''))) != numero:
        dados['avisos'].append('A Tri7 devolveu outra matrícula. Complemento recusado.')
        return
    texto = html.unescape(re.sub(r'<[^>]+>', ' ', resposta.get('texto', '')))
    if not texto:
        return
    dados['consultaAutomatica']['matriculaConsultada'] = True
    dados['consultaAutomatica']['textoHash'] = sha256(texto.encode()).hexdigest()
    contrato = dados.get('contrato', {}).get('numero', '')
    cnpj = dados.get('credor', {}).get('cnpj', '')
    cpfs = [p.get('cpf', '') for p in dados.get('devedores', []) if p.get('cpf')]
    candidatos = []
    for ato in processar_atos(texto):
        if not ato.codigo.startswith('R.') or 'alienacao fiduciaria' not in _normal(ato.descricao[:500]):
            continue
        partes = re.search(r'\bdevedor(?:a|es|as|\(es\)|\(a\))?\s*(?:/\s*fiduciante(?:s)?)?\s*:\s*(.*?)\bcredor(?:a|es|as)?\s*(?:[/\s]+fiduciari[oa]s?)?\s*:', _normal(ato.descricao), re.S)
        documentos_devedores = {doc._digitos(v) for v in re.findall(r'\d[\d./-]{9,22}\d', partes[1])} if partes else set()
        trecho_credor = _normal(ato.descricao)[partes.end():partes.end()+500] if partes else ''
        documentos_credor = {doc._digitos(v) for v in re.findall(r'\d[\d./-]{9,22}\d', trecho_credor)}
        if not contrato or not cnpj or cnpj not in documentos_credor or not cpfs or not all(p in documentos_devedores for p in cpfs):
            continue
        referencia = _contrato_no_ato(contrato, ato.descricao)
        if referencia:
            candidatos.append((ato, referencia))
    indicado = _registro(dados.get('registroIndicado', ''))
    if indicado:
        candidatos = [(a,n) for a,n in candidatos if _registro(a.codigo) == indicado]
    if len(candidatos) != 1:
        dados['avisos'].append('Garantia não localizada de forma única pelo contrato, credor e devedores. Confira a exceção; não foi escolhido o último R.')
        return
    ato, referencia = candidatos[0]
    if ato.status != 'ATIVO':
        dados['avisos'].append('A garantia correspondente consta cancelada no analisador. Não foi utilizada para preencher os documentos.')
        return
    origem = f'matricula:{numero}:{_registro(ato.codigo)}'
    dados['consultaAutomatica']['garantiaConfirmada'] = True
    _atribuir(dados, 'registroGarantia', _registro(ato.codigo), origem)
    _fonte(dados, 'contrato', referencia, origem)
    dados['contrato']['numero'] = referencia
    forma = re.search(r'FORMA DO T[IÍ]TULO\s*:\s*(.{1,1800}?)\s*(?:,?\s+datad[oa]\s+de\s+)', ato.descricao, re.I|re.S)
    if forma:
        titulo = re.sub(r'\s+', ' ', forma[1]).strip()
        # Excluir número, escritura pública e fundamentos posteriores do título literal.
        titulo = re.split(r'\s+n[.º°o\s]*\s*\d', titulo, maxsplit=1, flags=re.I)[0].rstrip(' ,;.')
        _atribuir(dados, 'titulo', titulo, origem)
        data_titulo = _data(ato.descricao[forma.end():forma.end()+100])
        _atribuir(dados, 'dataTituloAutuacao', data_titulo, origem)
        if data_titulo:
            anterior = dados['contrato'].get('data', '')
            _fonte(dados, 'dataContrato', data_titulo, origem)
            if any(i.get('campo') == 'dataContrato' for i in dados['inconsistencias']):
                pass
            elif anterior and anterior != data_titulo:
                dados['inconsistencias'].append(dict(campo='dataContrato', fontes={'oficio':anterior, origem:data_titulo}))
                dados['contrato']['data'] = ''
            else:
                dados['contrato']['data'] = data_titulo
    if not dados.get('enderecoImovel'):
        imovel = re.search(r'IM[ÓO]VEL\s*:\s*(.*?)(?=\bPROPRIET[ÁA]RI[OA]S?\s*:|\bORIGEM\s*:|\n\s*R[. -])', texto, re.S|re.I)
        if imovel and len(imovel[1]) < 2000:
            _atribuir(dados, 'enderecoImovel', re.sub(r'\s+', ' ', imovel[1]).strip(' .'), 'descricao_abertura_matricula')
    outorga = re.search(r'OUTORGA DE PROCURA[CÇ][ÕO]ES\s*:.{0,100}?item\s+(\d+)', ato.descricao, re.I|re.S)
    if outorga:
        _atribuir(dados, 'clausula', outorga[1]+' OUTORGA DE PROCURAÇÕES', origem)


def _complementar_protocolo(dados, resposta):
    p = resposta.get('protocolo', {})
    if doc._digitos(str(p.get('protocolo_numero', ''))) != doc._digitos(dados.get('protocoloTri7', '')):
        dados['avisos'].append('A Tri7 devolveu outro protocolo. Selos recusados.')
        return
    dados['consultaAutomatica']['protocoloConsultado'] = True
    selos = set()
    for item in resposta.get('itens_do_pedido', []):
        imovel = item.get('dados_imovel') or {}
        if not _normal(item.get('natureza_formal_descricao', '')).startswith('intimacao'):
            continue
        if doc._digitos(str(imovel.get('numero_registro', ''))) != doc._digitos(dados.get('matricula', '')):
            continue
        for selo in item.get('selos') or []:
            valor = str(selo.get('selo', ''))
            if re.fullmatch(r'\d{15,40}', valor):
                selos.add(valor)
    if len(selos) == 1:
        _atribuir(dados, 'selo', next(iter(selos)), 'protocolo:ato_intimacao')
    else:
        dados['avisos'].append('Selo da intimação ainda não emitido ou não identificado de forma única. Não foi usado o selo da prenotação nem da garantia antiga.')


def complementar_preparacao(dados, responsavel='', *, cliente=None):
    """Sem SQL ou emissões: complemento compartilhado pelo upload e executor."""
    dados.setdefault('origens', {})
    dados.setdefault('inconsistencias', [])
    dados.setdefault('avisos', [])
    dados['consultaAutomatica'] = dict(matriculaConsultada=False, protocoloConsultado=False, garantiaConfirmada=False)
    nome = ' '.join(str(responsavel or '').split())
    if len(nome.split()) >= 2 and not re.search(r'administra|sistema|suporte', nome, re.I):
        _atribuir(dados, 'signatario', nome, 'cadastro_usuario:responsavel_sugerido')
    try:
        cliente = cliente or cliente_tri7()
    except (ErroTri7, ValueError, RuntimeError):
        dados['avisos'].append('Consulta automática à Tri7 indisponível; confira os campos pendentes.')
        return dados
    for campo, metodo, aplicar in [('matricula', cliente.buscar_texto_matricula, _complementar_matricula),
                                    ('protocoloTri7', cliente.buscar_protocolo_completo, _complementar_protocolo)]:
        if dados.get(campo):
            try:
                aplicar(dados, metodo(dados[campo]))
            except (ErroTri7, ValueError, RuntimeError):
                dados['avisos'].append(f'Não foi possível complementar {campo} pela Tri7. Dados dos anexos preservados; confira a exceção.')
    return dados
