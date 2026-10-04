# ADR-0008 — Modelo operacional do LAB: golden path Go, FULL_VALIDATION fail-safe e FULL_CERTIFICATION sob demanda

| Informação | Valor |
| --- | --- |
| Estado | Proposto (Aceito com a aprovação de code owner do PR que o integra) |
| Data | 04/10/2026 |
| Owners | Containers Products (`@alric-corp/github_xj7_maintainer`) |
| Substitui | A **motivação** de prazo do [ADR-0004](0004-v1-referencia-go126.md) (rollout do primeiro E2E corporativo e bloqueio zlib). A seleção `go1-26`/`go1-26-dev` e a separação `execution_scope` × `exceptions` do ADR-0004 continuam valendo |
| Revisão | `execution_scope.review_by` em [`policies/operations/health.json`](../../policies/operations/health.json) — ver "Limitação conhecida" |
| Aplicação | `execution_scope` (visibilidade no health); `P0_04_BATCH` em [`default_batch.py`](../../scripts/pipeline/catalog/default_batch.py) e `workflow.yml` (execução); `pr_execution_scope.py` (FULL fail-safe de PR); `catalog-certification.yml` (certificação) |
| Evidência | Auditorias read-only de escopo do LAB de 04/10/2026 (runs de schedule/push do par Go, FULL validation de PR 16/16, catalog certification 35571871638) |

## Contexto

O ADR-0004 restringiu build e promoção automáticos a `go1-26`/`go1-26-dev`
como etapa temporária, por dois motivos: decisões do primeiro E2E corporativo
e o `CVE-2026-85091` (zlib), que fazia 13 frameworks falharem.

O bloqueio zlib foi resolvido upstream em 17/09/2026. A validação FULL de PR
passa 16/16 desde então. Mesmo assim, o código e a política ainda
descreviam o par Go como "perfil temporário", com revisão vencida em
30/09/2026.

As auditorias de 04/10/2026 mostraram três modos de execução. Juntos, eles
cobrem o LAB sem operar as 16 imagens diariamente:

- o par Go exercita o mecanismo compartilhado de ponta a ponta (Wolfi,
  Melange, Apko, multiarch, Trivy, trust, contrato, publicação, read-back,
  Cosign, SBOM, provenance, consumidores);
- todo PR com path compartilhado já valida as 16 imagens (build, Trivy e
  trust, sem AWS);
- `catalog-certification.yml` certifica o catálogo inteiro quando acionado.

Operar as 16 diariamente custaria cerca de 5× os job-minutes do par Go.
Além disso, acoplaria a release Go a falhas de qualquer outra linguagem: o
manifesto exige a evidência de todos os membros.

## Decisão

O LAB opera em três modos, de forma permanente (não como etapa de rollout):

1. **GO_PAIR** — `go1-26` + `go1-26-dev` é o golden path de build, publicação
   e promoção automáticos (schedule e push).
2. **FULL_VALIDATION fail-safe** — todo PR que toca um path compartilhado
   valida as 16 imagens (`pr_execution_scope.py`). Este ADR não enfraquece
   esse roteamento.
3. **FULL_CERTIFICATION sob demanda** — mudanças de classe B/C são
   certificadas com `catalog-certification.yml` antes de serem propostas
   fora do LAB.

O catálogo (16 definições), o lote FULL/DEFAULT e `exceptions` não mudam. O
LAB não passa a operar FULL permanentemente.

## Consequências

- `execution_scope.reason` deixa de citar o zlib e o primeiro E2E
  corporativo. Os frameworks fora do par continuam `out_of_scope` no health,
  sem alarme.
- Promover um manifesto FULL a `stable` continua exigindo a mudança
  revisada de `promote-dev.json`/`promote-hom.json`. A certificação FULL
  termina como candidate `WAITING`.
- Um PASS no LAB não equivale a homologação corporativa. O corporativo
  mantém seus próprios gates (`docs/corporate-production-readiness.md`).

## Limitação conhecida

`execution_scope.review_by` é exigido pelo job de saúde. Se ausente ou
vencido, ele gera o alerta `execution_scope_review`
(`operational_health.py`, coberto por testes). Este ADR **não** inventa uma
nova data: o campo permanece `2026-09-30` e o alerta continua visível até o
owner registrar a próxima data de revisão. Um modelo permanente sem data de
revisão exigiria mudar essa regra do health, o que fica fora deste ADR.

## Alternativas rejeitadas

- **FULL como schedule permanente do LAB:** rejeitada. Multiplica o custo,
  acopla a release Go a falhas de outras linguagens e não acrescenta prova
  de mecanismo. A compatibilidade de catálogo já é coberta pela certificação
  sob demanda.
- **Remover `review_by`:** rejeitada pelo motivo da limitação acima.
- **Reescrever o ADR-0004:** rejeitada; o histórico da decisão é preservado.

## Critério de revisão

Revisar quando houver: mudança no roteador FULL de PR; decisão de operar
outro framework automaticamente; ou evidência de que a certificação sob
demanda deixou de detectar regressões de catálogo a tempo.
