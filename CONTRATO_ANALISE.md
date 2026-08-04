# Contrato da análise registral

## Objetivo

O analisador é determinístico: a mesma versão, o mesmo texto e as mesmas regras aprovadas devem produzir o mesmo resultado. O contrato `2.0.0` adiciona rastreabilidade sem quebrar consumidores antigos.

## Campos novos

- `meta.motor`, `meta.versao` e `meta.modo`: identificam o motor utilizado.
- `meta.texto_persistido`: permanece `false` na análise interativa.
- `resultado_hash`: SHA-256 do resultado estruturado, usado para vincular uma conferência ao resultado exato.
- `evidencias.atos`: regra, fonte e trecho curto para cada ato apresentado.
- `evidencias.proprietarios`: origem calculada de cada titular atual.
- `evidencias.imovel`: fonte da situação e dos campos do imóvel.
- `imovel.campos_aplicaveis`: grade adequada ao tipo urbano/rural, preenchida com `NÃO CONSTA` quando o campo aplicável não foi identificado.

O texto integral recebido da Tri7 ou colado na contingência manual existe apenas durante a requisição. Ele não é incluído no feedback nem na auditoria.

## Processo de correção

1. O funcionário confere o resultado e marca **Resultado correto** ou **Solicitar revisão**.
2. Uma revisão informa a parte afetada e um comentário objetivo.
3. `ADMIN` ou `SUBSTITUTO` examina a fila privada.
4. A correção só entra no motor por mudança de código acompanhada de caso de regressão.
5. A suíte completa e o corpus de ouro devem passar antes da publicação.

Uma marcação humana não altera automaticamente a regex e não constitui comprovação jurídica por si só.
