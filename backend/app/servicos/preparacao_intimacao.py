"""Preparação pelo executor local, sem enviar os PDFs ou abrir portas na rede."""
from datetime import datetime
from pathlib import Path
import re
import unicodedata
from zoneinfo import ZoneInfo

from backend.app.database import conectar
from backend.app.servicos.contratos import cifrar
from backend.app.servicos.documentos_intimacao import (
    analisar_pdfs_intimacao, complementar_matricula, estruturar_endereco,
    ErroDocumentoIntimacao, LIMITE_PDF_INTIMACAO,
)
from backend.app.servicos.tri7 import cliente_tri7, ErroTri7

PASTA_CEPS = Path(r'T:\Setor Registro de Imoveis\Legislacoes e Orientacoes')


def normalizar(valor):
    texto = unicodedata.normalize('NFKD', str(valor)).encode('ascii', 'ignore').decode().upper()
    texto = re.sub(r'\bONZE\b', '11', texto)
    return re.sub(r'\s+', ' ', texto).strip()


def atualizar_ceps(dados, raiz=PASTA_CEPS):
    """Só substitui CEP em correspondência exata de logradouro E bairro."""
    from pypdf import PdfReader
    tabela = {}
    for nome in ('Alteração do CEP de Morrinhos.pdf', 'Alteração do CEP de Morrinhos Novo Prefeitura 10.25.pdf'):
        arquivo = raiz / nome
        if not arquivo.is_file():
            continue
        for pagina in PdfReader(arquivo).pages:
            for linha in (pagina.extract_text() or '').splitlines():
                match = re.match(r'^(.+?)\s+(\d{5}-\d{3})\s+(.+)$', linha.strip())
                if match:
                    tabela[(normalizar(match[1]), normalizar(match[3]))] = match[2]
                else:
                    match = re.match(r'^\d+\s+(.+?)\s{2,}(.+?)\s+(\d{5}-?\d{3})\s*$', linha)
                    if match:
                        tabela[(normalizar(match[1]), normalizar(match[2]))] = match[3]
    def corrigir(endereco):
        estrutura = estruturar_endereco(endereco)
        if normalizar(estrutura['cidade']) != 'MORRINHOS' or estrutura['uf'] != 'GO':
            return endereco
        cep = tabela.get((normalizar(estrutura['logradouro']), normalizar(estrutura['bairro'])))
        if not cep:
            dados['avisos'].append('CEP não confirmado na tabela atualizada: confira logradouro e bairro antes de copiar.')
            return endereco
        if re.search(r'\bCEP\s*:', endereco, re.IGNORECASE) or re.search(r'\bCEP\s+\d', endereco, re.IGNORECASE):
            return re.sub(r'\bCEP\s*:?\s*[\d. -]+$', f'CEP: {cep}', endereco, flags=re.IGNORECASE)
        return f'{endereco}, CEP: {cep}'
    dados['enderecos'] = [corrigir(e) for e in dados['enderecos']]
    dados['enderecoImovel'] = corrigir(dados['enderecoImovel']) if dados['enderecoImovel'] else ''
    dados['enderecosEstruturados'] = [estruturar_endereco(e) for e in dados['enderecos']]


def complementar_tri7(dados):
    try:
        cliente = cliente_tri7()
    except (ErroTri7, ValueError):
        dados['avisos'].append('Não foi possível consultar a Tri7. Confira a descrição do título, o registro da garantia e a data do protocolo.')
        return
    # Uma falha na consulta do protocolo não pode impedir a leitura da
    # matrícula: é dela que vêm o ato da garantia e a descrição do título.
    if dados.get('matricula'):
        try:
            complementar_matricula(dados, cliente.buscar_texto_matricula(dados['matricula'])['texto'])
        except (ErroTri7, ValueError):
            dados['avisos'].append('Não foi possível consultar o texto da matrícula na Tri7. Confira o registro da garantia e a descrição do título.')
    if dados.get('protocoloTri7'):
        try:
            protocolo = cliente.buscar_protocolo_completo(dados['protocoloTri7'])['protocolo']
            data = protocolo.get('data_protocolo') or protocolo.get('protocolo_data')
            if data and not dados.get('dataProtocolo'):
                try:
                    dados['dataProtocolo'] = datetime.fromisoformat(str(data)).strftime('%d/%m/%Y')
                except ValueError:
                    pass
        except (ErroTri7, ValueError):
            dados['avisos'].append('Não foi possível consultar o protocolo na Tri7. Confira a data do protocolo.')


