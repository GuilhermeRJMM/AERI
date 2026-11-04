# Nota formal e resumo para o cliente

O Gerador de Notas entrega um único DOCX: a nota formal completa seguida, em nova página, do resumo em linguagem simples. Não existe opção de geração sem resumo nas rotas do módulo.

## Conteúdo e manutenção

Os 72 modelos estão em `backend/app/gerador_notas/dados/resumos.json`, separados do catálogo jurídico. Cada modelo explica a pendência, o motivo e a providência. Os campos são preenchidos com os mesmos valores usados na nota formal, sem consultas a modelos de linguagem ou criação de fundamentação durante o uso.

As condições sobre assinaturas e protocolo separado são acrescentadas quando o texto formal do item as exige. Alternativas, prazos e condições específicas foram mantidos nos respectivos modelos simples. Os marcadores de revisão jurídica existentes não são alterados. Acrescentar uma exigência exige cadastrar também seu resumo: a geração falha de forma explícita se faltar esse modelo.

## Vinculação e entrega

A ordem dos itens é a mesma nos dois textos. A prévia se atualiza com os dados da nota. O resumo identifica protocolo, título, espécie e referência conjunta calculada sobre a nota e o resumo gerados. Essa referência não é assinatura digital nem prova de integridade de um arquivo posteriormente editado no Word. Após edição externa, é necessário conferir e atualizar os dois textos.

O botão gera somente um arquivo. O funcionário deve entregar o DOCX completo ou sua conversão integral para PDF. Não há integração de envio ao cliente, integração com o totem ou postagem na Tri7 nesta alteração.

O anexo tem o título centralizado RESUMO, itens em maiúsculas e rótulos destacados. Detalhes opcionais previamente rotulados no modelo editorial, como Na ART, No memorial e Na matrícula, são exibidos em linhas recuadas quando seus valores estão preenchidos. Motivo e providência seguem o mesmo recuo. O texto formal e o timbre não são alterados por essa formatação.

As rotas `/api/gerador-notas/previa` e `/api/gerador-notas/gerar` devolvem também o objeto `resumo`, com itens estruturados, para futura integração autenticada. Nenhuma rota pública de consulta foi criada, e não há armazenamento novo de dados pessoais. A auditoria registra espécie, quantidade e versão do resumo, sem seus textos.

## Validação

Os testes cobrem os 72 itens nas quatro espécies, preservação exata dos parágrafos XML formais, preenchimento, ordem, alternativas, assinaturas, protocolo separado, escape de HTML, sessão/CSRF e geração conjunta. O navegador testa o motor real com dados fictícios. A inspeção do DOCX foi feita por conversão com Word instalado, pois o renderizador do pacote não encontrou LibreOffice.

## Timbre do cartório

O molde operacional `molde-nota-cartorio.docx` usa cabeçalho, rodapé, imagens, estilos e geometria A4 do arquivo aprovado da sede nova. As mesmas referências de cabeçalho e rodapé atendem todas as páginas, incluindo o resumo. Arial 10 é mantida nos textos do motor. As fontes binárias incorporadas e o customXml do Google Docs foram removidos da cópia operacional para reduzir o tamanho; os bytes da logo, do cabeçalho e do rodapé foram preservados. O arquivo original da rede não foi alterado.

A importação pode ser reproduzida com `scripts/preparar_timbre_notas.py`, recebendo o caminho do modelo aprovado. A origem usada tem SHA256 `8d5ccec04193e188157a7fdd02e7a0cb76e97d4a8f5fcc71bae961be3e8db6cd`. Os testes verificam a identidade do timbre e se todos os relacionamentos internos continuam válidos.
