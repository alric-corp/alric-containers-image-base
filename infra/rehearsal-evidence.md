# Personal LAB greenfield rehearsal — 2026-09-20 UTC

Account `712107929769`; ECR `us-east-1`; new backend `us-east-2`.
This is LAB evidence, not corporate environment certification.

## Acceptance

| Check | Result |
| --- | --- |
| `OLD_ECR_COUNT` before recreation | `0` |
| `NEW_ECR_COUNT` after recreation | `16` |
| `IMAGE_BASE_CATALOG` / `INFRA_CATALOG` | `16` / `16` |
| `CATALOG_SETS_IDENTICAL` | `YES` |
| `BACKEND_BOOTSTRAP` | `PASS` |
| `BACKEND_CREATION_FROM_ABSENT` | `PASS` |
| `BACKEND_REUSE_WHEN_PRESENT` | `PASS` |
| `BACKEND_MISCONFIGURATION_REJECTED` | `PASS` |
| `INFRA_ROLE_SEPARATED` / `BUILD_ROLE_SEPARATED` | `YES` / `YES` |
| `OLD_REGISTRY_STATE` | `FINALIZED` |
| `OLD_IAM_BOOTSTRAP_STATE` | `FINALIZED` |
| `NEW_IMAGE_BASE_STATE` | `ACTIVE` |
| `GREENFIELD_INFRA_RECREATION` | `PASS` |
| `POST_RECREATE_TERRAFORM_DRIFT` | `NONE` |
| `LAB_ARTIFACT_PRESERVATION_REQUIRED` | `NO` |
| `FULL_CATALOG_PUBLISHED` | `NO` — all 16 repositories are empty |
| `GO126_GOLDEN_PATH` | `NEXT PHASE` |
| Old registry repository | `SUPERSEDED_READY_FOR_ARCHIVE`; not archived |

## Executed proofs

[Backend creation run 35482328892](https://github.com/alric-corp/alric-containers-image-base/actions/runs/35482328892)
assumed the new environment-only Infra role, created/configured the absent S3
bucket and completed `terraform init`. Its later provider validation failed
because the initial lockfile lacked the hosted Linux package checksum. The
official Linux checksum was added without changing the provider version.

[Successful recreation run 35482563600](https://github.com/alric-corp/alric-containers-image-base/actions/runs/35482563600)
used commit `c8b72e86173495a4777f920edc7599605ff62539`. Both jobs reused the backend
and completed init. The plan was exactly 48 creates, zero changes and zero
deletes; its binary and revision checksums were verified before approval and
again in the apply job. Apply created 48 resources. The subsequent plan returned
`No changes`, and the complete graph guard verified 48 no-ops. AWS read-back
independently verified the catalog, immutable tags with only `stable` excluded,
scanOnPush, AES256, lifecycle, repository policy and new Source tags. Image count
was zero across the catalog.

The real negative backend test temporarily suspended versioning while pipelines
were stopped and before ECR recreation. `backend.py` returned `UNSAFE_VERSIONING`
and left it suspended, proving no silent reconciliation. The authorized operator
restored `Enabled`, read it back, and reran ensure successfully. The permanent
bootstrap script never repairs an existing unsafe bucket.

64 Infra unit/contract tests, four Terraform tests with AWS mocks, actionlint,
Terraform fmt/validate and independent review passed. IAM policy simulations
confirmed Build publication allowed / ECR administration denied; Infra creation
allowed / publication and destructive operations denied; writes outside the
catalog denied. Live dispatch proved the exact immutable environment OIDC
subject. The environment requires reviewer `TomasAlric`, permits only `main`,
and disables administrator bypass. Deployment approvals were recorded through
the API under the user's explicit authorization for this LAB execution.

[PR plan run 35482961202](https://github.com/alric-corp/alric-containers-image-base/actions/runs/35482961202)
also passed for [PR #93](https://github.com/alric-corp/alric-containers-image-base/pull/93),
which is merged. It assumed the separate plan role using the exact immutable
`:pull_request` subject, reused the existing backend, completed init and produced
no changes with read-only state permissions. Its backend/init/plan artifacts are
included in the local evidence archive.

## Retirement and state ownership

The old ECR root's reviewed plan contained exactly 16 repositories, 16 lifecycle
policies and 16 repository policies. Existing images/referrers were removed using
a temporary role limited to those 16 ARNs and the old backend key. Terraform then
applied the saved 48-delete plan. AWS returned zero `image-base-*` repositories;
the old state became empty and a final destroy-plan showed no changes. The
temporary policy and role were deleted immediately and absence was verified.

Old ECR destroy-plan SHA-256:
`d17d9d318886bae72e2bf1cef987234b027d8e5a7bf31a6c251ddcbade8b8ba9`.

After successful recreation, a separate reviewed five-delete plan retired only
the old registry's dedicated IAM role, its two exclusive managed policies and
two attachments. Live checks proved no other users, groups, roles, instance
profiles or permissions boundaries consumed them. That bootstrap state is also
empty, with a final destroy-plan showing no changes. The shared OIDC provider
and both S3 buckets remain. The old repository has no active AWS ownership.

Old IAM destroy-plan SHA-256:
`42774ceca5d18a2a0600efefdae5f169307dbbeac7e209656e2ab67db1737eac`.

| State | Key | Managed resources | Lineage |
| --- | --- | --- | --- |
| Old ECR, retained | `alric-containers-registry/terraform.tfstate` | 0 | `5b7cb821-64b9-286c-a606-3f341e633370` |
| New ECR, active | `alric-containers-image-base/terraform.tfstate` | 48 | `8ebde8ec-69d6-c488-23bb-b7de2500fc3c` |

The new IAM root separately owns two Infra roles and their two inline policies.
The existing Build policy was reduced in place; no role or resource was imported
into the ECR root. No state move or moved block was used.

## Operational handoff

Build and promotion workflows are paused and `STABLE_PROMOTION_AUTHORIZED=false`.
The old registry's PR/apply workflows are disabled. The shared execution repository
was not modified. No repository was archived or deleted.

The existing product CI failure resolving its shared-workflow verification
checkout predates this rehearsal and is separate from the passing Infra workflow.
[The PR's product CI run](https://github.com/alric-corp/alric-containers-image-base/actions/runs/35482961282)
confirmed both failing checks stopped at that same pre-existing checkout step.
Pre-existing local product/Windows/CRLF/UTF-8 changes were left unstaged and were
not included in the rehearsal commits.

Raw plans, state snapshots, IAM simulations, command records and downloaded run
artifacts are retained locally in the ignored rehearsal evidence archive under
`reports/greenfield-corporate-topology-20260920.tar.gz`. State snapshots and plans
are not committed. Hosted plan artifacts
expire after one day and verification artifacts after five days.

Next: port the same structure to corporate DEV and prove only the
`go1-26` / `go1-26-dev` golden path. LAB Go publication, signing, promotion and
recovery also remain a separate phase; the other 14 repositories may stay empty.
