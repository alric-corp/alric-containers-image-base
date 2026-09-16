# Corporate-like target — Containers ECR & trust policies

```text
P0_04_IAM_MODEL = CORPORATE_LIKE
TARGET, NOT APPLIED. Editing these files does not change AWS.

CORPORATE_ROLE_PATTERN = corp-github-repo-<github-repository-id>
LAB_ROLE_PATTERN        = alric-github-repo-<github-repository-id>

IMAGE_BASE_GITHUB_REPOSITORY_ID = 1360616627
CONTAINERS_ROLE_TARGET          = alric-github-repo-1360616627
LEGACY_CONTAINERS_ROLE_NAME     = github-actions-image-base (currently live, unchanged this session)
```

This directory holds **target documents**, not a proposal template
(contrast with
[`../proposals/factory-permissions/`](../proposals/factory-permissions/README.md),
which models a future split execution/provisioning identity and uses
placeholders). These files are concrete for this repository's Containers
role (account `712107929769`, region `us-east-1`, scoped to
`repository/image-base-*`), and represent the **single-role**
corporate-like equalization decided for P0-04 — bringing this role's ECR
capability set in line with the observed corporate Containers role
(`corp-github-repo-1077149569`, an illustrative example of the corporate
naming pattern), not the eventual least-privilege publisher split.

- [`image-base-ecr-target.json`](image-base-ecr-target.json) — target ECR
  permission set (unchanged this round; naming/identity reconciliation
  does not touch capabilities).
- [`image-base-trust-target.json`](image-base-trust-target.json) — target
  OIDC trust, new this round: same principal/subject as the live trust
  plus explicit `repository_id`/`repository_owner_id` conditions (see
  "Role naming" and "OIDC trust" below).

## Role naming: `github-actions-image-base` (LEGACY) -> `alric-github-repo-1360616627` (TARGET)

Role identity now follows the GitHub repository's immutable numeric ID,
not the repository's function, mirroring the observed corporate pattern.
`1360616627` is `alric-corp/alric-containers-image-base`'s real repository
ID, confirmed via `gh api repos/alric-corp/alric-containers-image-base
--jq '.id'` (read-only) — and cross-checked: it already exactly matches
the ID already embedded in the **live** trust's `sub` claim
(`...alric-containers-image-base@1360616627...`), so this is not a new or
invented number, just the same fact stated as its own explicit claim.

```text
LEGACY_CONTAINERS_ROLE_NAME = github-actions-image-base
CONTAINERS_ROLE_TARGET      = alric-github-repo-1360616627
```

**No AWS change was made.** The role `github-actions-image-base` still
exists, unrenamed, unrecreated, undeleted. `alric-github-repo-1360616627`
is a prepared target name/document only — see
`alric-corp/alric-containers-registry`'s `iam/README.md`, "Migration
plan", for how a future cutover would actually apply this (create new →
switch → verify → retire legacy), which has not been executed.

The counterpart for the Infra role
(target `alric-github-repo-1371995836`, corporate-like ECR policy modeled
on `corp-github-repo-1280662205`) lives in
`alric-corp/alric-containers-registry`'s `iam/README.md`.

## What changes versus the live policy

The live policy attached to `github-actions-image-base` (read via
`aws iam get-policy-version` in a prior session of this engagement — not
re-verified by this session) is `github-actions-image-base-ecr` (v1):

```text
GetAuthorizationToken, CreateRepository, DescribeRepositories,
DescribeImages, BatchGetImage, BatchCheckLayerAvailability,
GetDownloadUrlForLayer, InitiateLayerUpload, UploadLayerPart,
CompleteLayerUpload, PutImage, PutImageTagMutability,
PutImageScanningConfiguration, TagResource, ListTagsForResource
```

Diff to this target:

