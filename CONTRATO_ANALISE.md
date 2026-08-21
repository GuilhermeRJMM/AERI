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

## Agente jurídico automático

Toda consulta pela Tri7 executa automaticamente o agente jurídico quando ele está configurado. A análise fica vinculada a `resultado_hash` e ao hash da base jurídica vigente, consulta somente trechos indexados com identificação de fonte e página e deve cobrir ônus, dados do imóvel e proprietários atuais. O backend rejeita fontes inventadas pelo modelo.

A resposta inclui o campo `agente_juridico`, com estado, análise por domínio, fontes e confiança. Se o texto da Tri7 produzir um novo hash, ou se o conjunto de normas mudar, a análise anterior deixa de ser reutilizada. O texto integral da matrícula continua sendo processado apenas em memória e não é gravado na base jurídica ou na tabela de análises.
