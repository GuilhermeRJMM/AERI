"""Configura/consulta RTD sem exibir credenciais. Não envia nada ao RTD."""
import argparse
import getpass
import os
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def carregar_ambiente():
    for nome in ('.env', '.env.buscas.local', '.env.rtd.local'):
        caminho = RAIZ / nome
        if caminho.exists():
            for linha in caminho.read_text(encoding='utf-8-sig').splitlines():
                if linha.strip() and not linha.lstrip().startswith('#') and '=' in linha:
                    chave, valor = linha.split('=', 1)
                    valor = valor.strip().strip('"').strip("'")
                    if valor and '[SENSITIVE]' not in valor:
                        os.environ.setdefault(chave.strip(), valor)


def salvar_token_local(nome, token):
    caminho = RAIZ / '.env.rtd.local'
    linhas = caminho.read_text(encoding='utf-8-sig').splitlines() if caminho.exists() else []
    saida = []
    substituido = False
    for linha in linhas:
        if linha.partition('=')[0].strip() == nome:
            if not substituido:
                saida.append(f'{nome}={token}')
                substituido = True
        else:
            saida.append(linha)
    if not substituido:
        saida.append(f'{nome}={token}')
    caminho.write_text('\n'.join(saida).rstrip() + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configurar', action='store_true')
    parser.add_argument('--ambiente', choices=('producao', 'homologacao'), default='producao',
                        help='Ambiente usado ao validar/configurar o token; a sincronização continua em produção.')
    parser.add_argument('--migrar-rtd', action='store_true', help='Aplica somente a migração RTD, sem executar as outras pendentes.')
    parser.add_argument('--passos', type=int, default=1)
    args = parser.parse_args()
    carregar_ambiente()
    from backend.app.servicos.rtd_cliente import ClienteRTD
    from backend.app.servicos.rtd_cliente import ErroRTD
    fechar_pool = None
    try:
        if args.configurar:
            token = getpass.getpass('Chave RTD (entrada oculta): ').strip()
            if not re.fullmatch(r'[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+', token):
                raise ValueError('Formato da chave inválido.')
            # Valida autenticação antes de persistir; nada é impresso da resposta.
            from datetime import date
            ClienteRTD(token, ambiente=args.ambiente).atualizacoes(date.today(), 1)
            variavel = 'AERI_RTD_TOKEN_HOMOLOGACAO' if args.ambiente == 'homologacao' else 'AERI_RTD_TOKEN'
            salvar_token_local(variavel, token)
            os.environ[variavel] = token
            print(f'Chave de {args.ambiente} validada e salva apenas em .env.rtd.local (ignorado pelo Git).')
        if args.migrar_rtd:
            from backend.app.database import conectar, fechar_pool as fechar_pool_banco
            fechar_pool = fechar_pool_banco
            with conectar() as con, con.cursor() as cur:
                cur.execute('SELECT pg_advisory_xact_lock(%s)', (1_095_062_089,))
                for nome in ('050_rtd_intimacoes.sql','051_rtd_destinatarios.sql',
                             '052_rtd_origem_devedor.sql','053_rtd_notificacoes_enviadas.sql'):
                    cur.execute('SELECT 1 FROM migracoes_aeri WHERE versao=%s', (nome,))
                    if not cur.fetchone():
                        cur.execute((RAIZ / 'backend/app/migrations' / nome).read_text(encoding='utf-8'))
                        cur.execute('INSERT INTO migracoes_aeri(versao) VALUES (%s)', (nome,))
                con.commit()
            print('Estrutura RTD pronta; demais migrações não foram alteradas.')
        passos = 0 if args.configurar and args.ambiente == 'homologacao' else args.passos
        if passos > 0:
            from backend.app.database import fechar_pool as fechar_pool_banco
            from backend.app.servicos.rtd_sincronizacao import executar_passo_rtd
            fechar_pool = fechar_pool_banco
        for _ in range(max(0, min(passos, 100))):
            print(executar_passo_rtd())
    except Exception as exc:
        print(str(exc) if isinstance(exc, (ErroRTD, ValueError)) else f'Falha local: {type(exc).__name__}. Nenhuma credencial exibida.')
        return 1
    finally:
        if fechar_pool:
            fechar_pool()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
