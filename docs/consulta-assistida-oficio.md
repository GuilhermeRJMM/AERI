# Consulta direta ao Ofício pelo Analisador

## Operação diária: sem arquivos de importação

1. Deixar o conector local aberto e o Ofício autenticado no Chrome.
2. No Ofício, deixar a listagem histórica completa de Intimações, página 1,
   sem filtros de data, protocolo, situação, prenotação ou solicitante.
3. No Analisador: **Intimações → Consultar Ofício Eletrônico → Consultar agora**.
4. Acompanhar a leitura ali mesmo. O resultado aparece automaticamente junto
   a cada IN cadastrado, ao lado da tarefa interna.

**Não há geração, escolha ou importação manual de JSON neste fluxo.** O
programa antigo `consultar.py` ficou apenas como ferramenta de diagnóstico.

O conector não abre INs/mensagens, não envia documentos, não aceita, cancela
ou muda pedidos no Ofício. Sua única requisição ao portal é a paginação da
listagem já preparada. POST de paginação é consulta, não envio de notificação.
O status externo não sobrescreve tarefa, fase, RTD ou conferência interna.

## Uma vez, antes da ativação

### Servidor / homologação

- `OFICIO_CARTORIO_ID`: identificador da serventia no portal. Os testes de
  Morrinhos confirmaram `8422`; não reutilizar em Campo Alegre.
- `OFICIO_TOTAL_HISTORICO_MINIMO`: piso histórico confirmado para a primeira
  consulta. Em 10/11/2026 foram **257**, não 49 em tratativa. Conferir o valor
  atual antes de configurar outra instalação. Após a primeira leitura, o
  maior total anterior também serve de piso. Novos pedidos são aceitos sem
  digitar diariamente o total. Se o portal remover pedidos históricos, o
  responsável precisa conferir e ajustar o piso/dado anterior conscientemente.
- Aplicar as migrações 067/068 pelo mecanismo normal, primeiro em homologação.
  Elas não alteram as tabelas operacionais de intimações/RTD.
- Não instalar Chrome, MCP ou reverse-api-engineer no servidor/Vercel.

A publicação do site não instala o conector no computador. As duas variáveis
acima precisam estar configuradas na implantação antes de parear a conta.

### Computador Windows

Requer Chrome com auto-connect habilitado em
`chrome://inspect/#remote-debugging`, Node.js/npx e Python 3.12.
O ambiente isolado já instalado neste computador é:
`%LOCALAPPDATA%\AnalisadorRGI-Lab\reverse-api-venv`.
Para outro computador, criar um ambiente isolado e instalar
`scripts/oficio/requirements-local.txt` nele. Não alterar as dependências
do backend. São usados reverse-api-engineer 0.15.0, MCP 2.3.0 e o transporte
chrome-devtools-mcp@1.12 fixado pelo repositório. Não há agente autônomo,
chave de IA ou envio de páginas a modelos.

1. No Analisador, abrir **Conexão deste computador → Gerar código de conexão**.
2. Executar `scripts/oficio/Iniciar-Conector.ps1`. Na primeira vez, informar
   a origem HTTPS exata desta instalação e colar o código quando solicitado.
   O código não vai em URL, argumento, variável de ambiente ou log.
3. O código vale 5 minutos e é de uso único. Após parear, a credencial fica
   protegida por **DPAPI do usuário Windows** — não fica em texto puro.
4. Manter a janela do conector aberta durante o uso. Nas próximas vezes,
   executar o mesmo iniciador sem gerar outro código, enquanto a conexão
   continuar válida. Nenhuma tarefa agendada/serviço é instalado automaticamente.
5. Ao consultar, autorizar a conexão do Chrome se aparecer a confirmação.
   A conexão é reaproveitada entre consultas durante essa execução; não há
   promessa de autorização permanente quando o programa/Chrome reiniciar.

**Desconectar conector**, no Analisador, revoga suas credenciais e trabalhos
pendentes. Cada conector pertence ao usuário que o pareou e só recebe
consultas solicitadas por essa conta. O resultado externo pode ser lido
pelos usuários locais com permissão de ver intimações, como os demais dados
do módulo. O conector de outra conta/computador precisa de seu próprio
pareamento; novo pareamento da mesma conta substitui o anterior.

## Segurança e limites

- Somente HTTPS de saída do conector para uma origem fixada. Não há porta
  localhost, CORS aberto, websocket de controle ou proxy genérico de navegador.
  Redirecionamentos HTTP são recusados para não encaminhar credenciais.
- O cookie/certificado/PIN do Ofício continua no Chrome. O servidor recebe
  apenas protocolo, prenotação, status, datas de status/pedido e texto do
  prazo de purga — não mensagens, anexos, nomes, CPF ou HAR.
- Código/token têm 256 bits de aleatoriedade; só o hash é guardado no banco.
  Token revogável de até 30 dias, vinculado à conta/serventia. Cada chamada
  reconfere conta ativa, troca obrigatória de senha e permissões locais.
- Solicitar consulta e parear/revogar exigem sessão, CSRF e
  `alterar_intimacoes`. Ver resultados exige `ver_intimacoes`.
- Um trabalho ativo por conta, expiração em 5 minutos, retirada atômica e
  resultado aceito só do conector que o retirou. Expirado, duplicado ou de
  outro usuário é recusado. Falha não apaga a última captura válida.
- Total/páginas/ordem/cartório/colunas e INs únicos precisam conferir. Até
  100 páginas/2.000 INs, consulta sequencial com 400 ms entre páginas.
- A leitura é só da lista preparada. O bug do Ofício pode mostrar somente
  os pedidos recentes até o operador entrar num IN autorizado, voltar e
  filtrar de novo. O conector **não faz essa abertura**: abrir mensagem pode
  ter efeitos de leitura no portal. Recorte abaixo do piso é recusado.
- O filtro `filterAptoEdital` é opcional, pois não é renderizado na tela real
  observada; se aparecer preenchido, a consulta é bloqueada.
- O prazo de purga é texto externo, não um prazo legal recalculado. Ausência
  de IN na lista não significa arquivamento. Status externo e tarefa interna
  têm significados diferentes e não geram confirmação automática.
- Não é API oficial/homologada ONR. A utilização permanece sujeita à
  autorização/regras do portal. A captura não é transacional: mudanças entre
  páginas podem ocorrer mesmo com contagens consistentes.

## Verificações

Os testes usam banco simulado e rede externa bloqueada nos cenários de UI.
Cobrem conta/cartório, token, revogação, corpo limitado, posse/expiração do
trabalho, captura parcial, DPAPI e operação sem arquivos de captura. O teste
de navegador cobre botão → fila → leitura → resultado, erro de conector,
logout, tema branco, computador/celular e nenhuma conferência automática.
Em 10/11/2026, as migrações, o pareamento, o ciclo fila/resultado, a posse do
trabalho e a revogação passaram em PostgreSQL 17 local isolado. Duas retiradas
simultâneas entregaram o trabalho a apenas uma transação. Os esquemas
sintéticos foram removidos ao final; nenhum dado do cartório foi utilizado.
O conector também leu 257 INs em 26 páginas do Chrome real, com retorno em
memória e sem importar a captura no banco real. Não foram incluídas alterações
do assinador SERPRO.

Referências:
https://github.com/kalil0321/reverse-api-engineer
https://github.com/ChromeDevTools/chrome-devtools-mcp
