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

## Incluir um novo Registro Auxiliar na sincronização

Quando surge um Registro Auxiliar com número maior que o último já indexado (ex.: lavratura recente), ele não aparece sozinho nas buscas até ser sincronizado. Na tela **Registros Auxiliares** (ADMIN/SUBSTITUTO):

1. Clicar em **"Buscar novos"** — busca a partir de `últimoExistente + 1` em lotes de 30 números.
2. Ler a mensagem de status:
   - `"N novo(s) Registro(s) Auxiliar(es) encontrado(s)"` com N ≥ 1 → concluído.
   - `"0 novo(s)..."` → clicar novamente (cada clique avança mais 30 números) até aparecer o registro ou até constatar que ele não existe na Tri7.
3. Se depois de algumas tentativas ainda não encontrar (lacuna maior que os lotes percorridos), usar o caminho manual: preencher o campo **"Limite"** com o número do registro e clicar em **"Iniciar sincronização"** — isso estende `limiteInicial`/`últimoExistente` até esse número e processa a lacuna.

Regras operacionais:

- não editar `sincronizacao_registros_auxiliares_aeri` diretamente no banco; sempre passar pela API/tela, que mantém a trava por lease e o hash de deduplicação;
- se um número específico falhar repetidamente, ele aparece em **"Ver erros"**; usar o botão de reprocessamento em vez de tentar consultá-lo manualmente na Tri7;
- produto/modalidade/safra são extraídos por regex sobre o texto (`backend/app/servicos/registros_auxiliares.py`) — cédulas com campos de template em branco (ex.: nome do produto omitido, só com as características de qualidade) podem exigir uma assinatura alternativa nova nesse arquivo, como foi feito para o padrão CONCEX da soja.

## Forçar a revisão de um número específico

A revisão automática (item anterior) percorre a fila inteira em ordem — se um Registro Auxiliar específico acabou de receber uma averbação/retificação e a fila está longe dele, pode demorar dias até o AERI reconsultar aquele número. No campo **"Revisar um número agora"** (mesma tela, ADMIN/SUBSTITUTO), digitar o número e clicar em **"Revisar agora"**: isso consulta só aquele número na Tri7 e regrava o índice na hora, sem mexer na fila sequencial.

Duas ressalvas importantes:

- não é automático nem por webhook — alguém precisa saber que houve uma retificação e disparar isso manualmente;
- o texto retornado pela Tri7 é cumulativo (R.01 + todas as averbações), e a extração de produto/modalidade só olha presença de palavra-chave no texto inteiro, não "estado atual". Uma retificação que troca o produto (ex.: "onde se lê SOJA, leia-se MILHO") deixa o registro indexado com os dois produtos juntos, não só o corrigido — o registro fica achável em ambos, mas o índice não expressa qual é o valor vigente.
