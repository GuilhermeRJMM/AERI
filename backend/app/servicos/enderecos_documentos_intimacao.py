"""Endereços das minutas, sem modificar a descrição registral ou os originais."""
import json
import re
from urllib.parse import quote
from urllib.request import urlopen

from backend.app.servicos.documentos_intimacao import _nome_para_comparacao


def _normal(v):
    s = _nome_para_comparacao(str(v))
    s = re.sub(r'\b(?:avda|av)\b\.?\s*', 'avenida ', s)
    s = re.sub(r'\bjd\.?\s*', 'jardim ', s)
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def endereco_de_morrinhos(endereco):
    s = _nome_para_comparacao(endereco)
    if re.search(r'\bmorrinhos\s*[-/,]\s*(?!go\b)[a-z]{2}\b', s):
        return False
    return bool(re.search(r'\bmorrinhos\s*[-/,]\s*go\b', s) or
                re.search(r'\bmunicipio de morrinhos\b(?!\s+(?:do|de|ceara))', s))


def consultar_viacep(logradouro):
    # Host fixo e componentes codificados: não aceitar URL fornecida pelo PDF.
    url = 'https://viacep.com.br/ws/GO/Morrinhos/' + quote(logradouro, safe='') + '/json/'
    try:
        with urlopen(url, timeout=3) as r:
            bruto = r.read(256_001)
            if len(bruto) > 256_000:
                return []
            dados = json.loads(bruto)
        return dados[:50] if isinstance(dados, list) else []
    except (OSError, ValueError, TimeoutError):
        return []


def compactar_endereco(endereco, *, descricao_abertura=False):
    s = re.sub(r'\s+', ' ', str(endereco or '')).strip(' ,;.')
    s = re.sub(r'\bCEP\s*:?\s*[\d. -]*', '', s, flags=re.I).strip(' ,;.')
    s = re.split(r',\s*(?:com\s+(?:a\s+)?[áa]rea|com as seguintes medidas|sendo\s*:)', s, maxsplit=1, flags=re.I)[0]
    if descricao_abertura:
        s = re.sub(r'\bnesta\s+cidade\b', 'Morrinhos-GO', s, flags=re.I)
    s = re.sub(r'\bMORRINHOS\s*[/,-]\s*GO\b', 'Morrinhos-GO', s, flags=re.I)
    s = re.sub(r'\bAV(?:ENIDA|DA)?\.?\s*,?\s+(?=[A-ZÀ-Ü])', 'Avenida ', s, flags=re.I)
    # Separar complemento de numeração/quadra/lote sem remover conteúdo.
    s = re.sub(r'(?<!da)(?<!do)\s+(QUADRA|LOTE)\s+', lambda m:', '+m[1].title()+' ', s, flags=re.I)
    s = re.sub(r'\b(JARDIM|SETOR|VILA)\b', lambda m:m[1].title(), s, flags=re.I)
    return re.sub(r',\s*,', ',', s).strip(' ,;.')


def _logradouro_bairro(endereco):
    m = re.search(r'\b(Avenida|Av\.?|Rua|Alameda|Praça|Estrada|Rodovia)\s+([^,]+)', endereco, re.I)
    if not m:
        return '', ''
    logradouro = m[1]+' '+re.split(r'\s+n[.º°o]*\s*\d', m[2], maxsplit=1, flags=re.I)[0].strip()
    bairro = re.search(r'\b((?:Jardim|Jd\.?|Setor|Vila|Parque|Bairro|Centro|Residencial)\b[^,]*)', endereco, re.I)
    return logradouro, bairro[1].strip() if bairro else ''


def _bairro_compativel(informado, oficial):
    a, b = _normal(informado).split(), _normal(oficial).split()
    # Abreviação por inicial ("Jardim V Cruz"), nunca distância/fuzzy.
    return a == b or (len(a) == len(b) and sum(len(t)>1 for t in a)>=2 and
                     all(x == y or len(x)==1 and y.startswith(x) for x,y in zip(a,b)))


def _cep_unico(resultados, logradouro, bairro):
    encontrados = set()
    if not bairro:
        return ''  # A mesma rua pode atravessar vários bairros/CEPs.
    for r in resultados:
        if not isinstance(r, dict) or r.get('erro') or r.get('uf') != 'GO' or _normal(r.get('localidade','')) != 'morrinhos':
            continue
        if _normal(r.get('logradouro','')) != _normal(logradouro) or not _bairro_compativel(bairro, r.get('bairro','')):
            continue
        # Não escolher um segmento por lado/paridade/numeração sem regra confirmada.
        if r.get('complemento') or r.get('unidade'):
            continue
        cep = re.sub(r'\D', '', r.get('cep',''))
        if len(cep) == 8:
            encontrados.add(cep)
    if len(encontrados) != 1:
        return ''
    c = next(iter(encontrados))
    return f'{c[:2]}.{c[2:5]}-{c[5:]}'


def preparar_enderecos(dados, *, buscar=None):
    dados.setdefault('avisos', [])
    dados.setdefault('origens', {})
    buscar = buscar or consultar_viacep
    cache = {}
    def formatar(original, abertura=False):
        s = compactar_endereco(original, descricao_abertura=abertura)
        cep = ''
        if endereco_de_morrinhos(s):
            logradouro, bairro = _logradouro_bairro(s)
            if logradouro and bairro:
                chave = _normal(logradouro)
                if chave not in cache and len(cache) < 6:
                    cache[chave] = buscar(logradouro)
                cep = _cep_unico(cache.get(chave, []), logradouro, bairro)
                if cep:
                    bairros = {r.get('bairro','') for r in cache.get(chave, []) if isinstance(r,dict)
                               and r.get('uf')=='GO' and _normal(r.get('localidade',''))=='morrinhos'
                               and _normal(r.get('logradouro',''))==_normal(logradouro)
                               and _bairro_compativel(bairro,r.get('bairro',''))
                               and re.sub(r'\D','',r.get('cep',''))==re.sub(r'\D','',cep)}
                    if len(bairros)==1:
                        s = s.replace(bairro, next(iter(bairros)), 1)
                    else:
                        cep = ''
        if not cep:
            dados['avisos'].append('CEP não confirmado para um endereço. Campo deixado em branco; não foi usado CEP genérico.')
        return s+', CEP: '+(cep or '________')
    original = dados.get('enderecoImovel', '')
    if original:
        fontes = dados.get('origens', {}).get('enderecoImovel', {})
        abertura = 'descricao_abertura_matricula' in fontes
        dados['enderecoImovel'] = formatar(original, abertura)
        dados['origens'].setdefault('enderecoFormatado', {})['descricao_anterior'] = original
    todos = dados.get('enderecosDoOficio', dados.get('enderecos', []))
    locais, excluidos = [], []
    for endereco in todos:
        if endereco_de_morrinhos(endereco):
            novo = formatar(endereco)
            if novo not in locais:
                locais.append(novo)
        else:
            excluidos.append(endereco)
    dados['enderecosPrimeiraNotificacao'] = locais
    dados['enderecosForaDaPrimeiraNotificacao'] = excluidos
    dados['origens']['enderecosPrimeiraNotificacao'] = {'oficio_e_anexos': locais}
    if excluidos:
        dados['avisos'].append(f'{len(excluidos)} endereço(s) de outra localidade ou sem município confirmado não entram na primeira notificação de Morrinhos.')
    if not locais:
        dados['avisos'].append('Não há endereço de Morrinhos confirmado para a primeira notificação. Confira o Ofício; não foi usada outra cidade.')
    return dados
