# Gerador de Notas — preenchimento pelo protocolo

Ao digitar o protocolo, a tela aguarda 750 ms e consulta a descrição literal
do título em `/api/v1/imoveis/protocolo-completo`, pela integração Tri7 já
configurada. Também é possível usar o botão de consulta para tentar novamente.

- Preenche somente **Título apresentado**, campo `descricao_titulo` da Tri7.
- Não presume espécie da nota, título judicial, dados das exigências ou natureza
  formal a partir do título; essas informações permanecem sob controle do usuário.
- Título manual não é sobrescrito. A tela oferece aplicar a descrição da Tri7.
- Ao trocar o protocolo, somente o título preenchido automaticamente é retirado.
- Resposta de um protocolo anterior, logout ou troca de conta não pode preencher
  o campo. Falha ou descrição ausente permite continuar manualmente.
- A consulta exige sessão, permissão do Gerador de Notas e CSRF. Não retorna
  pessoas, documentos, GED ou a resposta completa da Tri7 ao navegador.
- Nenhuma alteração em banco, assinatura SERPRO ou instalação Campo Alegre faz
  parte desta publicação.

Verificação: testes de resposta/erros/identidade do protocolo e navegador Chrome
em desktop/mobile; consulta real somente leitura ao protocolo 186804 confirmou
o campo e o número. Nenhuma nota foi expedida durante os testes.
