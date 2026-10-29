"""Exportação operacional do índice, sem exigir conferência de matrículas."""
from datetime import datetime
from html import escape
from io import BytesIO
from zoneinfo import ZoneInfo

import pymupdf


def gerar_pdf_buscas(dados: dict, nome: str, documento: str, somente_ativos: bool) -> bytes:
    def texto(valor):
        return escape(str(valor if valor is not None else "Não informado"))

    itens = dados.get("itens") or []
    matriculas = {item["matricula"] for item in itens}
    correspondencias = {
        'DOCUMENTO_EXATO':'Documento exato', 'DOCUMENTO_DIVERGENTE':'Documento diferente do pesquisado',
        'NOME_EXATO':'Nome exato', 'NOME_EQUIVALENTE':'Nome equivalente',
        'NOME_EXATO_SEM_DOCUMENTO':'Nome igual; documento não confirmado',
        'VARIACAO_DE_NOME':'Variação de nome / correspondência parcial',
    }
    linhas = []
    pendentes = 0
    for item in itens:
        alertas = list(item.get('alertas') or [])
        if item.get('motorDesatualizado') and not any('versão anterior' in a for a in alertas):
            alertas.append('Análise de versão anterior; atualização pendente')
        if item.get('revisaoPendente') and not alertas:
            alertas.append('Conferência pendente')
        if item.get('correspondencia') == 'DOCUMENTO_DIVERGENTE':
            alertas.append('Não confirma identidade da pessoa pesquisada')
        pendentes += bool(alertas)
        consulta = 'Não informada'
        if item.get('consultadoEm'):
            try:
                data = datetime.fromisoformat(str(item['consultadoEm']).replace('Z','+00:00'))
                if data.tzinfo is None:
                    # Dados legados sem fuso não autorizam inventar conversão.
                    consulta = data.strftime('%d/%m/%Y')
                else:
                    consulta = data.astimezone(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m/%Y')
            except (TypeError,ValueError):
                pass
        verificacao = correspondencias.get(item.get('correspondencia'),'Correspondência não informada')
        avisos = ''.join(f'<div class="alerta">{texto(a)}</div>' for a in dict.fromkeys(alertas))
        linhas.append(
            f'<tr><td>{format(int(item["matricula"]), ",").replace(",", ".")}</td>'
            f'<td><strong>{texto(item.get("nome"))}</strong><br>Participação: {texto(item.get("proporcao"))}</td>'
            f'<td>{texto(item.get("documento"))}</td><td>{texto(item.get("situacao"))}</td>'
            f'<td>{texto(verificacao)}{avisos}<div class="consulta">Consulta: {texto(consulta)}</div></td></tr>'
        )
    cobertura = dados.get('cobertura') or {}
    ressalvas = list(cobertura.get('ressalvas') or [])
    if cobertura.get('negativa_segura') is False and not ressalvas:
        ressalvas = ['A cobertura do índice tem pendências; ausência de resultado não comprova uma negativa segura.']
    aviso_cobertura = ('<div class="aviso"><strong>Cobertura do índice</strong><br>'
                      + '<br>'.join(texto(a) for a in ressalvas) + '</div>') if ressalvas else ''
    instante = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y às %H:%M")
    filtros = []
    if nome:
        filtros.append(f"Nome ou termo: {texto(nome)}")
    if documento:
        filtros.append(f"CPF/CNPJ pesquisado: {texto(documento)}")
    filtros.append("Situação: somente ativas" if somente_ativos else "Situação: incluindo encerradas")
    html = f"""<html><body>
    <h1>Cartório do 1º Ofício de Notas e Registro de Imóveis de Morrinhos-GO</h1>
    <h2>Resultado da busca</h2><p class="meta">Gerado em {instante}</p>
    <h3>1. Dados solicitados</h3><p>{'<br>'.join(filtros)}</p>
    <h3>2. Resultado</h3>
    <p>{len(itens)} resultado(s) em {len(matriculas)} matrícula(s).</p>
    {f'<p class="aviso">{pendentes} resultado(s) com alertas. Consulte a coluna Correspondência / alertas.</p>' if pendentes else ''}
    {aviso_cobertura}
    {('<table><tr><th>Matrícula</th><th>Titular no índice</th><th>CPF/CNPJ</th><th>Situação</th><th>Correspondência / alertas</th></tr>' + ''.join(linhas) + '</table>') if itens else '<p>Nenhum resultado localizado no índice para os parâmetros pesquisados.</p>'}
    <p class="nota">Exportação dos resultados do índice, sem conferência individual das matrículas.
    Este relatório não substitui certidão. Menções em atos anteriores não integram esta listagem.</p>
    </body></html>"""
    css = """body {font-family: sans-serif; font-size: 10pt; color: #10273c;}
    h1 {font-size: 13pt; color: #065f46; margin-bottom: 18pt;}
    h2 {font-size: 18pt; margin-bottom: 5pt;} h3 {font-size: 11pt; margin-top: 16pt;}
    p {line-height: 1.5;} .meta,.nota {font-size: 9pt; color: #42596b;}
    .nota {margin-top: 20pt;} table {border-collapse: collapse; width: 100%;}
    th {color: #065f46; font-size: 9pt; text-align: left;}
    td,th {padding: 7pt 5pt; border-bottom: 0.5pt solid #d5e7e0;}
    td {font-size: 8.5pt;} .alerta {color: #854d0e; margin-top: 4pt;}
    .aviso {color: #713f12; padding: 8pt; font-size: 9pt;}
    .consulta {font-size: 8pt; color: #42596b; margin-top: 5pt;}"""
    saida = BytesIO()
    writer = pymupdf.DocumentWriter(saida)
    try:
        story = pymupdf.Story(html=html, user_css=css)
        def pagina(_numero, _anterior):
            folha = pymupdf.Rect(0, 0, 595, 842)
            return folha, pymupdf.Rect(42, 42, 553, 790), None
        story.write(writer, pagina)
    finally:
        writer.close()
    with pymupdf.open(stream=saida.getvalue(), filetype="pdf") as pdf:
        for i, folha in enumerate(pdf):
            folha.insert_text((42, 817), f"AERI - Resultado da busca | Página {i + 1} de {len(pdf)}", fontsize=8, color=(.25, .35, .3))
        pdf.set_metadata({"title": "Resultado da busca", "author": "AERI"})
        return pdf.tobytes(garbage=4, deflate=True)
