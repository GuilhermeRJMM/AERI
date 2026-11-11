"""Explicações editoriais por item, sem criar ou modificar exigências jurídicas."""
import hashlib
import html
import json
import re
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
            resolver += (' Se for exigido reconhecimento de firma neste caso, providencie-o em um tabelionato. '
                         'Se a assinatura for eletrônica, entregue o arquivo original com a validação aceita '
                         'para esse documento, que permita conferir quem assinou e se o arquivo foi alterado.')
        if '{protocolo_apartado}' in fonte:
            resolver += ' Esse pedido deve ser apresentado em protocolo separado.'
        detalhes = []
        def separar_detalhe(match):
            campo = match[2]
            if str(item.valores.get(campo) or '').strip():
                detalhes.append({'rotulo': match[1].strip(), 'valor': str(item.valores[campo]).strip()})
            return ''
        # Somente segmentos rotulados do modelo editorial, nunca texto digitado.
        pendencia = re.sub(r'\[\s*([^:{}\[\]]+):\s*\{(\w+)\}\.\]', separar_detalhe, pendencia)
        saida.append({
            'numero': numero, 'exigencia': item.exigencia,
            'titulo': motor._preenche(titulo, item.valores),
            'pendencia': motor._preenche(pendencia, item.valores),
            'detalhes': detalhes,
            'motivo': motor._preenche(motivo, item.valores),
            'comoResolver': motor._preenche(resolver, item.valores),
        })
    especie = dados.get('especie', 'devolutiva')
    final = ('A nota formal explica por que o documento foi devolvido sem possibilidade de registro na forma apresentada.'
             if especie == 'impossibilidade' else
             'Depois que você entregar o que foi pedido, o cartório fará nova conferência dos documentos.')
    if especie == 'devolutiva':
        final += ' Se houver saldo de taxas a pagar, o valor será informado após a conferência de que o documento está pronto para registro.'
    if motor.modelo['especies'][especie].get('ressalva'):
        final += ' Se os documentos novos ou corrigidos trouxerem outro problema, ele será informado.'
    if dados.get('judicial'):
        final += ' Mesmo quando o documento vem da Justiça, o cartório confere sua forma e sua ligação com o registro, sem rever o mérito da decisão.'
    resumo = {
        'versao': catalogo['versao'], 'protocolo': str(dados.get('protocolo') or '').strip(),
        'titulo': str(dados.get('titulo') or '«título apresentado»').strip(),
        'especie': motor.modelo['especies'][especie]['rotulo'], 'itens': saida,
        'orientacaoFinal': final,
        'aviso': 'Veja o que falta e como resolver. Leia também a nota formal que acompanha este resumo: ela contém as exigências e as bases legais do seu pedido.',
    }
    # Identifica o par produzido na mesma geração. Não persiste o conteúdo.
    fonte = {'resumo': resumo, 'formal': [[b.papel, b.numero, [p[0] for p in b.partes]] for b in blocos_formais]}
    resumo['vinculo'] = hashlib.sha256(json.dumps(fonte, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    return resumo


def blocos_resumo(resumo):
    def texto(valor, papel='resumo_texto', negrito=False):
        return Bloco(papel, partes=[(valor, {'negrito'} if negrito else set())])
    def com_icone(icone,valor,papel='resumo_texto',negrito=False):
        return Bloco(papel,partes=[(icone,{'icone'}),(' '+valor,{'negrito'} if negrito else set())])
    blocos = [texto('RESUMO', 'resumo_titulo', True),
              Bloco('resumo_meta', partes=[(resumo['especie'], {'negrito'}), (' | ', set()),
                    ('Protocolo: ', {'negrito'}), (resumo['protocolo'] or 'não informado', set())]),
              Bloco('resumo_meta', partes=[('📄',{'icone'}),(' Documento apresentado: ', {'negrito'}), (resumo['titulo'], set())]),
              texto(resumo['aviso'])]
    for item in resumo['itens']:
        blocos.append(com_icone('📋',f"ITEM {item['numero']} - {item['titulo'].upper()}", 'resumo_item', True))
        blocos.append(com_icone('🔎','O que precisa ser resolvido: ' + item['pendencia'], 'resumo_balao'))
        for indice, detalhe in enumerate(item.get('detalhes', [])):
            blocos.append(Bloco('resumo_detalhe_inicio' if indice == 0 else 'resumo_detalhe',
                          partes=[(detalhe['rotulo'] + ':', {'negrito','sublinhado'}), (' ' + detalhe['valor'], set())]))
        for icone,rotulo,campo in [('⚖️','Por que isso é necessário', 'motivo'), ('🛠️','Como resolver', 'comoResolver')]:
            blocos.append(Bloco('resumo_recuado', partes=[(icone,{'icone'}),(' '+rotulo + ':', {'negrito','sublinhado'}), (' ' + item[campo], set())]))
    blocos.extend([com_icone('📌','Após a entrega dos documentos', 'resumo_item', True), texto(resumo['orientacaoFinal'])])
    return blocos


def html_resumo(resumo):
    def escapar(v):
        return html.escape(str(v)).replace('«', '<span class="falta">«').replace('»', '»</span>')
    def icone(valor):
        return f'<span class="nota-icone" aria-hidden="true">{valor}</span> '
    partes = ['<section class="nota-resumo" aria-label="Resumo">', '<h2>RESUMO</h2>',
              f'<p class="nota-resumo-meta"><strong>{escapar(resumo["especie"])}</strong> | <strong>Protocolo:</strong> {escapar(resumo["protocolo"] or "não informado")}</p>',
              f'<p class="nota-resumo-meta">{icone("📄")}<strong>Documento apresentado:</strong> {escapar(resumo["titulo"])}</p>',
              f'<p>{escapar(resumo["aviso"])}</p>']
    for item in resumo['itens']:
        partes.append(f'<section class="nota-resumo-item" data-resumo-numero="{item["numero"]}"><h3>{icone("📋")}ITEM {item["numero"]} - {escapar(item["titulo"].upper())}</h3>')
        partes.append(f'<div class="nota-resumo-balao">{icone("🔎")}<strong>O que precisa ser resolvido</strong><p>{escapar(item["pendencia"])}</p></div>')
        if item.get('detalhes'):
            partes.append('<div class="nota-resumo-detalhes nota-resumo-recuo">')
            for detalhe in item['detalhes']:
                partes.append(f'<p><strong><u>{escapar(detalhe["rotulo"])}:</u></strong> {escapar(detalhe["valor"])}</p>')
            partes.append('</div>')
        for simbolo,rotulo,campo in [('⚖️','Por que isso é necessário', 'motivo'), ('🛠️','Como resolver', 'comoResolver')]:
            partes.append(f'<p class="nota-resumo-recuo">{icone(simbolo)}<strong><u>{rotulo}:</u></strong> {escapar(item[campo])}</p>')
        partes.append('</section>')
    partes.extend([f'<h3>{icone("📌")}Após a entrega dos documentos</h3>', f'<p>{escapar(resumo["orientacaoFinal"])}</p>',
        f'<footer class="nota-referencia">Referência conjunta: {escapar(resumo["vinculo"])}</footer>', '</section>'])
    return ''.join(partes)
