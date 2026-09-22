# M10 — Ativar e observar a operação agendada

**Dependências:** M08 e M09; autorização operacional explícita para schedules/automação.  
**Tipo de trabalho:** Ativação controlada e observação; sem expansão automática para FULL.

## Objetivo desta sessão

Comprovar que a operação periódica em develop funciona com custos, escopo e alertas compreensíveis.

## Consultar somente

- `on`, condições e concorrência de `workflow.yml`, `promote-stable.yml` e `pipeline-health.yml`.
- `policies/operations/health.json` e somente a lógica que interpreta esses campos.
- Métricas e resultados dos primeiros runs corporativos.

Amplie a leitura apenas para a dependência necessária a um achado concreto. Caminhos completos são relativos à raiz do repositório; nomes curtos identificam workflows/scripts já citados no inventário.

## Executar

1. Confira a consistência código/policy. Na análise de origem: build `23 3 * * *`, promoção `17 * * * *`, health `40 5 * * *`; confirme a revisão real antes de usar esses valores.
2. Registre o escopo normal atual, ainda Go V1 segundo o relatório. Habilitar schedule não autoriza FULL.
3. Peça uma decisão explícita sobre operação automática de build e promoção. Não abrir promoção apenas porque o workflow está ativo.
4. Observe a janela combinada, sugerida como 24–48h no relatório, sem manter agente em espera indefinida. Cada nova sessão consulta os runs desde o checkpoint salvo.
5. Verifique execução efetiva, duração, fila, recursos por job, publicação, promoção e alertas. Não considerar verde um run que apenas resolveu defaults.
6. Ajustes de threshold exigem dados e revisão. Pausa deliberada deve ser registrada; não silenciar falhas verdadeiras nem baixar limiares só para obter verde.
7. Confirme owner e canal GitHub atual. Destino externo ausente é uma decisão operacional pendente, não uma integração que se possa declarar implementada.

## Critérios de aceite

- Schedules, escopo e política de health coerentes na revisão verificada.
- Evidência corporativa das execuções observadas e das pausas deliberadas.
- Capacidade/custo inicial por job registrados.
- Nenhuma promessa de horário exato ou SLA derivada apenas do cron.

## Quando parar

Falha recorrente, run ausente, backlog, custo inesperado ou alertas sem owner. Registre e volte somente ao marco responsável; não redesenhe toda a Factory.

## Resultado específico

Além do bloco curto de entrega definido em [CONTEXTO.md](CONTEXTO.md), informe:

```text
OBSERVATION_WINDOW =
SCHEDULE_RUNS_VERIFIED =
HEALTH_RESULT =
NORMAL_SCOPE =
```

Use valores observados ou `NÃO_VERIFICADO`; não preencha PASS antecipadamente. Atualize somente a linha deste marco e o checkpoint em [PROGRESSO.md](PROGRESSO.md).

## Prompt para a sessão

```text
Leia TODO/marcos-dev/CONTEXTO.md, TODO/marcos-dev/PROGRESSO.md e
TODO/marcos-dev/10-schedules-e-saude-operacional.md.
Execute somente M10. Observe a operação agendada no período acordado e compare os
runs com a policy. Não expanda o catálogo nem altere thresholds automaticamente.
Salve um checkpoint para a próxima sessão em vez de prometer monitoramento em
segundo plano.
Ao terminar ou bloquear, entregue o resumo curto e atualize PROGRESSO.md.
```

---

**Base documental:** Análise fornecida: seções 5.1, 6.1, 8.3 e Gate 5. Ajustes da revisão: observação não é SLA e health precisa refletir o estágio do rollout. Este marco é um roteiro; não comprova que as ações já foram realizadas.
