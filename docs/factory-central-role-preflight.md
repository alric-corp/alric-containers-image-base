# Central role: Stage A OIDC preflight

This increment proves GitHub OIDC assumption of the existing external role
`arn:aws:iam::712107929769:role/itau-github-repo-factory-distroless-v1`
(RoleId `AROA2LTHQWCU2N3H2OE3L`). It does not change the operational resolver.
The inline IAM policy remains `factory-distroless-v1`; Terraform does not own
this identity. The baseline is `bd578e20afcb63f89ccef8d8702b470fdd18de68`.

## Execution after approved integration

The workflow `factory-central-role-preflight.yml` is manual only, with no inputs.
Both independent jobs require this repository, `refs/heads/develop` and
`workflow_dispatch`, and use the protected `DEV` and `lab-image-base-infra`
Environments respectively. Their only token permissions are `contents: read`
and `id-token: write`. The credentials action uses the repository-approved SHA,
GitHub OIDC, the exact LAB account/role and `us-east-1`, with no credentials,
profile, role chaining or operator fallback. Ambient credential reuse and
environment-to-input translation are disabled.

Each 900-second session has an inline **session** policy allowing only
`sts:GetCallerIdentity`. This does not modify the role's IAM policy. The probe
compares Account, exact assumed-role ARN/session and the RoleId prefix in UserId.
It emits JSON in the job logs and step summary with run/attempt, source SHA,
ref/event, Environment, region, expected ARN and observed identity. Credentials
and OIDC tokens are never included in this report. A failed assumption or STS
comparison cannot report PASS. No checkout, external script download, Terraform,
ECR/S3 mutation, promotion or IAM modification is part of the workflow.

After the PR is integrated and its checks pass, an authorized operator dispatches:

```sh
gh workflow run factory-central-role-preflight.yml \
  --repo alric-corp/alric-containers-image-base --ref develop
```

Observe and satisfy the existing Environment approval through its normal owner
process; do not bypass it. Record the run/attempt, actual source SHA, both job
URLs, logs/JSON summaries, Account, ARN and RoleId. Both jobs must succeed with
the expected identity before Stage B. A queued/waiting/skipped job is not a
positive proof. Retain the logs before their existing GitHub retention expires;
this PR does not create a new artifact-retention policy or durable evidence store.
Local tests use a fake STS executable: they test rejection and reporting, not
hosted OIDC authentication.

## Publication isolation

The five changed paths are this document, the new workflow, its governance test,
and narrow preflight exceptions in the existing configuration and external-IAM
contract tests. None matches the push or PR paths of `workflow.yml`. Its schedule
is untouched and can independently execute normal Factory work. No preflight
execution invokes the publisher.

The future Stage B PR will modify `scripts/pipeline/governance/configuration.py`
and `policies/pipeline/config.json`; both match the publisher's develop push
trigger. Before that merge, record an operational window, gate status and the
owner's explicit activation approval. Publication from that merge is a real DEV
operation, not part of this STS-only proof.

## Security observations and decision before activation

Read-only observations on 2026-10-09:

| Control | Observed |
| --- | --- |
| develop checks | `Unit & integration tests`, `Repository & workflow lint`; strict/up-to-date |
| Required PR approvals | 0; code-owner review and last-push approval not required |
| develop admin enforcement | Disabled |
| Stale-review dismissal | Enabled |
| Force push / branch deletion | Disabled |
| DEV deployment branch | Exactly `develop`; custom branch policy |
| DEV required reviewers | None |
| DEV admin Environment bypass | Disabled |
| Infra deployment branch | Exactly `develop`; custom branch policy |
| Infra required reviewer | `TomasAlric`; self-review permitted (`prevent_self_review=false`) |
| Infra admin Environment bypass | Disabled |
| Default workflow token | Read; Actions cannot approve PR reviews |
| Actions execution policy | Enabled; all actions allowed; SHA pinning required |
| Default branch | `develop` |

The role trust accepts the two exact immutable-repository Environment subjects,
with exact audience, repository ID and owner ID; no trust change is included.
**Both Environments share every permission of the central role.** Infra's
reviewer does not isolate Terraform/backend/ECR/S3 privileges from DEV. The
STS-only session policy narrows these preflight sessions; it does not solve
that shared-role authorization risk for future operational workflows.

Before full activation, the owner must explicitly decide DEV review requirements
and the branch-review/admin-enforcement posture. Recommend a required DEV
reviewer and review of develop's zero-approval/admin-bypass configuration before
activating shared operational privileges. This PR neither changes those controls
nor accepts their risk on the owner's behalf. The API observations are a snapshot,
not a guarantee that the controls will remain unchanged; re-read at activation.

## Stage B remains gated

Only after both hosted proofs, introduce a separate operational-role field in
versioned configuration and update strict validation/resolution. DEV and protected
INFRA_APPLY (both plan and apply jobs) will resolve the central ARN. Keep
`DEV.role_name`, legacy Infra names, Terraform ownership and HOM unchanged.
Keep `infra.plan_enabled=false` and reject any future attempt to enable privileged
PR planning until a separately reviewed authorization design exists. Preserve
the application-certification read-only session policy and all existing gates.
No Stage B code or PR is part of this increment. Frozen SBOM inputs are not read
or modified. Real ingestion follows hosted authentication and validated cutover.
