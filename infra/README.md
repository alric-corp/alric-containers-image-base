# Product infrastructure

The factory remains at repository root. `infra/ecr` owns its ECR repositories;
`infra/iam` independently bootstraps the Infra identities. Shared image execution
remains in `alric-corp/alric-containers-reusable-workflows`. The historical
registry repository and its drift-remediation mechanism are not dependencies.

## Greenfield roots and catalog

`infra/ecr` reads `../../frameworks/*.yaml`. The current 16 definitions produce
16 instances of the pinned upstream ECR module 3.2.0. Its enabled resource graph
contains a repository, lifecycle policy and repository policy per definition:
48 managed resources. Tests exercise the actual module using an AWS mock, and
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
| Existing product Build | Existing exact main subject | Publish/read images; no Terraform or ECR administration |

Trust uses exact audience, repository ID, owner ID and subject. Infra trust has
no generic main-branch subject or repository wildcard. The LAB environment limits
deployment to `main` and requires its configured reviewer. Both dispatch jobs
use the environment so no unprotected branch session is needed to plan an apply.

PRs run static checks without AWS; only same-repository PRs receive the plan
identity. Fork PRs never receive AWS. `infra-apply.yml` is dispatch-only, with no
scheduled apply. It uploads the binary plan and SHA-256 checksum, pins both jobs
to the same commit, and applies only that exact plan. Its final plan must have
exit code zero and pass the complete no-op graph check. AWS read-back independently
checks all 16 repositories and their policies. The rehearsal also requires them
to be empty; `--expect-empty` is removed only in the later product phase.

Repository variables:

| Variable | LAB value |
| --- | --- |
| `AWS_ACCOUNT_ID` | `712107929769` |
| `AWS_REGION` | `us-east-1` |
| `INFRA_BACKEND_REGION` | `us-east-2` |
| `INFRA_TF_STATE_BUCKET` | `712107929769-alric-containers-image-base-tfstate` |
| `INFRA_PLAN_ROLE_ARN` | `arn:aws:iam::712107929769:role/alric-github-repo-1360616627-infra-plan` |
| `INFRA_APPLY_ROLE_ARN` | `arn:aws:iam::712107929769:role/alric-github-repo-1360616627-infra-apply` |

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
