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
no generic main-branch Infra assumption and no wildcard repository trust.
Configure protection rules on `lab-image-base-infra` before executing apply.
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
