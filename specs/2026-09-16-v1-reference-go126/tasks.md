# TASKS — 2026-09-16: V1 de referência Go 1.26

## T01 — Kill switch de promoção automática de `stable`
- Critério: A01.
- Arquivos: `.github/workflows/promote-stable.yml`.
- [x] Implementar (`vars.STABLE_PROMOTION_AUTHORIZED == 'true'` no `if:` do job `promote`).
- [x] Verificar (`actionlint`, variável ausente confirmada, checks obrigatórios verdes).
- [x] Registrar evidência (PR #72, mergeado 2026-09-16T05:08:55Z).

## T02 — Script de verificação externa do consumidor
- Critério: A02.
- Arquivos: `scripts/verify-image.sh`, `tests/integration/scripts/test_verify_image.py`,
  `docs/consumer-verification-contract.md`.
- [x] Implementar.
- [x] Verificar (9 testes de integração; execução real contra o digest publicado).
- [x] Registrar evidência.

## T03 — ADR-0004 e `execution_scope`
- Critério: A03.
- Arquivos: `docs/adr/0004-v1-referencia-go126.md`, `docs/adr/README.md`,
  `policies/operations/health.json`,
  `scripts/pipeline/operations/operational_health.py`,
  `tests/unit/pipeline/operations/test_operational_health.py`.
- [x] Implementar.
- [x] Verificar (`make lint`; `default_batch.py lint` confirma 17 no catálogo,
  1 excluído — inalterado; 6 testes novos, todos passando).
- [x] Registrar evidência.

## T04 — Matriz completa do catálogo (17 frameworks)
- Critério: A04.
- [x] Implementar (download e parsing individual dos 13 relatórios Trivy do
  run `35049596440`; parsing estrutural do APKINDEX; inspeção de steps de
  job para build/multiarch).
- [x] Verificar (nenhuma causa agrupada sem confirmação individual).
- [x] Registrar evidência em `evidence.md`.

## T05 — Lista de expansão de ECR
- Critério: A05.
- [x] Implementar (15 repositórios `image-base-<framework>` fora de
  `go1-26`/`go1-26-dev`, confirmados ausentes via `aws ecr describe-repositories`).
- [x] Registrar evidência.

## Dependências externas

Nenhuma bloqueia as tarefas acima. Bloqueiam apenas a **expansão** futura do
`execution_scope` (fora do escopo desta spec): fix do zlib no Wolfi, decisões
do Stage 1 de `specs/2026-09-15-first-corporate-e2e/`, e a decisão de destino
de alerta externo (`external_destination`).
