# SPEC — P1-08 — Contrato operacional, alertas e proposta de SLO/SLA

## Objetivo

Explicar como operar a fábrica com os mecanismos existentes, suas evidências
e limites, sem criar compromissos corporativos. Fonte canônica de operação:
[M11/M04](../../docs/m11-m04-operational-health.md). A premissa de autoria e
sustentação permanece no [ADR-0003](../../docs/adr/0003-controles-seguranca-workflows-federados.md).

## Requisitos

- R1: partir da main que incorpora PR #58, preservando trabalho e snapshots.
- R2: relacionar health, pins, resumos e timing ao código, cadência, fontes,
  timestamps, limites de consulta, condições de alerta e exceções reais.
- R3: separar detecção, relatório, envio, entrega e reconhecimento. Configuração
  ou job bem-sucedido não comprova encaminhamento nem atendimento.
- R4: toda medição tem fonte, data de coleta, janela, escopo, tamanho da amostra
  e limites; ausência, truncamento ou falha não se convertem em saúde.
- R5: poucos indicadores explicitam cálculo/unidade/ausências. Separar SLI,
  SLO proposto e SLA acordado; metas sem dados/decisão ficam a definir.
- R6: responsabilidades e diagnóstico preservam gates, autoria federada,
  identidades de sandbox e decisões corporativas externas.
- R7: registrar dependência compartilhada do scheduler e critérios pendentes
  para fechar P1-08 integralmente, além da entrega documental.

## Estados

IMPLEMENTED é mecanismo no código; OBSERVED_IN_EVIDENCE é observação datada;
NOT_MEASURED indica medição ausente; PROPOSED é proposta não aprovada;
EXTERNAL_PENDING depende dos responsáveis externos. Para entrega de alertas,
NOT IMPLEMENTED e NOT VERIFIED distinguem integração ausente de prova ausente.

## Restrições

Somente documentos/spec e testes documentais pertinentes. Sem staging,
commit, push, PR, dispatch/rerun, mensagens, novos serviços ou infraestrutura.
Não alterar scripts, workflows, policies, cron, thresholds, retenção,
exceções, scanners ou controles de release. Não fechar outras fatias por
inferência nem copiar levantamentos restritos. P1-01 mantém hosted PASS
limitado; P1-02/P1-03 mantêm PENDING.

## Conclusão

Documento pronto para revisão não significa operação aceita, notificação
comprovada ou SLA aprovado. Critérios em [acceptance.md](acceptance.md).
