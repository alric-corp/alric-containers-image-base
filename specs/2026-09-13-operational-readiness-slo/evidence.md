# EVIDENCE — P1-08

Estado: documentação implementada e verificada localmente.
Revisão independente pelo Claude Code posterior. P1-08 integral permanece
pendente de operação/canal/aceites externos.

## Baseline e autorização

Diretório real: raiz do checkout do repositório `alric-containers-image-base`.
Árvore inicial limpa em `docs/federated-factory-security-controls`, HEAD
`bc773804200504c17caa1032544c9453832ac6eb`. Origin fetch/push confirmado:
`https://github.com/alric-corp/alric-containers-image-base.git` (sandbox).

Consulta `gh pr view 58 --repo alric-corp/alric-containers-image-base --json
state,mergedAt,mergeCommit,baseRefName`: MERGED, base main, merge em
`2026-09-13T21:57:07Z`, commit `d60be51de7d1480b40fb333b0d1afc6d7b0d1158`.
Após fetch, switch para main e merge `--ff-only`, HEAD == origin/main == esse
SHA. Ancestralidade do commit do PR confirmada; nenhuma replicação manual,
reset ou descarte. Não havia spec P1-08 equivalente no repositório.

Lidos AGENTS/CLAUDE, Constitution, Capability Matrix, PROJECT e WORKFLOW;
ADR-0003, RFC, consumer contract, CONTRIBUTING/testes, documentação e specs
operacionais relevantes. No workspace não há AGENTS/CLAUDE na raiz.
O roadmap local `analysis/opus-roadmap-consolidated-2026-09-11.md`, item
“Dono, canal e SLA”, é snapshot de planejamento, não fonte executável atual.
`plan/` é material conceitual; não virou backlog obrigatório ou conteúdo
copiado para o repositório. Código atual e pedido prevaleceram.

## Correspondência com a implementação

| Fonte | Fato conferido / impacto documental |
| --- | --- |
| [health.json](../../policies/operations/health.json) | Janela 7d, idades 30h/48h, cron 30h/12h; owner/escalation sandbox, external_destination null; retenção OCI 3d/demais 30d; dotnet8 review_by 2026-10-09 |
| [health workflow](../../.github/workflows/pipeline-health.yml) | 05:40 UTC ou dispatch em main; ambos os checks continuam para preservar evidence e gate final falha; upload pode avisar ausência, não comprova envio externo |
| [operational_health.py](../../scripts/pipeline/operations/operational_health.py) | Idades por job.completed_at, sem ECR/read-back; filtro workflow.yml; seis páginas de runs, uma página de jobs, orçamento de framework 300 no workflow; limitações documentadas |
| [pin_inventory.py](../../scripts/pipeline/governance/pin_inventory.py) | Falha por pin indisponível; drift Wolfi detect-only. PR stale é informativa/default CLI 7d, não lê threshold da policy; erro de listagem pode virar vazio |
| [ci_timing.py](../../scripts/pipeline/operations/ci_timing.py) | CLI sob demanda; nenhuma chamada em workflow; espera bruta e duração distintas, skipped nulo, amostra limitada/paginação de jobs incompleta |
| [pipeline_summary.py](../../scripts/pipeline/operations/pipeline_summary.py) | Resumo deriva de artifacts, não é gate; publicação pode ser listada antes de signing; escolha lexical entre artifacts não substitui verificador de retry; scan vem de build-scans |
| [seletor](../../scripts/pipeline/release/find_promotion_candidate.py), [promoção](../../.github/workflows/promote-stable.yml), [read-back](../../scripts/pipeline/release/verify_stable.py) | Idade do conteúdo pré-escrita via imagePushedAt difere do proxy health; promoted exige confirmação exata, sem timestamp próprio da confirmação no JSON |
| [testes operations](../../tests/unit/pipeline/operations/) | Cron/ausência, truncamento, exceções, promoção skipped, tempos, resumo; não são teste de entrega/ACK |

