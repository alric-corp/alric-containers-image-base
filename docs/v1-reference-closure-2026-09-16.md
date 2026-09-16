# V1 de referência Go 1.26 — fechamento operacional, 16/09/2026

Snapshot congelado de uma única validação limpa em `main`, executada pelo
caminho normal do produto, sem alterar arquitetura, IAM, gate de Trivy ou
catálogo. Complementa
[`specs/2026-09-16-v1-reference-go126/`](../specs/2026-09-16-v1-reference-go126/)
(que registra a mudança de código) com o resultado de uma execução
hospedada real, depois do merge.

## Identidade da execução

| Campo | Valor |
| --- | --- |
| Integrated SHA | `0c7c92a893dfb17e3dd14f51dca1a25b2a529774` (merge do PR #73) |
| Run | [`35060032353`](https://github.com/alric-corp/alric-containers-image-base/actions/runs/35060032353) |
| Evento | `push` (automático, path `policies/**`) — caminho normal, sem dispatch manual |
| Conclusão | `success` |
| Attempt | 1 |
| Timestamp | 2026-09-16T05:34:08Z → 05:42Z |
| Build tag | `160926-0242-r35060032353-a1` (runtime e dev) |

Um `workflow_dispatch` manual foi criado em paralelo (`35060128418`) e
**cancelado** por ser redundante ao push automático do mesmo commit —
evitando publicação duplicada.

## Baseline e escopo

```
main == origin/main: SIM
working tree: clean
PR #73: MERGED (2026-09-16T05:34:04Z)
CATALOG_DEFINITIONS = 17  (confirmado: default_batch.py lint)
execution_scope.current = [go1-26, go1-26-dev]
```

## Stable safety (antes e depois da execução)

```
STABLE_PROMOTION_AUTHORIZED: ausente (gh variable list)
STABLE_AUTOMATIC_PROMOTION = DISABLED
promote-stable (job): skipped no run 35060032353
stable_tags_found (go1-26): 0
stable_tags_found (go1-26-dev): 0
latest_tags_found (ambos): 0
STABLE_TOUCHED = false
```

## Build once / Multiarch / Digest preservation

`validated_digest == copied_digest == remote_digest` para os dois,
confirmado no artifact `publication-*-evidence.json` do run:

| | Runtime (`go1-26`) | Dev (`go1-26-dev`) |
| --- | --- | --- |
| Índice OCI (digest publicado) | `sha256:d9342b2688702ebc1e442e1f0bbff50c5520979d730aa6d81df2495f7aedd3b8` | `sha256:32c33ce17aca62f42c09a6cf1a237eb3be67e0b15c98f684e657784d0870e193` |
| `linux/amd64` | `sha256:267c0586b16d668cd04ffd5c01b820c88a8f4af750e7feb0572d0fac9f800c6d` | `sha256:7cb573a5f440aa5bbc12571701fe3e189c7e0218f02cc6cfa89412afcaeef771` |
| `linux/arm64` | `sha256:5f77ed9266b5648d02864370fe5ec46abfa24a1f419bb3f9d0986d46278f3151` | `sha256:81f7843386fc89eb58c6f1b3bb9d1bf0831caecce2fe243340282b10790957f8` |

```
GO_BUILD_ONCE = PASS         (mesmo image.oci reusado por scan/contrato/publish)
GO_MULTIARCH = PASS          (linux/amd64 + linux/arm64, exatos, code-enforced)
GO_DIGEST_PRESERVATION = PASS
```

## Trivy / contrato funcional

```
GO_TRIVY_GATE = PASS         (bloqueante nas duas arquiteturas; nenhum
                               parâmetro de severidade/--ignore-unfixed alterado)
GO_FUNCTIONAL_CONTRACT = PASS
  runtime-go1-26-amd64.json -> status: passed
  runtime-go1-26-arm64.json -> status: passed
  go1-26-dev: companion, sem contrato independente (por design)
```

## ECR preflight (ao vivo, `aws ecr describe-repositories`)

| | `image-base-go1-26` | `image-base-go1-26-dev` |
| --- | --- | --- |
| Mutability | IMMUTABLE | IMMUTABLE |
| Exclusion filters | nenhum | nenhum |
| scanOnPush | true | true |
| Encryption | AES256 | AES256 |
| Account/Region | 712107929769 / us-east-1 | 712107929769 / us-east-1 |
| URI | `712107929769.dkr.ecr.us-east-1.amazonaws.com/image-base-go1-26` | `.../image-base-go1-26-dev` |

```
GO_ECR_PREFLIGHT = PASS
```

## Trust (Cosign / SBOM / Provenance) — verificado como consumidor externo

`scripts/verify-image.sh`, executado desta máquina, sem checkout do
repositório, contra os dois digests recém-publicados:

```
$ scripts/verify-image.sh go1-26 sha256:d9342b26... --account 712107929769 --region us-east-1
PASS: assinatura (identidade build-base-images.yml@refs/heads/main)
PASS: attestation SBOM (spdxjson)
PASS: provenance SLSA v1
RESULTADO: PASS

$ scripts/verify-image.sh go1-26-dev sha256:32c33ce1... --account 712107929769 --region us-east-1
PASS: assinatura
PASS: attestation SBOM (spdxjson)
PASS: provenance SLSA v1
RESULTADO: PASS
```

```
GO_COSIGN = PASS
GO_SBOM = PASS
GO_PROVENANCE = PASS
GO_EXTERNAL_CONSUMER_VERIFICATION = PASS
```

SBOM attestations confirmadas por digest (índice + duas plataformas) em
`sbom-publication.json` do run, `attested: true` nas três entradas.

## Infra mutation guard

```
grep de CreateRepository/PutImageTagMutability/PutImageScanningConfiguration/
PutLifecyclePolicy/SetRepositoryPolicy/TagResource/UntagResource em
.github/workflows/build-base-images.yml + scripts/pipeline/artifacts/*.py +
scripts/pipeline/release/*.py: ZERO ocorrências.

CONTAINERS_INFRA_MUTATIONS = 0
```

Nota: a IAM policy anexada ao role `alric-github-repo-1360616627` continua
mais ampla que o contrato (tem `CreateRepository`/`SetRepositoryPolicy`) —
gap já documentado em `alric-containers-registry/README.md`, não é um
mutation observado, e esta rodada não altera IAM.

## Health

```
V1_HEALTH_SCOPE = GO_REFERENCE   -- confirmado (execution_scope.current)
```

Run [`35060857899`](https://github.com/alric-corp/alric-containers-image-base/actions/runs/35060857899),
disparado após a publicação: 30 alertas `out_of_scope` (15 frameworks × 2
métricas), **zero** `alert` de publicação/stable para qualquer framework
fora do escopo atual — nenhum tratado como "failed/unhealthy". Único
`alert` real do run:

```
alert  schedule_gap_hours  17 * * * *  maior intervalo entre runs na janela: 18.62h (limite 12h)
```

Achado pré-existente e não relacionado a esta rodada (scheduler do GitHub
Actions, cron de promoção) — registrado, não mascarado, não corrigido
aqui (fora do escopo desta spec). Por isso a conclusão hospedada do job é
tecnicamente `failure` (o mecanismo de alerta funcionando como projetado
para um achado real), **não** por regressão de `execution_scope`.

```
OPERATIONAL_ALERT_DESTINATION = MISSING  (external_destination continua null)
```

## Terraform (Infra, `alric-containers-registry`)

| Momento | Run | Resultado |
| --- | --- | --- |
| Pré-publicação | [`35060496038`](https://github.com/alric-corp/alric-containers-registry/actions/runs/35060496038) | `No changes.` / `Apply complete! Resources: 0 added, 0 changed, 0 destroyed.` |
| Pós-publicação | [`35060833213`](https://github.com/alric-corp/alric-containers-registry/actions/runs/35060833213) | `No changes.` |

```
POST_PUBLICATION_TERRAFORM_DRIFT = NONE
```

## Other languages (inalterado nesta rodada)

```
OTHER_LANGUAGES_REMOVED = NO
FULL_CATALOG = PRESERVED (17 definições)
FULL_CATALOG_V1 = IN_PROGRESS
ZLIB_CVE_2026_85091 = UPSTREAM_BLOCKER (sem correção no APKINDEX do Wolfi;
                                        gate não relaxado)
```

Matriz completa por framework:
[`specs/2026-09-16-v1-reference-go126/evidence.md`](../specs/2026-09-16-v1-reference-go126/evidence.md).

## Estado final

```
ENGINE_V1 = PASS
REFERENCE_PRODUCT_V1_GO = PASS

GO_BUILD_ONCE = PASS
GO_MULTIARCH = PASS
GO_TRIVY_GATE = PASS
GO_FUNCTIONAL_CONTRACT = PASS
GO_ECR_PREFLIGHT = PASS
GO_DIGEST_PRESERVATION = PASS
GO_COSIGN = PASS
GO_SBOM = PASS
GO_PROVENANCE = PASS
GO_EXTERNAL_CONSUMER_VERIFICATION = PASS

V1_HEALTH_SCOPE = GO_REFERENCE
CONTAINERS_INFRA_MUTATIONS = 0
POST_PUBLICATION_TERRAFORM_DRIFT = NONE

STABLE_TOUCHED = false
STABLE = OUT_OF_SCOPE

FULL_CATALOG = PRESERVED
FULL_CATALOG_V1 = IN_PROGRESS

SECURITY_GATE_RELAXED = NO
```

## Veredito

**GO 1.26 REFERENCE V1 CLOSED — FUNCTIONAL, CONSUMABLE AND VERIFIABLE**
