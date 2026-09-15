"""Cria a credencial exclusiva do executor uma única vez.

O token fica em .env.buscas.local, ignorado pelo Git. A chave HMAC nunca é
lida, alterada ou exportada por este script.
"""
import base64
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.database import conectar, preparar_banco


def main():
    destino = Path(__file__).resolve().parents[1] / '.env.buscas.local'
    if destino.exists():
        raise SystemExit('Já existe .env.buscas.local; não substituirei uma credencial.')
    token = 'aeri_hash_' + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('=')
    token_hash = hashlib.sha256(token.encode('ascii')).hexdigest()
    expiracao = datetime.now(timezone.utc) + timedelta(days=365)
    preparar_banco()
    with conectar() as con:
        with con.cursor() as cur:
            cur.execute('''INSERT INTO executores_hash_documentos_aeri
                (id,nome,token_hash,expira_em)
                VALUES (gen_random_uuid(),'executor-local',%s,%s)''', (token_hash, expiracao))
        con.commit()
    destino.write_text('AERI_HASH_REMOTO_TOKEN=' + token + '\n', encoding='utf-8')
    try:
        os.chmod(destino, 0o600)
    except OSError:
        pass
    print('Credencial criada no banco e salva em .env.buscas.local.')
    print('Configure o mesmo valor como AERI_HASH_REMOTO_TOKEN na Vercel.')
    print('O valor não será exibido por este script.')


if __name__ == '__main__':
    main()
