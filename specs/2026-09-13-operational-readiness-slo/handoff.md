# HANDOFF — P1-08

Baseline: main `d60be51de7d1480b40fb333b0d1afc6d7b0d1158`, PR #58 MERGED
em 2026-09-13T21:57:07Z. Origin sandbox alric-corp/alric-containers-image-base.
Árvore inicial limpa; atualizada por fast-forward autorizado, sem replicar PR.

Estado: documentação implementada e verificada localmente; pronta para
revisão independente pelo Claude Code, **sem auto-aprovação**. Escopo em
[spec.md](spec.md), estratégia em [plan.md](plan.md), fontes/validações em
[evidence.md](evidence.md). São 11 arquivos, index vazio, deixados na main.
Sem autorização de staging/commit/push/PR, dispatch/rerun ou envio de mensagens.

## Documento canônico

[Contrato operacional M11/M04/P1-08](../../docs/m11-m04-operational-health.md):
fonte única para indicadores, estados de alerta, diagnóstico e metas propostas.
A autoria/sustentação permanece no [ADR-0003](../../docs/adr/0003-controles-seguranca-workflows-federados.md).
Não reabrir a autorização nem convertê-la em compromisso corporativo.

Limites que precisam permanecer explícitos:

- Health usa jobs, não o ECR atual; stable proxy não verifica o read-back.
- Timestamp imagePushedAt do antigo stable na seleção não mede promoção nova.
- Fila 900s na policy não é alerta implementado; PR stale é informativa.
- API/coleta limitada, ausência e truncamento não significam saúde comprovada.
- Health depende do mesmo scheduler e não monitora sua própria ausência.
- Falha, resumo/artifact, envio, entrega e reconhecimento são estados separados.

## Evidência e verificação

Janela de leitura sandbox 12/09 00:00–13/09 22:00 UTC; coleta 13/09
22:21:58–22:24:38 UTC, GET paginado. 44 runs, 16 schedule: 2 build, 12 promoção,
2 health. Ambos os health falharam e preservaram JSONs; não comprovaram
notificação/ACK. Reports têm janelas próprias desde 08/09 e SHAs históricos.
Nenhum novo percentil/SLA, inventário ECR ou execução sobre esta fatia.

Checks reexecutados: 300 unitários, 24 integração, 6 documentais; três lints,
check_ai_context e diff --check PASS. Logs e tempos na evidence. Testes
documentais validam links/sintaxe; não comprovam conteúdo de endpoints ou entrega.

## O que falta para encerrar P1-08 integralmente

1. Canal/destinatários e responsáveis corporativos reais, janela de atendimento,
   classificação/retenção e escalonamento aprovados.
2. Integração autorizada e prova de envio/entrega/ACK, incluindo falha de envio,
   por teste controlado futuro. external_destination continua null.
3. Série suficiente/completa por framework e inventário verificável para
   avaliar frescor, elegibilidade/promoção e release utilizável.
4. Avaliação dos SLOs propostos e eventual SLA acordado; META A DEFINIR onde
   faltam dados. Nenhum prazo de correção upstream ou plantão assumido.
5. Decisão sobre scheduler compartilhado, recursos/aceites externos e
   primeiro aceite operacional corporativo. Não implementar watchdog aqui.

P1-01 hosted PASS continua limitado aos frameworks/runs comprovados;
P1-02/P1-03 PENDING. Nova observação de Wolfi em health não encerra P1-03.
IAM/PKI/ECR/rede/scanner/Sigstore permanecem com seus owners externos.
Documentação aprovada não equivale a operação integralmente aceita ou SLA.