def protocolo_rgi_da_pasta(pasta: Path, protocolo_in: str) -> tuple[str, str, list[str]]:
    """Lê o recibo do protocolo RGI na pasta do IN; nunca escolhe outro número solto."""
    expedidos = [item for item in pasta.iterdir() if item.is_dir()
        and normalizar(item.name) == 'EXPEDIDO PELO CARTORIO']
    if len(expedidos) != 1:
        return '', '', ['Pasta "Expedido pelo Cartório" não localizada de forma única; confira o protocolo RGI.']
    raiz = pasta.resolve()
    arquivos = [item for item in expedidos[0].iterdir() if item.is_file() and item.suffix.lower() == '.pdf']
    recibos = {}
    numeros = set()
    for arquivo in arquivos:
        nome = normalizar(arquivo.stem)
        if re.fullmatch(r'\d{3}\.\d{3}|\d{6}', nome):
            numero = re.sub(r'\D', '', nome)
            numeros.add(numero)
            recibos.setdefault(numero, []).append(arquivo)
        else:
            titulo = re.fullmatch(r'TITULO REGISTRADO\s*-\s*RI\s*-\s*PROTOCOLO\s*(\d{6})', nome)
            if titulo:
                numeros.add(titulo.group(1))
    if len(numeros) != 1:
        return '', '', ['Não foi encontrado um único protocolo RGI de seis dígitos nos comprovantes da pasta deste IN. Confira o número manualmente.']
    numero = numeros.pop()
    if len(recibos.get(numero, [])) != 1:
        return '', '', ['O recibo do protocolo RGI não foi localizado de forma única na pasta deste IN. Confira o número manualmente.']
    recibo = recibos[numero][0]
    if not recibo.resolve().is_relative_to(raiz) or recibo.stat().st_size > LIMITE_PDF_INTIMACAO:
        return '', '', ['O recibo do protocolo está fora da pasta permitida ou acima de 8 MB. Confira o número manualmente.']
    from backend.app.servicos.documentos_intimacao import _ler_pdf
    try:
        texto = _ler_pdf(recibo.read_bytes(), 'Recibo do protocolo RGI')
    except (ErroDocumentoIntimacao, OSError):
        return '', '', ['Não foi possível ler o recibo do protocolo RGI. Confira o número manualmente.']
    formato_numero = rf'{numero[:3]}\.?{numero[3:]}'
    if not re.search(rf'\b{re.escape(protocolo_in)}\b', texto, re.IGNORECASE) or not re.search(
        rf'\bProtocolo[.\s]{{0,35}}:\s*{formato_numero}(?!\d)', texto, re.IGNORECASE
    ):
        return '', '', ['O recibo não confirma este IN e o protocolo RGI indicado no nome do arquivo. Confira o número manualmente.']
    data = re.search(
        rf'\bProtocolo[.\s]{{0,35}}:\s*{formato_numero}\s*,?\s*de\s+(\d{{2}}/\d{{2}}/\d{{4}})',
        texto, re.IGNORECASE,
    )
    return numero, data.group(1) if data else '', []


