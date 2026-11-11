"""Importação mecânica dos esquemas oficiais; nunca executada pelo servidor.

Sem argumentos apenas confere a fonte pública. --instalar copia os JSONs
intactos e regenera os wrappers JS. A revisão e os testes precedem o deploy.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request
import zipfile

PORTAL = 'https://ridigital.org.br/Suporte/frmITNS.aspx'
VERSAO = '1.3.0'
REPOSITORIO = '/ONR-SAEC/35ce965a-d703-4a4d-b8ce-9f5486a2294b/_apis/git/repositories/7a360f55-6d98-4e05-8bc4-6171323d67fd/items'
SCHEMAS = Path(__file__).resolve().parents[1] / 'backend/static/mapa_onr/schemas'


def baixar(url, limite=8_000_000):
    p=urllib.parse.urlsplit(url)
    if p.scheme!='https' or not (
        (p.netloc=='ridigital.org.br' and p.path=='/Suporte/frmITNS.aspx')
        or (p.netloc=='dev.azure.com' and p.path==REPOSITORIO)
    ):
        raise ValueError('A origem não corresponde à fonte oficial esperada.')
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Analisador-RGI-schema-review'}),timeout=30) as r:
        final=urllib.parse.urlsplit(r.geturl())
        if final.scheme!='https' or final.netloc!=p.netloc:
            raise ValueError('Redirecionamento inesperado da fonte oficial.')
        b=r.read(limite+1)
    if len(b)>limite: raise ValueError('Pacote excede o limite da importação.')
    return b


def obter():
    pagina=baixar(PORTAL).decode('utf-8')
    catalogo=re.search(r"var ITNJsonUrl = '([^']+)'",pagina).group(1)
    itn=next(i for i in json.loads(baixar(catalogo)) if i['ITN']=='ITN 003')
    anexo=next(a for a in itn['lista_anexos'] if 'JSON Schema' in a['titulo_anexo'])
    ativo=next(v for v in anexo['versoes'] if v['status']=='Ativo')
    pacote=baixar(ativo['link'])
    manifesto={'portal':PORTAL,'catalogo':catalogo,'pacote':ativo['link'],
        'versao':VERSAO,'data_lancamento':ativo['data_lancamento'],
        'sha256_pacote':hashlib.sha256(pacote).hexdigest(),'arquivos':{}}
    arquivos={}
    with zipfile.ZipFile(io.BytesIO(pacote)) as z:
        for plural in ['rurais','urbanos']:
            nome=f'imoveis-{plural}-onr.schema.json'
            membros=[i for i in z.infolist() if i.filename.endswith('/'+nome)]
            if len(membros)!=1 or membros[0].file_size>5_000_000:
                raise ValueError('Conteúdo inesperado no pacote de esquemas.')
            bruto=z.read(membros[0]);d=json.loads(bruto.decode('utf-8-sig'))
            if d.get('properties',{}).get('version',{}).get('const')!=VERSAO:
                raise ValueError('Nova versão oficial: revisar antes de importar.')
            arquivos[nome]=bruto
            manifesto['arquivos'][nome]={'sha256':hashlib.sha256(bruto).hexdigest(),'id':d['$id']}
    return arquivos,manifesto


def instalar(arquivos,manifesto):
    for tipo,plural in [('rural','rurais'),('urbano','urbanos')]:
        nome=f'imoveis-{plural}-onr.schema.json';p=SCHEMAS/nome
        legado=SCHEMAS/'v1.2.0'/nome
        atual=p.read_bytes()
        if json.loads(atual.decode('utf-8-sig'))['properties']['version']['const']=='1.2.0':
            legado.parent.mkdir(exist_ok=True)
            if legado.exists() and legado.read_bytes()!=atual:
                raise ValueError('O esquema legado existente difere do arquivo original.')
            legado.write_bytes(atual)
        elif not legado.exists():
            raise ValueError('Esquema legado ausente: não prosseguir sem preservar compatibilidade.')
        p.write_bytes(arquivos[nome])
        for sufixo,bruto,global_ in [('',arquivos[nome],'ONR_SCHEMA_'+tipo.upper()),
            ('-legado',legado.read_bytes(),'ONR_SCHEMA_'+tipo.upper()+'_LEGADO')]:
            cab='// Gerado mecanicamente de JSON Schema oficial. Não editar à mão.\n'
            cab+=f'// Fonte e hashes: origem-oficial.json. Legado preservado em v1.2.0/.\n'
            texto=cab+'window.'+global_+' = '+json.dumps(json.loads(bruto.decode('utf-8-sig')),ensure_ascii=False,indent=2)+';\n'
            (SCHEMAS/(tipo+sufixo+'.schema.js')).write_text(texto,encoding='utf-8',newline='\n')
    (SCHEMAS/'origem-oficial.json').write_text(json.dumps(manifesto,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--instalar',action='store_true')
    args=cli.parse_args();arquivos,manifesto=obter()
    if args.instalar: instalar(arquivos,manifesto)
    print(json.dumps({'instalado':args.instalar,'versao':manifesto['versao'],
        'arquivos':manifesto['arquivos']},ensure_ascii=False,indent=2))
