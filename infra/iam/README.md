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

## Central Factory role (v1)

`factory.tf` adds, in this same local bootstrap state, the LAB role
`itau-github-repo-factory-distroless-v1` (`var.factory_role_name`) and four
customer-managed policies attached to it. It is additive: the two Infra roles,
their inline policies, the lifecycle DEV role (`infra/lifecycle`,
`DEV.role_name`) and every workflow role ARN stay unchanged until a separate
configuration cutover. No OIDC provider, IAM user, access key or IAM
administration permission is created.

Trust: `StringEquals` on `aud`, `repository_id`, `repository_owner_id` and the
two exact subjects `<prefix>:environment:lab-image-base-infra` and
`<prefix>:environment:DEV`; both Environments allow only `develop`. There is no
`:pull_request`, branch/ref or wildcard subject, so PR planning keeps no
privileged AWS access. Sessions last up to 3 hours (10800 s).

| Policy suffix | Domain | Scope |
| --- | --- | --- |
| `-infra` | A — Terraform | Exactly the Infra apply document above: backend bucket, state object, `.tflock` (the only deletable object), ECR configuration on the 16-repository catalog, regional repository inventory, analytics bucket configuration |
| `-ecr` | B — build/publication | `ecr:GetAuthorizationToken` (`Resource: "*"`, region-bound, the API has no ARN) and the proven DEV read/push actions on the exact catalog |
| `-releases` | C — DEV release store | `s3:ListBucket` on `DEV.release_bucket`; `s3:GetObject`/`s3:PutObject` on its objects (proven DEV scope; the bucket policy still requires `If-None-Match` for immutable records). No deletion |
| `-sbom` | D — SBOM snapshots | `s3:PutObject`, `s3:GetObject`, `s3:GetObjectVersion` on `sbom-analytics/poc-v1/snapshots/*` and prefix-limited `s3:ListBucket`. The bucket policy still requires `If-None-Match: *`. No deletion |

Domain E (Athena/Glue) is planned for this same role but not attached: a
separate increment will scope it to the approved POC workgroup, database,
tables/views, the snapshot Parquet prefixes and `query-results/poc-v1/`, after
those resources and controls are approved. No workgroup, database or SQL is
created here.

Bootstrap is the same operator process as above, from the original local state
with a new reviewed plan: only creations of the role, the four policies and the
four attachments are acceptable. Pending drift on the existing Infra inline
policies (for example a console change) is reconciled in its own reviewed step,
never inside the central-role plan. Legacy roles are retired only after the
cutover proves every LAB/DEV flow on the central role.
