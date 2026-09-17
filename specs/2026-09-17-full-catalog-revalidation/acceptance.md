# ACCEPTANCE — 2026-09-17 full-catalog-revalidation

| ID | Requisito | Critério observável | Comando ou inspeção |
| --- | --- | --- | --- |
| A01 | R1 | 16 definições (todas exceto `dotnet8`) buildadas via apko/melange reais, ambas arquiteturas, em CI | Run `35179012804`, jobs `Validate <framework>` (16), todos `success` |
| A02 | R2 | Nenhum framework YAML, gate, ignore policy, config de scanner, base distro, execution_scope ou default batch alterado | `git diff d2eac6e894a4f2f87e99a4f304775d034fcb7363 e308c7d` mostra só o comentário no `Makefile`; `default_batch.py lint` inalterado |
| A03 | R3 | Nenhum publish/promote/ECR nesta rodada | Jobs `build-base-images`/`promote-stable` do run `35179012804` = `skipping`; PR `#81` fechado sem merge |
| A04 | R4 | Trivy version + estado do advisory DB registrados, não só PASS/FAIL | `evidence.md` §2 (versão `0.72.0`, DB `mirror.gcr.io/aquasec/trivy-db:2` baixado `03:41:06–12Z`) |
| A05 | R5 | Evidência de `dotnet8` sem reintroduzi-lo em nenhum lote | `evidence.md` §5 (APKINDEX ao vivo + resolução de closure, sem CI) |
| A06 | R6 | ADR-0006 e matriz do catálogo atualizados sem apagar histórico | ADR-0006 com seção "Addendum" preservando o corpo original; nota de superseded no topo de `specs/2026-09-16-v1-reference-go126/evidence.md` sem editar sua matriz histórica |

## Negativos e limites

- Contrato funcional **não** roda em PR por desenho do `execution_scope`
  vigente — não é uma falha desta spec, e não foi forçado a rodar (isso
  exigiria alterar `build-base-images.yml`/`workflow.yml`, fora do
  permitido nesta rodada).
- `dotnet8` **não** teve build/scan real de CI nesta rodada — estrutural
  (ADR-0001), não uma omissão. A evidência via registro ao vivo é real
  (mesma fonte que o `apko` consultaria), mas não substitui um run de CI
  caso o Tech Lead exija essa forma específica de prova antes de decidir
  sobre `dotnet8`.
- Captura de metadado do Trivy DB no mecanismo de evidence **não** foi
  implementada (vive em `alric-containers-reusable-workflows`, revisado
  separadamente) — só recomendada.

## Aceite externo

Revisão independente de code owner ainda não ocorreu para esta spec nem
para a atualização do ADR-0006 — mesmo padrão do ADR-0006 original.
Recomendado antes de qualquer decisão de rollout apoiada nesta matriz.