| Action | Live (prior read) | Target (this file) |
| --- | --- | --- |
| `ecr:PutImageTagMutability` | present | **removed** — corporate role never observed this action; also required so this role can never widen an ECR repository's mutability, which is Infra's job |
| `ecr:ListImages` | absent | **added** — observed in the corporate role |
| `ecr:GetRepositoryPolicy` | absent | **added** |
| `ecr:SetRepositoryPolicy` | absent | **added** |
| `ecr:DeleteRepositoryPolicy` | absent | **added** |
| `ecr:StartImageScan` | absent | **added** |
| `ecr:DescribeImageScanFindings` | absent | **added** |
| `ecr:UntagResource` | absent | **added** |
| everything else | present | unchanged |

## OIDC trust: `repository_id` claim added (verified against AWS docs, not assumed)

This session confirmed against **official AWS documentation** (IAM User
Guide, "Available keys for AWS OIDC federation" → GitHub tab,
`reference_policies_iam-condition-keys.html#condition-keys-wif`) — not
GitHub's own docs — that `token.actions.githubusercontent.com:repository_id`
and `token.actions.githubusercontent.com:repository_owner_id` are real,
documented AWS STS condition keys for this identity provider, valid in a
trust policy ("Available in session: No", i.e. trust-policy-only use,
exactly this case).

```text
OIDC_REPOSITORY_ID_CLAIM_ENFORCEMENT = IMPLEMENTED (target only)
```

[`image-base-trust-target.json`](image-base-trust-target.json) adds both
as an **additional** `StringEquals` condition (AND with the existing
`sub`/`aud`) alongside the same subject the **live** trust
(`../github-actions-image-base-trust.json`, LEGACY name, unmodified) already
uses. This is defense-in-depth, not a replacement: `sub` already embeds
the same repository/owner IDs in its immutable `owner@id/repo@id` format,
so `repository_id`/`repository_owner_id` here are a second, independent
anchor to the same fact, evaluated as a separate condition key rather than
parsed out of a string.

## What this does NOT mean

```text
IAM_ENFORCED_SEPARATION = NO
```

Adding `SetRepositoryPolicy`/`PutImageScanningConfiguration`/etc. to this
role's *permission ceiling* does not authorize the publisher workflow to
*use* them. The distinction the whole P0-04 IAM model rests on:

```text
permission available
!=
permission required
!=
permission authorized for this workflow
```

`.github/workflows/build-base-images.yml`'s `PREPROVISIONED_ONLY` behavior
(`PUBLISHER_CREATE_REPOSITORY = NO`, `PUBLISHER_MUTATES_TAG_MUTABILITY = NO`,
`PUBLISHER_MUTATES_SCAN_CONFIGURATION = NO`, `STRICT_ECR_PREFLIGHT = PASS`,
already reviewed and approved) and the guard tests in
`tests/unit/pipeline/governance/test_publisher_preprovisioned_ecr.py` are
unaffected by this file and must keep passing unchanged — see
[`../../../tests/unit/pipeline/governance/test_corporate_like_iam_target.py`](../../../tests/unit/pipeline/governance/test_corporate_like_iam_target.py),
which asserts both facts together: the target grants more than the
publisher uses, and the publisher still uses none of the provisioning
actions regardless.

## Applying this (not done by this session)

These files are data. Applying `image-base-ecr-target.json` today (before
any role rename) would mean updating the managed policy
`arn:aws:iam::712107929769:policy/github-actions-image-base-ecr` (a new
policy version, or a new policy + reattachment) on the still-live
`github-actions-image-base` role. Applying `image-base-trust-target.json`
would mean updating that same role's trust policy in place — both are
independent of the naming migration and could, in principle, be applied to
the legacy-named role before it is ever renamed.

Actually cutting over to the `alric-github-repo-1360616627` name is a
separate, larger change (see `alric-corp/alric-containers-registry`'s
`iam/README.md`, "Migration plan": create the new role → attach these same
policies → validate assume-role → switch the `AWS_ROLE_ARN` repository
variable → verify → only then classify `github-actions-image-base` for
retirement). No AWS IAM mutation, `aws iam` command, or Terraform apply is
run by this repository or by this session.
