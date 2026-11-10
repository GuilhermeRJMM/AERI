"""Consulta explícita com o transporte do reverse-api-engineer. Sem agente de IA."""
import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.app.servicos.oficio_consultas import validar_captura


class ErroConsulta(ValueError):
    """Mensagem controlada, sem conteúdo recebido do navegador."""


def mensagem_erro(erro):
    folhas = []
    def visitar(item):
        if isinstance(item, BaseExceptionGroup):
            for filho in item.exceptions:
                visitar(filho)
        else:
            folhas.append(item)
    visitar(erro)
    for item in folhas:
        if isinstance(item, ErroConsulta):
            return str(item)
    tipos = sorted({type(item).__name__ for item in folhas})
    return ('Não foi possível concluir a consulta. Confira autorização, conexão e dependências locais. '
            'Diagnóstico sem conteúdo do portal: ' + ', '.join(tipos))


def extrair_json(resultado):
    if resultado.is_error:
        raise ErroConsulta('O Chrome recusou a consulta. Nenhum arquivo foi gerado.')
    texto = '\n'.join(c.text for c in resultado.content if hasattr(c, 'text'))
    blocos = re.findall(r'```(?:json)?\s*\n(.*?)\n```', texto, re.S)
    if len(blocos) != 1 or len(blocos[0]) > 1_000_000:
        raise ErroConsulta('Resposta do conector não reconhecida.')
    dados = json.loads(blocos[0])
    if isinstance(dados, dict) and 'erro' in dados:
        codigos = {'pagina_incorreta', 'cartorio_diferente', 'filtro_ativo_ou_desconhecido',
                   'cartorio_nao_confirmado', 'total_ou_pagina_divergente', 'consulta_incompleta'}
        codigo = dados['erro'] if dados['erro'] in codigos else 'consulta_interrompida'
        campo = dados.get('campo', '')
        campos = {'filterProtocolo','filterDataPedidoDe','filterDataPedidoAte','filterPrenotacao',
                  'filterEmolumentos','filterSolicitante','filterAptoEdital','filterStatus',
                  'filterIsencao','filterNotificadoPorE-mail'}
        detalhe = f' Campo {campo}: {"ativo" if dados.get("presente") else "não encontrado"}.' if campo in campos else ''
        raise ErroConsulta(f'Consulta recusada ({codigo}).{detalhe} Confira a lista e os filtros no Ofício.')
    return dados


def paginas_oficio(resultado):
    if resultado.is_error:
        raise ErroConsulta('O Chrome não autorizou a conexão.')
    ids = []
    for bloco in resultado.content:
        for linha in getattr(bloco, 'text', '').splitlines():
            m = re.search(r'(\d+):.*?\((https?://[^\s)]+)\)', linha)
            if not m:
                continue
            url = urlsplit(m[2])
            if (url.scheme == 'https' and url.hostname in {'oficioeletronico.com.br', 'www.oficioeletronico.com.br'}
                    and url.path == '/Cartorios/Intimacoes'):
                ids.append(int(m[1]))
    if len(ids) != 1:
        raise ErroConsulta('Deixe exatamente uma aba na listagem de Intimações do Ofício, já filtrada.')
    return ids[0]


@asynccontextmanager
async def abrir_sessao():
    # Importação só no conector local: estas dependências não entram no servidor.
    from reverse_api.chrome_mcp import CHROME_DEVTOOLS_MCP_PACKAGE, check_auto_connect
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    if CHROME_DEVTOOLS_MCP_PACKAGE != 'chrome-devtools-mcp@1.12':
        raise ErroConsulta('Versão do transporte diferente da validada. Use reverse-api-engineer 0.15.0.')
    if not check_auto_connect().ok:
        raise ErroConsulta('Habilite a depuração no Chrome e mantenha o Ofício aberto e autenticado.')
    npx = shutil.which('npx.cmd') or shutil.which('npx')
    if not npx:
        raise ErroConsulta('Node.js/npx não encontrado no computador local.')
    params = StdioServerParameters(command=npx, args=[
        '-y', CHROME_DEVTOOLS_MCP_PACKAGE, '--autoConnect', '--no-usage-statistics',
        '--no-performance-crux', '--no-category-input', '--no-category-performance',
        '--no-category-emulation', '--no-category-memory'],
        env={**os.environ, 'CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS':'1',
             'CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS':'1'})
    print('Autorize a conexão do Chrome, se solicitado. Uma conexão, sem reconectar automaticamente.')
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=180.0) as sessao:
            await sessao.initialize()
            yield sessao


async def ler_sessao(sessao, cartorio, *, total=None, minimo=1):
    pagina = paginas_oficio(await sessao.call_tool('list_pages', {}))
    js = Path(__file__).with_name('coletar.js').read_text(encoding='utf-8')
    config = json.dumps({'cartorio':cartorio, 'total':total, 'minimo':minimo})
    resultado = await sessao.call_tool('evaluate_script', {'pageId':pagina,
        'function':f'async () => await ({js})({config})', 'waitForStableDom':False, 'dialogAction':'dismiss'})
    return validar_captura(extrair_json(resultado), cartorio)


async def consultar(args):
    async with abrir_sessao() as sessao:
        dados = await ler_sessao(sessao,args.cartorio,total=args.total_esperado)
    # Criação exclusiva: não substitui um arquivo existente ou destino incorreto.
    with args.saida.open('x', encoding='utf-8') as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
    print(f'Consulta concluída: {dados["total"]} INs, {len(dados["paginas"])} páginas.')
    print(f'Importe este arquivo na Mesa de conferência: {args.saida}')


def main():
    parser = argparse.ArgumentParser(description='Consulta assistida ao Ofício. Sem enviar ou alterar pedidos.')
    parser.add_argument('--cartorio', required=True, help='Identificador da sua serventia no Ofício')
    parser.add_argument('--total-esperado', required=True, type=int,
                        help='Total histórico exibido após preparar a lista completa (não o total em tratativa)')
    parser.add_argument('--saida', required=True, type=Path, help='Novo arquivo .json para importar no Analisador')
    args = parser.parse_args()
    if (not re.fullmatch(r'[1-9][0-9]{0,9}', args.cartorio) or not 1 <= args.total_esperado <= 2000
            or args.saida.suffix.lower() != '.json' or args.saida.exists()):
        parser.error('Cartório, total ou destino inválido; use um novo arquivo .json.')
    args.saida = args.saida.resolve()
    try:
        asyncio.run(consultar(args))
    except KeyboardInterrupt:
        print('Consulta cancelada. Nenhuma importação foi realizada.')
        return 1
    except Exception as erro:
        # Erros de grupos MCP podem conter conteúdo remoto. Não imprimir traceback.
        print(mensagem_erro(erro))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
