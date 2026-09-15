"""Cria a credencial exclusiva do executor uma única vez.

O token fica em .env.buscas.local, ignorado pelo Git. A chave HMAC nunca é
lida, alterada ou exportada por este script.
"""
import base64
import hashlib
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Quando o arquivo é executado como `python scripts\...py`, o Python coloca
# apenas a pasta `scripts` no sys.path. Incluímos a raiz para que `backend`
# seja importado tanto pelo executor quanto por `python -m`.
RAIZ_PROJETO = Path(__file__).resolve().parents[1]
if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))

from backend.app.database import conectar, fechar_pool, preparar_banco


def carregar_env(caminho: Path) -> None:
    """Carrega variáveis simples do .env sem substituir o ambiente atual."""
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        valor = valor.strip().strip('"').strip("'")
        if not valor or "[SENSITIVE]" in valor:
            continue
        os.environ.setdefault(chave.strip(), valor)


def main():
    destino = Path(__file__).resolve().parents[1] / '.env.buscas.local'
    if destino.exists():
        raise SystemExit('Já existe .env.buscas.local; não substituirei uma credencial.')
    carregar_env(RAIZ_PROJETO / '.env')
    token = 'aeri_hash_' + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('=')
    token_hash = hashlib.sha256(token.encode('ascii')).hexdigest()
    expiracao = datetime.now(timezone.utc) + timedelta(days=365)
    try:
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
    finally:
        fechar_pool()
    print('Credencial criada no banco e salva em .env.buscas.local.')
    print('Configure o mesmo valor como AERI_HASH_REMOTO_TOKEN na Vercel.')
    print('O valor não será exibido por este script.')


if __name__ == '__main__':
    main()
