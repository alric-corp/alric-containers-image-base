# SPEC — 2026-09-16: `stable` + lifecycle de 7 dias (realinhamento RFC-013)

## Objetivo

Restaurar duas características originais da RFC-013 para `go1-26`/
`go1-26-dev`, sem redesenhar build, sem relaxar Trivy, sem remover
frameworks, sem desfazer `PREPROVISIONED_ONLY`:

1. `stable` como referência oficial de consumo.
2. Lifecycle ECR de 7 dias para builds históricos, com `stable` protegida.

Ver [ADR-0005](../../docs/adr/0005-stable-lifecycle-realinhamento-rfc013.md)
para o registro de decisão completo.

## Requisitos

- R1: `image-base-go1-26`/`image-base-go1-26-dev` (Infra,
  `alric-containers-registry`) passam a `IMMUTABLE_WITH_EXCLUSION` com
  exatamente `[{filterType: WILDCARD, filter: "stable"}]` — nenhum outro
  filtro aceito.
- R2: mutability continua sendo responsabilidade exclusiva de Infra; o
  publisher (Containers) nunca volta a chamar `ecr:PutImageTagMutability`.
- R3: o preflight do publisher (`validate_ecr_repository.py`) passa a
  exigir exatamente essa configuração, falhando fechado em qualquer
  divergência (`MUTABLE`, `IMMUTABLE` puro, filtro diferente, filtro
  adicional).
- R4: a build normal continua publicando só a build tag imutável; `stable`
  nunca é escrita nesse caminho.
- R5: a promoção de `stable` (via `promote-stable.yml`) continua exigindo
  candidato validado → re-scan → contrato → publicação/read-back → trust,
  sem rebuild/repack, e passa a verificar que runtime e dev vêm do mesmo
  build run antes de considerar a promoção coordenada válida.
- R6: lifecycle de exatamente 7 dias para imagens tagueadas, com `stable`
  protegida por prioridade de regra (não por não-coincidência de padrão).
- R7: nenhuma mudança de IAM permanente — a reconciliação de mutability dos
  dois repositórios existentes usa o mecanismo one-time já preparado
  (`alric-containers-registry/drift-remediation/`).
- R8: preview de lifecycle obrigatório antes de aplicar, com critério de
  parada se `stable` for selecionada para expiração.

## Restrições e invariantes

- Gate de Trivy (severidade, `--ignore-unfixed`, exit code) inalterado.
- Nenhum framework removido de `frameworks/`; `CATALOG_DEFINITIONS = 17`.
- `PUBLISHER_PREPROVISIONED_ONLY` continua verdadeiro — o publisher nunca
  cria nem reconfigura repositório.
- Lifecycle policy definida e versionada em `alric-containers-registry`
  (Terraform), nunca em `alric-containers-image-base`.
- Nenhum cleanup genérico de artifacts não-tagueados (assinaturas Cosign,
  attestations SBOM, provenance) introduzido nesta rodada.

## Fora do escopo

- Expandir `stable`/lifecycle para outros frameworks além de
  `go1-26`/`go1-26-dev` (depende de ECRs que ainda não existem).
- Resolver `CVE-2026-85091` (zlib) ou qualquer bloqueio upstream de outros
  frameworks.
- Repository policy do ECR (continua `DEFERRED`, decisão corporativa).
- Conceder `ecr:PutImageTagMutability` permanentemente a qualquer role.

## Dependências

| Item | Owner | Bloqueia esta entrega? |
| --- | --- | --- |
| Módulo `terraform-aws-modules/ecr/aws@3.2.0` suportar exclusion filter + lifecycle | upstream (já confirmado no código do módulo) | Não |
| Revisão independente dos PRs (image-base + registry) | Code owners de cada repositório | Sim, para merge |
| Reconciliação one-time de mutability dos dois ECRs existentes | Infra (`drift-remediation/`, execução manual) | Sim, antes de autorizar `STABLE_PROMOTION_AUTHORIZED=true` |

## Conclusão

Ver [acceptance.md](acceptance.md) e [evidence.md](evidence.md).
