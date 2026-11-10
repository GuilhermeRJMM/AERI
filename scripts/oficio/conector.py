"""Ponte de saída HTTPS. Nenhum servidor local, proxy genérico ou cookie remoto."""
import argparse
import asyncio
from contextlib import AsyncExitStack
import getpass
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from uuid import UUID

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.oficio.consultar import abrir_sessao, ler_sessao, ErroConsulta
from scripts.oficio.credencial_windows import carregar, salvar


def origem(valor):
    u=urlsplit(valor)
    if (u.scheme!='https' or not u.hostname or u.username or u.password
            or u.path not in {'','/'} or u.query or u.fragment or u.port not in {None,443}):
        raise ValueError('Informe a origem HTTPS exata do Analisador, sem caminho ou credenciais.')
    return 'https://'+u.hostname.lower()


class SemRedirecionamento(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def enviar(servidor,rota,dados,token=None):
    # Só rotas fixas do protocolo do conector; nada recebido do site vira URL.
    if not (rota in {'/conector/vincular','/conector/proximo'}
            or re.fullmatch(r'/conector/trabalhos/[a-f0-9-]{36}/resultado',rota)):
        raise ValueError('Rota recusada.')
    headers={'Content-Type':'application/json'}
    if token:
        if not re.fullmatch(r'oficio_[A-Za-z0-9_-]{43}',token):
            raise ValueError('Credencial local inválida. Conecte novamente sua conta.')
        headers['Authorization']='Bearer '+token
    req=urllib.request.Request(origem(servidor)+'/api/oficio-consultas'+rota,
        data=json.dumps(dados,ensure_ascii=False).encode('utf-8'),headers=headers,method='POST')
    # Redirects são recusados para não levar a credencial a outro host.
    with urllib.request.build_opener(SemRedirecionamento()).open(req,timeout=15) as resposta:
        corpo=resposta.read(1_000_001)
        if len(corpo)>1_000_000:
            raise ValueError('Resposta do Analisador excede o limite.')
        return json.loads(corpo)


def validar_trabalho(item,cartorio):
    if not isinstance(item,dict) or set(item)!={'id','cartorio','minimo'}:
        raise ValueError('Trabalho inválido.')
    UUID(item['id'])
    if item['cartorio']!=cartorio or type(item['minimo']) is not int or not 1<=item['minimo']<=2000:
        raise ValueError('Trabalho de outra serventia ou fora dos limites.')
    return item


def codigo_erro(erro):
    if isinstance(erro,BaseExceptionGroup):
        for filho in erro.exceptions:
            codigo=codigo_erro(filho)
            if codigo!='consulta_interrompida':
                return codigo
    if isinstance(erro,ErroConsulta):
        mensagem=str(erro)
        for codigo in ['pagina_incorreta','filtro_ativo_ou_desconhecido','cartorio_diferente','total_ou_pagina_divergente']:
            if codigo in mensagem:
                return codigo
        if any(t in mensagem for t in ['Chrome','aba','depuração']):
            return 'conexao_chrome'
    return 'consulta_interrompida'


async def executar(config, *, uma_vez=False):
    servidor=origem(config['servidor'])
    stack=AsyncExitStack()
    sessao=None
    print('Conector aberto. Clique em Consultar agora na Mesa de conferência. Ctrl+C para encerrar.')
    falhas=0
    try:
        while True:
            try:
                resposta=await asyncio.to_thread(enviar,servidor,'/conector/proximo',{},config['token'])
                trabalho=resposta.get('trabalho')
                if trabalho:
                    trabalho=validar_trabalho(trabalho,config['cartorio'])
                    try:
                        if sessao is None:
                            sessao=await stack.enter_async_context(abrir_sessao())
                        dados=await ler_sessao(sessao,trabalho['cartorio'],minimo=trabalho['minimo'])
                        resultado={'captura':dados}
                    except Exception as erro:
                        resultado={'erro':codigo_erro(erro)}
                        # Uma nova tentativa só ocorre em um NOVO clique no Analisador.
                        # Filtro/tela incorretos não derrubam a conexão já autorizada.
                        if not isinstance(erro,(ErroConsulta,ValueError)):
                            await stack.aclose()
                            stack=AsyncExitStack()
                            sessao=None
                    await asyncio.to_thread(enviar,servidor,
                        '/conector/trabalhos/'+trabalho['id']+'/resultado',resultado,config['token'])
                    print('Consulta entregue ao Analisador.' if 'captura' in resultado else 'Consulta não concluída. Veja a orientação no Analisador.')
                falhas=0
            except urllib.error.HTTPError as erro:
                if erro.code in {401,403}:
                    raise ValueError('Conector revogado ou expirado. Gere um novo código no Analisador.') from None
                falhas+=1
                print('Analisador indisponível. Nenhum envio ao Ofício foi realizado.')
            except (OSError,ValueError):
                falhas+=1
                print('Falha de comunicação ou trabalho inválido. Nenhuma consulta adicional foi iniciada.')
            if uma_vez:
                return
            await asyncio.sleep(min(60,4*max(1,falhas)))
    finally:
        await stack.aclose()


def main():
    p=argparse.ArgumentParser(description='Consulta direta do Analisador pelo Chrome local autorizado.')
    p.add_argument('--parear',action='store_true',help='Conectar uma vez com código gerado no Analisador')
    p.add_argument('--servidor',help='Origem HTTPS exata do Analisador, obrigatória no pareamento')
    p.add_argument('--uma-vez',action='store_true',help='Uma verificação da fila, sem execução contínua')
    args=p.parse_args()
    try:
        if args.parear:
            if not args.servidor:
                p.error('Informe --servidor ao parear.')
            servidor=origem(args.servidor)
            codigo=getpass.getpass('Código de conexão gerado no Analisador (não será exibido): ').strip()
            if not re.fullmatch(r'oficio_pair_[A-Za-z0-9_-]{43}',codigo):
                raise ValueError('Código inválido.')
            dados=enviar(servidor,'/conector/vincular',{'codigo':codigo})
            if (not isinstance(dados,dict) or set(dados)!={'token','cartorio'}
                    or not re.fullmatch(r'oficio_[A-Za-z0-9_-]{43}',dados.get('token',''))
                    or not re.fullmatch(r'[1-9][0-9]{0,9}',dados.get('cartorio',''))):
                raise ValueError('Resposta de pareamento inválida.')
            salvar({'servidor':servidor,**dados})
            print('Conta conectada. Credencial protegida pelo seu usuário Windows.')
        config=carregar()
        if args.servidor and origem(args.servidor)!=config['servidor']:
            raise ValueError('Servidor diferente do pareado. Não enviarei a credencial.')
        asyncio.run(executar(config,uma_vez=args.uma_vez))
    except KeyboardInterrupt:
        print('Conector encerrado.')
    except Exception:
        print('Conector não iniciado ou desconectado. Confira o pareamento e a autorização no Chrome. Não compartilhe a credencial.')
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
