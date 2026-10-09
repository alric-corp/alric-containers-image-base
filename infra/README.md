# Product infrastructure

The factory remains at repository root. `infra/ecr` owns its ECR repositories
and calls the SBOM analytics child at `infra/s3` in the **same** state;
`infra/iam` independently bootstraps the Infra identities. Shared image execution
remains in `alric-corp/alric-containers-reusable-workflows`. The historical
registry repository and its drift-remediation mechanism are not dependencies.

## Greenfield roots and catalog

`infra/ecr` reads `../../frameworks/*.yaml`. The current 16 definitions produce
16 instances of the pinned upstream ECR module 3.2.0. Its enabled resource graph
contains a repository, lifecycle policy and repository policy per definition:
48 ECR managed resources. The six explicitly named S3 resources add to that
graph without moving ECR addresses. Tests exercise the actual modules using an AWS mock, and
`verify_plan.py` checks the complete real plan before apply. There are no imports,
moved blocks or state-migration operations.

Repositories use AES256, scanOnPush, immutable tags with only `stable` excluded,
the established seven-day lifecycle and organization pull policy, and
`Source=alric-corp/alric-containers-image-base`. `force_delete=false` remains the
permanent configuration. Publication is a separate operation.

## Backend bootstrap policy

Every workflow runs `backend.py ensure` before `terraform init`. The script is
independent of Terraform and never creates a bucket through the ECR root state.

* A confirmed absent bucket is created with explicit ownership, encryption,
  versioning and all four public access blocks; every control is read back.
* A correctly configured existing bucket is only read and reused.
* An existing unsafe bucket, access denial, wrong account/region, creation
  collision or partial bootstrap fails. Existing controls are not reconciled
  automatically. An operator must investigate before retrying.

The LAB uses a new bucket, `712107929769-alric-containers-image-base-tfstate`, in
`us-east-2`, with key `alric-containers-image-base/terraform.tfstate`. ECR remains
in `us-east-1`. Backend region is a separate variable. Absent-bucket creation in
`us-east-1` is rejected because [S3's legacy CreateBucket behavior](https://docs.aws.amazon.com/AmazonS3/latest/API/API_CreateBucket.html)
can report success for an already owned bucket during a creation race. Existing
safe buckets in that region can still be validated. All Infra workflows share
one concurrency group. State uses native S3 locking and server-side encryption.

The old LAB bucket and finalized state remain retained as retirement evidence;
they are not used by the new root. The backend bucket is owned by the explicit
pipeline bootstrap contract, outside both Terraform roots.

## IAM and workflow boundaries

`infra/iam` has a separate local bootstrap state. Cloud/IAM must provide these
identities before their first pipeline use; the shared OIDC provider is referenced
and never created or deleted here. No static AWS credentials are stored in GitHub.

| Identity | OIDC context | Responsibility |
| --- | --- | --- |
| Infra plan | Exact immutable repository subject ending `:pull_request` | Read ECR, ensure this backend, read state, acquire/release its lock |
| Infra apply | Exact immutable repository subject ending `:environment:lab-image-base-infra` | Manage this catalog and its state; ensure this backend |
| Existing product Build | Exact `refs/heads/develop` subject required by the DEV contract | Publish/read images; no Terraform or ECR administration |

Trust uses exact audience, repository ID, owner ID and subject. Infra trust has
no generic branch subject or repository wildcard. The existing LAB environment
still limits deployment to `main`; the authorized cutover must change that
restriction to `develop` and preserve the configured reviewer. Both dispatch
jobs use the same environment and require `refs/heads/develop` in code. The
environment-based Infra subject does not change. Publisher trust is ref-based
and requires a separate external update; editing its JSON does not update IAM.
See [the cutover procedure](../docs/develop-as-dev.md).

PRs targeting `develop` run static checks without AWS; only same-repository
PRs targeting `develop` receive the plan
identity. Fork PRs never receive AWS. `infra-apply.yml` is dispatch-only, with no
scheduled apply. It uploads the binary plan and SHA-256 checksum, pins both jobs
to the same commit, and applies only that exact plan. Its final plan must have
exit code zero and pass the complete no-op graph check. AWS read-back independently
checks all catalog repositories and their policies, including when images exist.
`--expect-empty` remains an optional greenfield-rehearsal check, not an incremental
S3 prerequisite. The S3 collision preflight and configuration read-back preserve
JSON diagnostics and expose the applied protocol-v1 ingestion configuration.
See [the S3 contract and application prerequisites](s3/README.md).

The historical greenfield initialization ran through the protected dispatch.
This incremental S3 adoption requires that existing ECR state; an empty/wrong
state is rejected rather than used for recreation. PR plans reuse that
state with read-only state permissions (plus locking). The provider lockfiles
include verified Linux amd64 and macOS arm64 checksums, so readonly initialization
works in both the hosted runner and the LAB operator environment.

Pipeline settings come from [`policies/pipeline/config.json`](../policies/pipeline/config.json):

| JSON field | Current value |
| --- | --- |
| `DEV.account_id` / `DEV.region` | `712107929769` / `us-east-1` |
| `infra.backend.region` | `us-east-2` |
| `infra.backend.bucket` | `712107929769-alric-containers-image-base-tfstate` |
| `infra.backend.key` | `alric-containers-image-base/terraform.tfstate` |
| `infra.plan_role_name` | `alric-github-repo-1360616627-infra-plan` |
| `infra.apply_role_name` | `alric-github-repo-1360616627-infra-apply` |

Roles derive their ARN from the DEV account and the configured name. Workflows
load and validate this file before obtaining AWS credentials or ensuring the
backend. `infra.plan_enabled=false` currently skips the AWS PR plan while the
credential-free contracts and mocked Terraform checks still run. It preserves
the disabled path previously indicated by the absent `INFRA_PLAN_ROLE_ARN`.
See the [configuration and migration contract](../policies/pipeline/README.md).

Corporate adoption substitutes the account, identities, backend, organization
policy and environment configuration. The physical topology stays the same:
`itau-xj7-container-image-base` contains product + Infra, and
`itau-xj7-reusable-containers-products` contains shared execution.

## Verification and retirement

```sh
python3 -B -m unittest discover -s infra/tests -p 'test_*.py'
terraform -chdir=infra/ecr init -backend=false -lockfile=readonly
terraform -chdir=infra/ecr validate
terraform -chdir=infra/ecr test
actionlint .github/workflows/infra-pr.yml .github/workflows/infra-apply.yml
```

The destructive LAB rehearsal has its own saved plan and evidence, outside the
permanent product workflows. Only the 16 old ECR repositories, their contents
and their 32 policies may be destroyed. The old state must be empty and a final
destroy-plan must show no changes before recreation. Temporary destructive
permissions must be removed immediately, including when the operation fails.
Neither the new Infra roles nor the Build role receives repository/image deletion
permissions. No shared OIDC provider, unrelated IAM identity or backend is deleted.

`LAB_ARTIFACT_PRESERVATION_REQUIRED=NO`. Build and promotion are paused during the
rehearsal. Recreating the catalog does not publish it. The next phase is only
`go1-26` + `go1-26-dev`: multiarch build, scan, functional contracts, signed and
attested candidate, promotion, recovery and another Terraform no-change check.
The old registry repository is not deleted or archived automatically.
