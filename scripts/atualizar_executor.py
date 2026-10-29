"""Instala código de um commit no executor existente, sem copiar credenciais.

Prévia por padrão. Snapshot do código anterior e rollback se o smoke falhar.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
from datetime import datetime, timezone
from zipfile import ZipFile

RAIZ = Path(__file__).resolve().parents[1]
TAREFA = 'AERI Executor'


def caminho_pacote(nome, destino):
    relativo = PurePosixPath(nome)
    if (relativo.is_absolute() or '..' in relativo.parts or '\\' in nome
            or not relativo.parts or ':' in nome
            or not (relativo.parts[0] == 'backend' or nome == 'scripts/worker_operacional.py')
            or any(parte.startswith('.env') for parte in relativo.parts)):
        raise ValueError('Caminho fora do pacote de código permitido.')
    alvo = destino.joinpath(*relativo.parts).resolve()
    if not alvo.is_relative_to(destino.resolve()):
        raise ValueError('Destino fora da instalação.')
    return alvo


def tarefa(acao):
    if os.name != 'nt':
        raise RuntimeError('A instalação de serviço exige Windows.')
    comando = {
        'estado': f"(Get-ScheduledTask -TaskName '{TAREFA}' -ErrorAction Stop).State",
        'parar': f"Stop-ScheduledTask -TaskName '{TAREFA}' -ErrorAction Stop",
        'iniciar': f"Start-ScheduledTask -TaskName '{TAREFA}' -ErrorAction Stop",
    }[acao]
    return subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',comando],
                          check=True,capture_output=True,text=True).stdout.strip()


def codigo_motor(python, raiz, *, smoke=False):
    codigo = 'from backend.app.analise.contrato import versao_indice_motor; '
    if smoke:
        codigo += "import runpy; runpy.run_path('scripts/worker_operacional.py',run_name='aeri_smoke'); "
    codigo += 'print(versao_indice_motor())'
    resultado = subprocess.run([str(python),'-c',codigo],cwd=raiz,capture_output=True,text=True,
                               timeout=90,check=True)
    return resultado.stdout.strip().splitlines()[-1]


def assinatura_configs(destino):
    return {nome:hashlib.sha256((destino/nome).read_bytes()).hexdigest()
            for nome in ('.env','.env.buscas.local') if (destino/nome).is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destino',type=Path,required=True)
    parser.add_argument('--aplicar',action='store_true')
    args = parser.parse_args()
    destino = args.destino.resolve()
    if destino == RAIZ or destino in RAIZ.parents or not (destino/'.env').is_file():
        raise ValueError('Informe uma instalação separada e já configurada.')
    python = destino/'.venv/Scripts/python.exe'
    if not python.is_file() or not (destino/'scripts/worker_operacional.py').is_file():
        raise ValueError('Instalação do executor incompleta.')
    # Somente arquivos rastreados do HEAD, nunca a árvore experimental local.
    subprocess.run(['git','diff','--exit-code','HEAD','--','backend','scripts/worker_operacional.py'],
                   cwd=RAIZ,check=True,capture_output=True)
    commit = subprocess.run(['git','rev-parse','HEAD'],cwd=RAIZ,check=True,capture_output=True,text=True).stdout.strip()
    pacote = subprocess.run(['git','archive','--format=zip','HEAD','--','backend','scripts/worker_operacional.py'],
                            cwd=RAIZ,check=True,capture_output=True).stdout
    with ZipFile(io.BytesIO(pacote)) as zipado:
        arquivos = [(i.filename,zipado.read(i)) for i in zipado.infolist() if not i.is_dir()]
    for nome,_ in arquivos:
        caminho_pacote(nome,destino)
    esperado = codigo_motor(python,RAIZ)
    print(json.dumps({'previa':not args.aplicar,'commit':commit,'arquivos':len(arquivos),
                      'motorEsperado':esperado,'motorInstalado':codigo_motor(python,destino)}))
    if not args.aplicar:
        return
    configs = assinatura_configs(destino)
    backup = destino/'.tmp/atualizacoes'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup.mkdir(parents=True,exist_ok=False)
    anteriores = []
    executando = tarefa('estado') == 'Running'
    if executando:
        tarefa('parar')
    try:
        for nome,conteudo in arquivos:
            alvo = caminho_pacote(nome,destino)
            existia = alvo.is_file()
            if existia:
                copia = backup/nome
                copia.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(alvo,copia)
            anteriores.append((nome,existia))
            alvo.parent.mkdir(parents=True,exist_ok=True)
            alvo.write_bytes(conteudo)
        instalado = codigo_motor(python,destino,smoke=True)
        if instalado != esperado or configs != assinatura_configs(destino):
            raise RuntimeError('Smoke ou preservação das configurações divergente.')
        (backup/'manifesto.json').write_text(json.dumps({'commit':commit,'motor':instalado,
                                                       'arquivos':anteriores},ensure_ascii=True),encoding='utf-8')
        print(json.dumps({'aplicado':True,'motor':instalado,'configsPreservadas':True,'backup':str(backup)}))
    except Exception:
        for nome,existia in reversed(anteriores):
            alvo = caminho_pacote(nome,destino)
            if existia:
                shutil.copy2(backup/nome,alvo)
            elif alvo.is_file():
                alvo.unlink()
        raise
    finally:
        if executando:
            tarefa('iniciar')


if __name__ == '__main__':
    try:
        main()
    except Exception as erro:
        # Não imprimir exceções que possam incluir configuração do ambiente.
        print('Atualização não concluída: '+type(erro).__name__)
        raise SystemExit(1)
