# Infra IAM bootstrap

This Terraform root owns only the two new product Infra roles and their two
inline policies. Its **local state** is independent of `infra/ecr`, the S3
backend, and the role credentials used by the normal Infra pipelines. Preserve
the local IAM state securely after the one-time operator bootstrap; never commit
state or credentials. The shared GitHub OIDC provider is referenced by ARN and
is not created, imported, or modified here.

```sh
terraform -chdir=infra/iam init
terraform -chdir=infra/iam plan -var-file=lab.tfvars -out=bootstrap.tfplan
terraform -chdir=infra/iam apply bootstrap.tfplan
```

Review the explicit plan before applying. The initial graph is two roles and two
inline policies; it contains no ECR repositories, S3 buckets, IAM users, or OIDC
providers. Operator credentials are used only for this independent IAM
bootstrap. Normal ECR plans/applies assume the new roles through GitHub OIDC.

| Responsibility | LAB role | Exact subject suffix |
| --- | --- | --- |
| Infra PR plan | `alric-github-repo-1360616627-infra-plan` | `:pull_request` |
| Infra controlled apply | `alric-github-repo-1360616627-infra-apply` | `:environment:lab-image-base-infra` |
| Product build/publication | Existing `alric-github-repo-1360616627` | Existing product trust, independently maintained |

Both new trusts use `StringEquals` for `aud`, immutable `repository_id`,
immutable `repository_owner_id`, and the complete immutable subject. There is
no generic branch Infra assumption and no wildcard repository trust.
For DEV, configure `lab-image-base-infra` to allow deployments only from
`develop`, preserving required reviewers, before executing apply. Its subject
stays `:environment:lab-image-base-infra`; the PR role's `:pull_request` subject
also stays unchanged. The workflow guards constrain DEV to `develop`.
The independent product role uses an exact ref-based subject: its external
trust must switch from `refs/heads/main` to `refs/heads/develop`, without
accepting both. No remote IAM change is performed by this code migration.
See [the cutover and old-main retirement requirements](../../docs/develop-as-dev.md).
AWS documents the supported GitHub ID claims in its
[OIDC condition-key reference](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_iam-condition-keys.html).

The plan role reads the exact catalog ECR repositories. The apply role adds
creation/configuration actions and image inventory on the same ARNs. Both also
have `ecr:DescribeRepositories` on `Resource: "*"`, restricted to the ECR region:
this read-only inventory is required to detect unexpected `image-base-*`
repositories when checking exact set equality. All ECR writes and other reads
remain restricted to the exact catalog ARNs. Neither can publish images,
delete repositories, or delete images. Both can bootstrap the one named backend
bucket because backend ensure precedes `terraform init`. That exception gives
the PR role bucket-control permissions, restricted to the exact backend bucket
and its region; ECR administration and state-object writes remain apply-only.
The backend script validates existing controls without mutation and rejects
unsafe controls. Both roles can read/write/delete only the exact `.tflock`
object; neither can delete the state object or bucket. Only the default
Terraform workspace is supported. The LAB state key is
`alric-containers-image-base/terraform.tfstate`.

Both roles also have one statement on the SBOM analytics bucket created by
`module.sbom` in the shared ECR state: the exact ARN
`arn:aws:s3:::alric-distroless-sbom-<account>-<region>` (LAB:
`alric-distroless-sbom-712107929769-us-east-1`), restricted to the ECR region.
The plan role gets only the reads listed in
[`infra/s3/permissions.md`](../s3/permissions.md); the apply role adds creation
and configuration (public access block, ownership, encryption, versioning,
policy, tags). Neither gets object access or any deletion on that bucket.

The backend lives in `us-east-2`, independently of ECR in `us-east-1`. S3's
legacy `us-east-1` CreateBucket behavior can report success for an already owned
bucket during a creation race. Backend creation uses another region to ensure
that this collision fails closed; see the
[S3 CreateBucket API](https://docs.aws.amazon.com/AmazonS3/latest/API/API_CreateBucket.html).

`build-publication-policy.json` is the reviewed replacement document for the
existing build role's managed policy
`alric-github-repo-1360616627-ecr`. The role and managed policy remain outside
this bootstrap state; update that existing policy with an auditable operator
step, recording the prior document and new default version. The replacement
allows publication/read on the exact 16-repository catalog and authentication,
with no ECR administration, Terraform, S3, or IAM permissions. Catalog permission
does not trigger catalog publication; the next product proof is exclusively
`go1-26` and `go1-26-dev`.

Legacy registry IAM retirement is a separate operation, pending explicit
classification and authorization. Successful destruction of the old ECR state
does not authorize deleting its IAM role/policies, its backend, or the shared
OIDC provider. Record legacy resources and any remaining ownership before
reporting the registry as ready for archive; do not archive it automatically.

## Central Factory role: external ownership (v1)

The operational role `itau-github-repo-factory-distroless-v1` and its only inline
policy `factory-distroless-v1` are **not managed by Terraform**. LAB provisioning
is an operator step with `Tomas-Instructor`; corporate provisioning belongs to
the IAM team via a ticket. The reviewed reference documents are
[`factory-distroless-v1.trust.json`](../../policies/aws/factory-distroless-v1.trust.json)
and [`factory-distroless-v1.inline-policy.json`](../../policies/aws/factory-distroless-v1.inline-policy.json).
No workflow applies them. See the [external IAM contract and LAB runbook](../../docs/factory-distroless-v1-iam-runbook.md)
for exact subjects, permissions, quota checks, collision handling and API read-back.

This root keeps only the legacy Infra roles and their inline policies at their
existing addresses. There are no central-role resources, variables, outputs,
preconditions or state dependencies. The existing local IAM state, lifecycle
DEV identity, ECR/S3 state and workflows are preserved. Do not apply this root
to provision the external identity or use state operations to transfer ownership.

The external policy preserves the reviewed scopes and removes only the invalid
IAM action `ecr:ListImageReferrers`; the API uses `ecr:BatchGetImage`, which remains
on the same repository ARNs. It has eleven statements and 4,740 characters
without formatting whitespace, below the aggregate 10,240-character inline-role
quota. Athena/Glue and IAM administration are excluded. Effective analytics
bucket listing remains bucket-wide because the reviewed Terraform HeadBucket
grant already requires `s3:ListBucket`; the snapshot listing statement does not
narrow that earlier Allow.

Offline contract tests run with `python3 -B -m unittest discover -s infra/tests -p test_external_iam_contract.py -v`.
The three existing mocked Terraform tests for the legacy Infra identities stay
in `tests/boundaries.tftest.hcl`. Neither suite provisions the central role.
A later PR introduces a separate operational-role configuration reference after
approved IAM read-back; it must preserve `DEV.role_name` while lifecycle still
manages that legacy role. No HOM cutover or automatic legacy retirement is included.
