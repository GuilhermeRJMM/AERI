# Acesso único do Sync para o AERI

## Situação

O AERI já tem o receptor `POST /api/login/sync`. Ele recebe um ticket JWT
assinado pelo servidor do Sync, valida a assinatura e a validade, aceita cada
ticket uma única vez e cria uma sessão normal do AERI. Nenhuma senha do usuário
é enviada ou compartilhada.

O recurso ainda fica **desativado** até a configuração da chave pública. Não há
chave do Sync configurada neste código e não foi feita publicação.

## O que o Sync precisa implementar

1. Após o usuário entrar no Sync, o servidor do Sync deve emitir um JWT assinado
   com **RS256**. A chave privada deve permanecer somente no servidor do Sync.
2. O Sync deve enviar o JWT em um formulário `POST` para
   `https://aeri-two.vercel.app/api/login/sync`, no campo `ticket`. Não colocar
   o token na URL, em query string, em `localStorage` ou em JavaScript público.
3. A página do Sync deve estar disponível por HTTPS. O endereço hoje informado
   (`http://192.168.10.240:3031/app.html`) usa HTTP; antes de ativar o SSO, a
   equipe deve proteger o Sync com HTTPS e emitir o ticket no servidor.
4. O `sub` do JWT precisa corresponder ao campo `usuario` de uma conta existente
   e ativa no AERI. Não há criação automática de contas nem importação de cargos
   ou permissões do Sync: o AERI continua sendo a autoridade dos acessos.
5. Se a conta do AERI exigir MFA, o Sync precisa incluir `"mfa"` no array `amr`
   somente quando tiver confirmado o segundo fator daquela sessão.

Formulário esperado no navegador do usuário:

```html
<form method="post" action="https://aeri-two.vercel.app/api/login/sync">
  <input type="hidden" name="ticket" value="JWT_CURTO_EMITIDO_NO_SERVIDOR">
  <button type="submit">Abrir AERI</button>
</form>
```

O JWT deve ter cabeçalho `{"alg":"RS256","typ":"JWT"}` e estas claims:

| Claim | Regra |
| --- | --- |
| `iss` | `sync` por padrão; precisa coincidir com `AERI_SYNC_SSO_ISSUER` no AERI |
| `aud` | `aeri` por padrão; precisa incluir `AERI_SYNC_SSO_AUDIENCE` |
| `sub` | Nome de usuário já cadastrado no AERI |
| `iat` | Horário de emissão em Unix (segundos) |
| `exp` | Expiração em Unix; no máximo 90 segundos depois de `iat` |
| `jti` | Identificador aleatório, exclusivo, com pelo menos 16 caracteres |
| `amr` | Array de métodos usados; incluir `mfa` somente se o segundo fator foi validado |

Exemplo de payload (sem assinatura/chaves reais):

```json
{
  "iss": "sync",
  "aud": "aeri",
  "sub": "USUARIO_AERI",
  "iat": 1791470000,
  "exp": 1791470060,
  "jti": "identificador-aleatorio-unico-123456",
  "amr": ["pwd", "mfa"]
}
```

## Configuração do AERI

O Sync deve gerar um par de chaves RSA de pelo menos 2048 bits e entregar ao
AERI **somente a chave pública**. A chave privada nunca deve ser enviada ao
AERI, inserida no repositório ou entregue ao navegador.

Na Vercel, configurar:

- `AERI_SYNC_SSO_PUBLIC_KEY_PEM`: chave pública RSA em PEM;
- `AERI_SYNC_SSO_ISSUER`: emissor combinado com a equipe do Sync (`sync` por padrão);
- `AERI_SYNC_SSO_AUDIENCE`: destinatário combinado (`aeri` por padrão).

O endpoint responde com redirecionamento ao AERI e um cookie de sessão `HttpOnly`,
`Secure`, compatível com o fluxo de navegação iniciado pelo Sync. Tickets
reutilizados são recusados; somente o hash do `jti` é guardado para bloquear
repetições, e os registros expirados são limpos pela manutenção do banco.

## O que ainda falta para ativar

- Receber do Sync a chave pública e confirmar `iss`, `aud`, `sub` e `amr`.
- Configurar essas variáveis na Vercel e publicar a versão que contém o receptor.
- O Sync implementar a emissão do ticket no servidor e o formulário `POST`.
- Fazer um teste com usuário já existente e ativo no AERI, primeiro em ambiente
  controlado, conferindo que um segundo envio do mesmo ticket é recusado.

`SYNC_ORIGINS` é uma configuração separada para permitir que o AERI seja
incorporado em iframe; ela não autentica o usuário e não substitui este SSO.