def ler_pasta_processo(protocolo, protocolo_tri7='', referencia=None, pasta=None):
    from ferramentas.abrir_pasta_intimacao import localizar_pasta_existente, PADRAO_PROTOCOLO
    if not PADRAO_PROTOCOLO.fullmatch(protocolo):
        raise ErroDocumentoIntimacao('Protocolo IN inválido.')
    pasta = Path(pasta) if pasta else localizar_pasta_existente(protocolo)
    if pasta is None or not pasta.is_dir():
        raise ErroDocumentoIntimacao('Pasta do IN não localizada na rede da serventia.')
    raiz = pasta.resolve()
    referencia = referencia or datetime.now(ZoneInfo('America/Sao_Paulo')).date()
    arquivos = []
    for subpasta in pasta.iterdir():
        if subpasta.is_dir() and 'RECEBID' in normalizar(subpasta.name):
            arquivos.extend(subpasta.glob('*.pdf'))
    def escolher(prefixo):
        candidatos = [f for f in arquivos if normalizar(f.stem) == prefixo]
        if len(candidatos) != 1:
            raise ErroDocumentoIntimacao('Ofício ou planilha de projeção não localizado de forma única na pasta recebida.')
        arquivo = candidatos[0]
        if not arquivo.resolve().is_relative_to(raiz) or arquivo.stat().st_size > LIMITE_PDF_INTIMACAO:
            raise ErroDocumentoIntimacao('PDF fora da pasta permitida ou acima de 8 MB.')
        return arquivo.read_bytes()
    dados = analisar_pdfs_intimacao(escolher('OFICIO'), escolher('PLANILHA DE PROJECAO'), referencia, protocolo, protocolo_tri7)
    numero_rgi, data_rgi, avisos_rgi = protocolo_rgi_da_pasta(pasta, protocolo)
    dados['avisos'].extend(avisos_rgi)
    if numero_rgi:
        if dados.get('protocoloTri7') and re.sub(r'\D', '', str(dados['protocoloTri7'])) != numero_rgi:
            raise ErroDocumentoIntimacao('O protocolo RGI da pasta diverge do protocolo vinculado a este IN no AERI.')
        dados['protocoloTri7'] = numero_rgi
        if data_rgi and not dados.get('dataProtocolo'):
            dados['dataProtocolo'] = data_rgi
    registrados = [f for f in pasta.rglob('*.PDF') if normalizar(f.stem).startswith('TITULO REGISTRADO')]
    if len(registrados) == 1 and registrados[0].resolve().is_relative_to(raiz) and registrados[0].stat().st_size <= LIMITE_PDF_INTIMACAO:
        from backend.app.servicos.documentos_intimacao import _ler_pdf, complementar_titulo_registrado
        complementar_titulo_registrado(dados, _ler_pdf(registrados[0].read_bytes(), 'Título registrado'))
    complementar_tri7(dados)
    atualizar_ceps(dados)
    dados['avisos'].append('Informe o número sequencial do ofício após conferir a pasta de ofícios enviados; a leitura não reserva esse número.')
    return dados


def processar_preparacao_intimacao():
    """Lease curto e conclusão condicionada: outro worker não sobrescreve o resultado."""
    # Servidores sem drive T: não podem reclamar os trabalhos desta fila.
    from ferramentas.abrir_pasta_intimacao import RAIZES_BUSCA
    if not any(raiz.is_dir() for raiz in RAIZES_BUSCA):
        return {'estado': 'SEM_TRABALHO'}
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute('DELETE FROM preparacoes_intimacao_aeri WHERE expira_em < NOW()')
            cur.execute("""UPDATE preparacoes_intimacao_aeri SET estado='ERRO', erro='A leitura foi interrompida. Solicite novamente.', atualizado_em=NOW()
                WHERE estado='LENDO' AND atualizado_em < NOW() - INTERVAL '5 minutes'""")
            cur.execute("""SELECT p.id,i.protocolo,i.protocolo_tri7 FROM preparacoes_intimacao_aeri p
                JOIN intimacoes_aeri i ON i.id=p.intimacao_id
                WHERE p.estado='PENDENTE' AND p.expira_em>NOW() AND i.excluida_em IS NULL AND i.fase='INTIMACAO'
                ORDER BY p.criado_em FOR UPDATE OF p SKIP LOCKED LIMIT 1""")
            trabalho = cur.fetchone()
            if trabalho:
                cur.execute("UPDATE preparacoes_intimacao_aeri SET estado='LENDO', atualizado_em=NOW() WHERE id=%s", (trabalho['id'],))
        con.commit()
    if not trabalho:
        return {'estado': 'SEM_TRABALHO'}
    try:
        dados = ler_pasta_processo(trabalho['protocolo'], trabalho['protocolo_tri7'] or '')
        cifrado, erro, estado = cifrar(dados), None, 'PRONTO'
    except (ErroDocumentoIntimacao, ValueError) as exc:
        cifrado, erro, estado = None, str(exc)[:500], 'ERRO'
    except Exception:
        cifrado, erro, estado = None, 'Não foi possível ler o processo. Confira a rede e a configuração do executor.', 'ERRO'
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute("""UPDATE preparacoes_intimacao_aeri SET dados_cifrados=%s,erro=%s,estado=%s,atualizado_em=NOW()
                WHERE id=%s AND estado='LENDO'""", (cifrado, erro, estado, trabalho['id']))
        con.commit()
    return {'estado': estado}
