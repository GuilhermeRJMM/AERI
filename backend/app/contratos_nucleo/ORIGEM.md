# Núcleo integrado

Origem autorizada pelo usuário: https://github.com/dudufamilia2005-cmd/Preenchedor-de-Contratos

Commit consultado: `3f1d5d2861fa39449c529e8e7e95905f9ed39ac8`.

Arquivos Python de `minutas/` preservados nesta pasta; script OCR Windows em `scripts/ocr_windows_contratos.ps1`. A integração não carrega a interface ou servidor externo e não utiliza iframe.

As adaptações AERI ficam em `servicos/contratos.py`, `servicos/documentos_contratos.py` e `rotas/contratos.py`: autenticação, GED, fila, permissões, cifragem, retenção de evidências, round-trip de empresas, decisões e ligação ao motor registral atual. O servidor standalone e o pipeline OCR upstream não são expostos como rotas.

Uma atualização upstream deve ser feita de forma revisada, mantendo esta referência e executando ambas as suítes. Não sincronizar automaticamente código remoto em produção.
