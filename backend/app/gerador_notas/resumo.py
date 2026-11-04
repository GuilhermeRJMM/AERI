"""Explicações editoriais por item, sem criar ou modificar exigências jurídicas."""
import hashlib
import html
import json
from functools import lru_cache

from .catalogo import BASE
from .redator import Bloco


@lru_cache(maxsize=1)
def catalogo_resumos():
    return json.loads((BASE / 'dados' / 'resumos.json').read_text(encoding='utf-8'))


def montar_resumo(dados, itens, motor, blocos_formais):
    catalogo = catalogo_resumos()
    saida = []
    for numero, item in enumerate(itens, 1):
        if item.exigencia not in catalogo['itens']:
            raise ValueError('Esta pendência ainda não possui resumo cadastrado. A nota não foi gerada sem o resumo.')
        titulo, pendencia, motivo, resolver = catalogo['itens'][item.exigencia]
        e = motor.cat.exigencia(item.exigencia)
        fonte = e['defeito'] + ' ' + e['providencia']
        if '{assinatura}' in fonte:
            resolver += (' As assinaturas exigidas neste item devem ser feitas em papel com firma reconhecida '
                         'ou digitalmente com certificado ICP-Brasil, verificável em https://validar.iti.gov.br/.')
        if '{protocolo_apartado}' in fonte:
            resolver += ' Esse pedido deve ser apresentado em protocolo separado.'
        saida.append({
            'numero': numero, 'exigencia': item.exigencia,
            'titulo': motor._preenche(titulo, item.valores),
            'pendencia': motor._preenche(pendencia, item.valores),
            'motivo': motor._preenche(motivo, item.valores),
            'comoResolver': motor._preenche(resolver, item.valores),
        })
    especie = dados.get('especie', 'devolutiva')
    final = ('O documento apresentado foi devolvido por impossibilidade de registro, pelos motivos da nota formal.'
             if especie == 'impossibilidade' else
             'Após o cumprimento dos itens, o cartório poderá prosseguir com a análise para o registro.')
    if especie == 'devolutiva':
        final += ' O valor de eventual pagamento complementar será informado após a superação das exigências e a análise de aptidão para registro.'
    if motor.modelo['especies'][especie].get('ressalva'):
        final += ' A análise dos documentos novos ou corrigidos poderá identificar outras exigências.'
    if dados.get('judicial'):
        final += ' Mesmo quando o documento vem da Justiça, o cartório confere sua forma e sua ligação com o registro, sem rever o mérito da decisão.'
    resumo = {
        'versao': catalogo['versao'], 'protocolo': str(dados.get('protocolo') or '').strip(),
        'titulo': str(dados.get('titulo') or '«título apresentado»').strip(),
        'especie': motor.modelo['especies'][especie]['rotulo'], 'itens': saida,
        'orientacaoFinal': final,
        'aviso': 'Este resumo explica os mesmos itens da nota formal que o acompanha. Leia os dois juntos; a nota formal mantém as exigências e os fundamentos completos.',
    }
    # Identifica o par produzido na mesma geração. Não persiste o conteúdo.
    fonte = {'resumo': resumo, 'formal': [[b.papel, b.numero, [p[0] for p in b.partes]] for b in blocos_formais]}
    resumo['vinculo'] = hashlib.sha256(json.dumps(fonte, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    return resumo


def blocos_resumo(resumo):
    def texto(valor, papel='resumo_texto', negrito=False):
        return Bloco(papel, partes=[(valor, {'negrito'} if negrito else set())])
    blocos = [texto('Resumo para o cliente', 'resumo_titulo', True),
              texto(f"{resumo['especie']} | Protocolo: {resumo['protocolo'] or 'não informado'} | Referência conjunta: {resumo['vinculo']}"),
              texto('Documento apresentado: ' + resumo['titulo']), texto(resumo['aviso'])]
    for item in resumo['itens']:
        blocos.append(texto(f"Item {item['numero']} da nota - {item['titulo']}", 'resumo_item', True))
        blocos.extend([texto('O que precisa ser resolvido: ' + item['pendencia']),
                       texto('Por que isso é necessário: ' + item['motivo']),
                       texto('Como resolver: ' + item['comoResolver'])])
    blocos.extend([texto('Após a entrega dos documentos', 'resumo_item', True), texto(resumo['orientacaoFinal'])])
    return blocos


def html_resumo(resumo):
    def escapar(v):
        return html.escape(str(v)).replace('«', '<span class="falta">«').replace('»', '»</span>')
    partes = ['<section class="nota-resumo" aria-label="Resumo para o cliente">', '<h2>Resumo para o cliente</h2>',
              f'<p>{escapar(resumo["especie"])} · Protocolo: {escapar(resumo["protocolo"] or "não informado")}</p>',
              f'<p>Documento apresentado: {escapar(resumo["titulo"])}</p>',
              f'<p>{escapar(resumo["aviso"])}</p>']
    for item in resumo['itens']:
        partes.append(f'<section class="nota-resumo-item" data-resumo-numero="{item["numero"]}"><h3>Item {item["numero"]} da nota · {escapar(item["titulo"])}</h3>')
        for rotulo, campo in [('O que precisa ser resolvido', 'pendencia'), ('Por que isso é necessário', 'motivo'), ('Como resolver', 'comoResolver')]:
            partes.append(f'<p><strong>{rotulo}:</strong> {escapar(item[campo])}</p>')
        partes.append('</section>')
    partes.extend([f'<p>{escapar(resumo["orientacaoFinal"])}</p>', f'<small>Referência conjunta: {escapar(resumo["vinculo"])}</small>', '</section>'])
    return ''.join(partes)
