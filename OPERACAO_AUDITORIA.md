# Operação segura da auditoria em lote

A auditoria completa consulta a Tri7 e deve rodar fora da Vercel, em máquina controlada, com credenciais somente no ambiente. O script `scripts/auditar_semantica_tri7.py` reaproveita a saída existente e permite retomada sem duplicar matrículas concluídas.

Exemplo conservador:

```powershell
python scripts/auditar_semantica_tri7.py --inicio 1 --fim 39767 --workers 2 --rps 2 --tentativas 4 --saida output/relatorios/auditoria-semantica.csv
```

Regras operacionais:

- nunca incluir senha, token ou texto integral no repositório;
- usar arquivo de saída exclusivo por rodada e preservar a rodada anterior;
- se interrompido, repetir o mesmo comando e o mesmo `--saida`;
- usar `--base` para uma nova rodada derivada da anterior;
- consolidar filas com `scripts/consolidar_auditoria_registral.py`;
- executar todos os testes e comparar resultados estruturados antes de publicar;
- não transformar alertas heurísticos em correções automáticas.

Essa rotina não mede disponibilidade da Tri7, ONR ou banco e não verifica assinatura digital.
