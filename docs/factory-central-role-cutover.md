# Central operational role — Stage B activation review

This PR prepares configuration resolution. It does not merge itself, dispatch
operational workflows, change IAM or activate SBOM ingestion.

Baseline: `88ffee845cee455d2dca6af27a469844acea173d` (PR #120).
The hosted [preflight run 37983556188](https://github.com/alric-corp/alric-containers-image-base/actions/runs/37983556188),
attempt 1, succeeded in both DEV and lab-image-base-infra. Its JSONs bind the
baseline SHA, account `712107929769`, RoleId `AROA2LTHQWCU2N3H2OE3L` and distinct
`factory-preflight-37983556188-1-dev` / `-infra` sessions. This proves STS/OIDC
identity, not operational permissions or isolation between workflows.

## Versioned configuration and ownership

`policies/pipeline/config.json` adds `factory.operational_role_name`:
`itau-github-repo-factory-distroless-v1`. The existing resolver remains the only
operational source for `steps.pipeline.outputs.AWS_ROLE_ARN`; no vars, secrets,
profile or administrative fallback supplies the role.

| Scope | Resolved role | Account / region |
| --- | --- | --- |
| DEV | `itau-github-repo-factory-distroless-v1` | `712107929769` / `us-east-1` |
| INFRA_APPLY (protected plan and apply) | Same central role | Same LAB account / region |
| HOM | `alric-image-base-factory-hom` | `248908662184` / `sa-east-1` |
| INFRA_PLAN | Legacy plan name, disabled | No AWS assumption in PR |

The strict parser requires the new field and rejects invalid/unknown keys or
collision with legacy identity names. `infra.plan_enabled` must remain false;
setting it true fails closed at loading and resolution, pending a separately
reviewed PR authorization design. Pull-request events cannot emit privileged
DEV/INFRA_APPLY/HOM settings. Disabled INFRA_PLAN checks still receive their
existing legacy metadata and `INFRA_PLAN_ENABLED=false`.

`DEV.role_name` remains `alric-image-base-factory-dev`, used by
`infra/lifecycle/main.tf` to manage the legacy role. Infra plan/apply names remain
unchanged; `infra/iam` continues managing its existing resources. The central
role and inline policy `factory-distroless-v1` remain external. This increment
changes no Terraform files, state addresses, backend, trust/policy contracts,
workflow files, HOM configuration or App Certification read-only session policies.
No existing IAM identity is retired.

## Owner decision required before merge

Read-back on 2026-10-09: DEV has no required reviewer. Both Environments restrict
deployment to develop and disable admin Environment bypass. Infra requires
TomasAlric but permits self-review. Develop requires the two repository checks
and up-to-date branches, but zero approving reviews, no code-owner or last-push
approval, and does not enforce branch protection on administrators.

**DEV and Infra sessions share the full central role permissions**, including
infrastructure administration and image publication. Infra approval does not
prevent a DEV session from using those same permissions. The STS-only preflight
session policy does not restrict future operational sessions. App Certification
retains its independent read-only session policy.

The owner must explicitly select and record one of these options on the PR:

- **A — recommended:** require DEV Environment review and strengthen develop
  protection (review requirements, administrator enforcement and independent
  review posture), through an authorized Settings change before activation.
- **B:** retain current controls and explicitly accept the shared-role risk,
  recording the owner, scope and rationale. No acceptance is inferred from the
  bootstrap, preflight or preparation of this PR.

No Settings change is included. Code review remains required; author self-review
is not independent review. Whichever option is chosen, merge also requires
explicit operational activation approval and a recorded execution window.

## Merge is an operational activation

The entrypoint `workflow.yml` matches both `scripts/**` and `policies/**` on a
push to develop. Merging this PR can immediately start Build & publish using the
central role. The same changes trigger PR validation (shared-impact FULL), not
AWS publication: the publisher requires develop plus push/schedule/dispatch and
Infra PR planning remains disabled.

On merge, the current golden path selects `go1-26` and `go1-26-dev`:

1. `build-base-images` calls validation (including package/environment and
   reproducibility gates, OCI multiarch, scan and trust), planning and runtime
   contract jobs. Existing gates must all authorize publication.
2. `build-push` assumes the central role in DEV, reads the pre-provisioned ECR
   configuration and copies the validated OCI by digest without rebuilding it.
   It writes candidate tags/layers/manifests to `image-base-go1-26` and
   `image-base-go1-26-dev` in LAB ECR; signing, SPDX attestations and provenance
   add evidence to the registry/GitHub and use the existing keyless signing path.
3. `dev-stable` / `approve` verifies the published candidates and consumers,
   writes DEV release-store candidates/receipts/state, and may update the ECR
   `stable` tags and approval manifests. Current DEV policy is enabled, selects
   the runtime/dev pair and has zero soak hours. Holds, scope, watermark,
   scans/trust and other gates still apply. A successful approval job can report
   WAITING; inspect its outcome and digests before claiming stable changed.

The DEV release bucket is `712107929769-image-base-releases-dev`. A scheduled DEV
promotion can also use the new resolver after merge. Schedules/concurrency/hold
semantics are unchanged; do not disable or clear them to facilitate activation.
HOM promotion remains disabled in its policy, with its existing account/role;
recovery is unchanged. The SBOM analytics bucket/snapshot is not written by this
increment. Ordinary SPDX attestations in ECR are not analytics ingestion.

Infra Apply remains manual and protected, not a consequence of merge. A future
authorized run must preserve the same shared backend/key/default workspace,
saved plan/revision/checksum, scope verification, ECR/S3 read-back and full no-op
post-apply plan. Never apply unexpected changes merely to test authentication.
Backend/state/lock writes are possible only in that separately authorized flow.

## Activation checklist (not executed by this PR)

Before recommending merge, record the exact reviewed HEAD, passing repository,
Infra and Factory FULL checks, the owner security decision, operational window
and explicit authorization for the potential ECR/DEV release/stable writes above.
Re-read Environment/branch controls, active runs, current holds, candidate/stable
digests and relevant gate outcomes in that window; no live AWS hold/stable state
is claimed by this preparation. Do not infer authorization from a green CI.

After approved integration, retain actual source SHA/run/attempt and compare
resolver ARN, STS assumed-role ARN, account, region and job scope in operational
logs/evidence. Distinguish OIDC success from publication/DEV outcome; preserve
published and stable digests and any WAITING/FAIL reason. Do not dispatch apply
or repeat publication solely to obtain green authentication. Failure requires
investigation and a reviewed remedy, not trust expansion or legacy-role fallback.
SBOM ingestion, HGC-04 activation and legacy-role retirement remain separate.