Diferenças corrigidas somente na documentação: idade de stable tratada como
proxy; fila 900s declarada mas sem avaliação de alerta; PRs antigas informativas;
30h não significam dois ciclos perdidos; Melange30d na policy, anteriormente
1d no documento; limite 300 já incorporado. A afirmação de que acompanhar o
repo comprova recebimento foi substituída por estados separados. Scheduler
compartilhado e ausência de monitoramento do próprio health permanecem explícitos.

## Fontes oficiais complementares

Consultadas em 13/09/2026, somente leitura, para qualificar os limites do
serviço; não estabelecem requisitos corporativos:

- [GitHub schedule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule): possibilidade de atraso/descarte sob carga; cron não é compromisso de execução pontual.
- [Notificações de runs](https://docs.github.com/en/actions/concepts/workflows-and-actions/notifications-for-workflow-runs): preferências/destinatários dependem de configuração e do ator do schedule; não há recibo/ACK inferido por owner da policy.
- [AWS ImageDetail](https://docs.aws.amazon.com/AmazonECR/latest/APIReference/API_ImageDetail.html): imagePushedAt descreve push da imagem, não instante de movimentação da tag.

## Evidências anteriores usadas primeiro

- [Timing 09/09](../../docs/evidence/ci-timing-2026-09-09.json): 8 runs fast checks e 5 de validação, IDs/amostras explícitos; não mede atualização até stable.
- [Checklist 09/09](../../docs/old-checklist-closure.md) e [release-readiness 10/09](../../docs/evidence/release-readiness-2026-09-10.json): execuções e falhas históricas, não disponibilidade atual.
- [Spec dotnet8](../2026-09-12-dotnet8-fora-do-lote-padrao/evidence.md): health 34586962957 em 11/09, lacuna histórica/known; não reaproveitado como medição corrente.
- [P1-09/P1-10](../2026-09-13-consumer-contract-rfc-refresh/evidence.md): P1-01 hosted PASS limitado, P1-02/P1-03 PENDING. Estados preservados.

O quadro antigo de cobertura 100%/10,2% permanece identificado como snapshot
de 09/09 no documento canônico, com amostras de 2 e 5 runs. Sua janela não
possui ali limites UTC completos/dataset suficiente para reconstituição;
não se apresenta como série atual ou base de meta. Não se reescreveram
evidências históricas nem specs anteriores.

## Consulta adicional do sandbox

Janela fechada por `created_at`: **2026-09-12T00:00:00Z a
2026-09-13T22:00:00Z**. Coleta GET iniciada **2026-09-13T22:21:58.979204Z**;
último GET **2026-09-13T22:24:38.162426Z**. A hora UTC foi conferida antes:
teto já passado. Consultas auxiliares somente leitura, sem review independente.

Comandos de reprodução da listagem e do health principal:

```bash
gh api --method GET --paginate --slurp \
  'repos/alric-corp/alric-containers-image-base/actions/runs?created=2026-09-12T00:00:00Z..2026-09-13T22:00:00Z&per_page=100'
gh api --method GET --paginate --slurp \
  'repos/alric-corp/alric-containers-image-base/actions/runs/34752279969/jobs?per_page=100'
gh api --method GET --paginate --slurp \
  'repos/alric-corp/alric-containers-image-base/actions/runs/34752279969/artifacts?per_page=100'
```

Listagem de runs: uma página, total_count 44, 44 IDs únicos. As outras 18
listagens (16 de jobs dos schedules, duas de artifacts health) usaram
paginação; itens/IDs únicos conferidos contra total_count. Sem truncamento
observado **nesta coleta**, diferente dos limites do coletor implementado.
Todos os GETs/downloads terminaram exit 0. Não é inventário de todos os tempos,
dos ECRs ou de consumidores. Fora da janela não se afirma completude.

| Recorte na janela de coleta | Quantidade / resultado agregado |
| --- | --- |
| Todos os workflows | 44 completed: 20 success, 23 failure, 1 cancelled |
| Eventos | 14 push, 14 pull_request, 16 schedule; zero dispatch |
| Schedule build diário, por grupo de jobs | 2 failure |
| Schedule promoção horária, por grupo de jobs | 12: 3 success, 9 failure |
| Schedule health | 2 failure |

Os 14 schedules da fábrica tiveram grupo único não-skipped; cron não foi
deduzido pelo horário. Builds: `34680585414`, `34745870807`. Promoções:
`34664043188`, `34676729901`, `34689625591`, `34698575947`, `34707622286`,
`34714193105`, `34722536931`, `34729624987`, `34742329778`, `34756100214`,
`34768459323`, `34777865949`. Todos attempt 1. Conclusão agregada não prova
escrita de stable, gate aprovado por framework ou release utilizável. Não
foram inspecionados scans/publicações de todo esse lote para atribuir causa
às falhas; não classificá-las automaticamente como upstream ou regressão.

## Dois artifacts de health inspecionados

| Campo | 12/09 | 13/09 |
| --- | --- | --- |
| Run / attempt | [34686168116](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34686168116) / 1 | [34752279969](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34752279969) / 1 |
| Commit | 517d2bffab084bf7fe90881ef5f288db5cebcc3f | e3ed68259f66af41e8054a4c0ac29a54082ddd60 |
| Criação do run UTC | 2026-09-12T09:33:31Z | 2026-09-13T10:36:07Z |
| Job | [103533413060](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34686168116/job/103533413060) | [103710711740](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34752279969/job/103710711740) |
| Artifact pipeline-health-1 | [10295711913](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34686168116/artifacts/10295711913) | [10316417044](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34752279969/artifacts/10316417044) |
| Expiração declarada UTC | 2026-10-12T09:35:28Z | 2026-10-13T10:38:47Z |
| Generated_at UTC do report | 2026-09-12T09:33:50.591759Z | 2026-09-13T10:36:30.724921Z |
| Janela própria do report | 2026-09-08T00:38:29Z até generated_at | 2026-09-08T00:38:29Z até generated_at |
| Runs / consultas framework / truncated | 113 / 67 / false | 131 / 80 / false |
| Catálogo naquela execução | 15 frameworks | 17 frameworks |
| Pins disponíveis no report | 43 ocorrências, zero update PRs | 52 ocorrências, zero update PRs |
| Alertas | 1 alert de lacuna horária + 2 known dotnet8 | 1 alert de lacuna horária + 4 alerts de ausência por framework + 2 known dotnet8 |

Os dois ZIPs estavam disponíveis, `expired=false`; contêm
`operational-health.json` e `tool-pins.json`. SHA-256 dos ZIPs bate com digest
da API: `aa5318cd732b534e79f05b1ea3534727c82add94fc459c2c570f8b0f33f4e7e9`
(12/09) e `30f2d4039d877ef43cfe1110e0c2f9aa823d6ebf62bbaaaa0047b3650ea23faa`
(13/09). São consultas a SHAs históricos, não novo health sobre d60be51.

Em ambos, logs mostram exit 1 de Measure operational health, upload success
e gate final failure. A API apresenta o step de medição como success por
`continue-on-error`; não usar essa conclusão isolada como ausência de alerta.
O comando recebeu `--markdown GITHUB_STEP_SUMMARY`; a UI não foi inspecionada.
Conteúdo/armazenamento do relatório comprovados, leitura humana/entrega/ACK não.

### Valores selecionados do report de 13/09

São valores já calculados no report, **não** atualização até a hora da coleta.
Aplicam-se à janela própria desde 08/09 e ao generated_at acima:

| Indicador / escopo | Observação |
| --- | --- |
| I01 diário | Último run há 2,91h; maior lacuna 24,32h; 6 runs atribuídos |
| I01 horário | Último run há 4,34h; maior lacuna 24,08h (>12h), 21 runs atribuídos |
| I02 go1-26 / go1-26-dev | 2,75h; jobs no run 34745870807 concluídos às 07:51:28Z/07:51:29Z de 13/09 |
| I03 go1-26 / go1-26-dev | 4,33h/4,32h; jobs no run 34742329778 concluídos às 06:16:42Z/06:17:09Z de 13/09 |
| I02/I03 nodejs22 | 27,12h/42,05h; publicação 12/09 07:29:10Z, escrita observada 11/09 16:33:47Z |
| I02/I03 go1-25-dev e java25-dev | null/null, sem dado na janela; quatro alerts. Não prova ausência atual no registry |
| I04 | dotnet8 conhecido, revisão 09/10; sem alerta de exceção vencida. Não comprova rotina futura |
| I05/I06 / entrega/ACK | NOT_MEASURED; sem série/inventário verificado/recibo |

Ambos os reports registram quatro schedules não atribuídos de 10–11/09,
fora da janela de coleta: 34549524103, 34538444261, 34522287463, 34502399632.
A lacuna 24,08h pertence à janela histórica do report; não foi recalculada
para 12–13/09. Nenhum percentual de disponibilidade ou novo percentil foi
calculado. A ocorrência `wolfi-signing-key` em 13/09 tem available=true e
remote_status=same; observação de monitor somente, sem encerrar P1-03.

Dados temporários fora do repo: `/private/tmp/p108-hosted-observation.json`,
`p108-collection-{metadata,requests,runs}.json`, `p108-artifact-downloads.json`,
ZIPs/reports `p108-artifact-*`, trechos de logs e manifesto
`p108-files-sha256.json`. Conteúdo relevante está resumido acima; sem dumps
de ambiente, credenciais ou relatórios corporativos integrais versionados.

## Verificação local

Executados em 13/09/2026, macOS arm64, na main acima com este diff documental.
Shared no checkout consumido `7a9b055a462eeb8552d3404c26538b44e8ccd83f`;
nenhuma alteração no repositório compartilhado.

| Comando | Resultado desta execução |
| --- | --- |
| make test-unit | PASS, exit 0; 300 testes em 5,510s |
| make test-integration | PASS, exit 0; 24 testes em 11,650s |
| make lint-local | PASS, exit 0; 52 pins/49 arquivos e lote 17−1 |
| make lint-shared | PASS, exit 0; contrato shared e retenção/cron em 11 workflows |
| make lint-workflows | PASS, exit 0; actionlint local e shared |
| python3 -B -m unittest tests.unit.pipeline.governance.test_consumer_documentation -v | PASS, exit 0; 6 testes em 0,114s, também incluídos nos 300 unitários |
| python3 -B tools/check_ai_context.py | PASS, exit 0 |
| git diff --check | PASS, exit 0 |

Logs `/private/tmp/p108-local-{unit,integration,lint-local,lint-shared,lint-workflows,docs,context,diff}.log`.
Extensão documental cobre links do documento canônico e seis arquivos da
spec e sintaxe Bash dos comandos de coleta, sem executar comandos remotos
nos testes. Não houve novo parser ou teste que simule SLA/entrega externa.
Links validam paths locais; não auditam endpoints/âncoras genericamente.
Os três links de diagnóstico ao README foram conferidos contra títulos
existentes (promoção, recovery e dependências/pins).

Critérios A01–A09: correspondência com fontes e observações descritas,
inspecionada pelo implementador. A10 também usa checks estruturais e diff.
Essa verificação local não é a revisão independente posterior.

## Arquivos e escopo

11 arquivos: `README.md`, `RFC-013-Image-Base-Completa-com-Mermaid.md`,
`docs/README.md`, `docs/m11-m04-operational-health.md`,
`tests/unit/pipeline/governance/test_consumer_documentation.py` e os seis
documentos desta spec. Fora do novo contrato/spec, referências incrementais.
Sem diffs em workflows, scripts operacionais, policies, ADRs, outras specs
ou snapshots em docs/evidence. Index Git vazio; sem staging/commit/push/PR.

## Limites e aceite

Sem consulta AWS/ECR, dispatch/rerun, envio de mensagens ou escrita externa.
Notificação externa NOT IMPLEMENTED; entrega/ACK NOT VERIFIED/NOT_MEASURED.
Meta corporativa e SLA EXTERNAL_PENDING. Histórico não foi reescrito; nenhuma
observação nova encerra P1-01/P1-02/P1-03. Revisão do implementador não é
aprovação independente; próximos aceites no [handoff](handoff.md).
