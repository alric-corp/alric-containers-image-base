# SBOM analytics storage in the existing state

This is a child module of `infra/ecr`, selected by `source = "../s3"`. It has
no backend, provider configuration, credential/profile selection or independent
lockfile. Plan/apply execute only from `infra/ecr`; the existing ECR addresses,
S3 backend, key, default workspace and native locking remain unchanged.

The LAB configuration supplies account `712107929769` and region `us-east-1`.
The root derives `alric-distroless-sbom-712107929769-us-east-1` from that expected
account/region; `sbom_bucket_name` can select an explicitly authorized name.
The child has no LAB account or region literals. Its caller account precondition
compares the provider session with the independently supplied expected owner.
The backend remains in `us-east-2`; its region is not the bucket/provider region.

## Six resources and controls

All six addresses are `module.sbom.<type>.sbom`, with types:

- `aws_s3_bucket`
- `aws_s3_bucket_public_access_block`
- `aws_s3_bucket_ownership_controls`
- `aws_s3_bucket_server_side_encryption_configuration`
- `aws_s3_bucket_versioning`
- `aws_s3_bucket_policy`

The general-purpose bucket has all four public-access blocks, ACLs disabled by
BucketOwnerEnforced, explicit SSE-S3/AES256 without a KMS key, Enabled versioning,
root provenance tags, `force_destroy=false` and `prevent_destroy=true`. There
are no ACL, lifecycle/expiration, Object Lock, replication, logging or KMS
resources. The pinned provider/lockfile is not upgraded.

Policy has three Deny statements and no Allow: TLS is required for the bucket
and its objects; object creation at `sbom-analytics/poc-v1/snapshots/*` requires
`If-None-Match: *`. The documented `s3:ObjectCreationOperation` condition limits
those header rules to object creation, including multipart completion. The
integrated adapter still uses only simple conditional PutObject. Missing headers
and a different condition are denied. CopyObject to that area is incompatible
with this policy. These statements do not cover `query-results/poc-v1/`;
Athena result writes need their own future IAM authorization.

References: [S3 conditional-write enforcement](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html),
[PutObject](https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html),
[IAM condition operators](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_condition_operators.html).
Principal `*` in an explicit Deny does not grant public or cross-account access.
Bucket policy does not supply missing identity permissions.

## Gates, state and collision preflight

`verify_state.py` checks the selected existing backend bucket/key/region, encryption,
native lock, default workspace, exact execution root and all catalog ECR addresses
before planning. It rejects an empty/wrong state or unexpected managed address.
The temporary JSON state stays private and is excluded from workflow artifacts.

`verify_plan.py --mode sbom-adoption --account-id ... --region ...` requires all
catalog ECR resources to be no-op and the six S3 resources to be create or no-op.
It checks both plan graphs, names, tags, provider identity, region, policies and
security values. Changes, replacements, imports, moves and extra/missing resources
fail. `--mode noop` requires every resource to exist and be no-op after apply.
The old permissive create-or-noop ECR mode is removed from the operational flow.

Computed new bucket IDs must carry the unknown marker AND the exact dependency
on `aws_s3_bucket.sbom.id`. Required security values cannot be unknown. With
AWS 6.64.0, an explicitly empty optional KMS key can still appear computed: only
a create with the inspected literal empty-key configuration and known AES256
input is accepted, not an unknown configured key. The applied key is checked
after creation. Computed MFA status and blocked-encryption-type observations
are not requirements added to this contract. A default owner FULL_CONTROL ACL
response is not configured ACL authority; OwnershipControls must still enforce
BucketOwnerEnforced, and configured grants/ACLs are refused.

`readback.py preflight` checks STS against external account and HeadBucket with
ExpectedBucketOwner. A create plan requires observed absence. Any existing name
is a collision; there is no adoption/import/reconciliation. AccessDenied is an
error, never absence. A managed bucket must remain present in the expected region.
The check runs after planning and immediately before saved-plan apply. Creation
is exclusively Terraform, never CreateBucket as an existence probe. This reduces
collision risk without claiming an atomic global name reservation. The pinned
[provider source](https://github.com/hashicorp/terraform-provider-aws/blob/v6.64.0/internal/service/s3/bucket.go)
also checks an existing owned name before us-east-1 creation.

## Authorized application and read-back

Both Infra workflows use the same new gates and existing concurrency group,
identities, pinned revision, saved binary plan/checksum and protected Environment.
PR planning remains disabled by the existing `infra.plan_enabled=false` setting;
this delivery does not enable it or widen any trust/permissions.

The apply flow still applies the exact verified saved plan, then requires a full
`-detailed-exitcode` zero/no-op plan. Operational ECR read-back checks the complete
catalog, policies, configuration and tags and permits existing images. The optional
`--expect-empty` guard remains available only for explicit greenfield rehearsals;
no images are deleted to satisfy it.

S3 read-back uses the applied Terraform outputs, external account/region and API
checks for owner, region, four public blocks, ownership, encryption, versioning,
policy, tags and absent lifecycle/Object Lock. GetBucketLocation null is the
documented us-east-1 representation. Each check records expected, observed and
result in JSON, including failed/inconclusive checks, before nonzero exit.
See [GetBucketLocation](https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetBucketLocation.html).

`terraform -chdir=infra/ecr output -json ingestion_config` exposes the exact
protocol-v1 configuration consumed by #115, with prefix `sbom-analytics/poc-v1`
(the adapter appends `/snapshots/<snapshot_id>/`). Bucket name/ARN/region/owner,
tags and both reserved prefixes are also root outputs, with no credentials.
Outputs do not authorize upload, catalog creation or Athena queries.

## External prerequisites observed before first use

Read-only LAB inspection on 2026-10-09 found the bucket absent, the existing
backend/key/default workspace in use, and the Infra apply inline policy scoped
to the backend bucket only. No S3 permissions for the new bucket were granted.
The Environment still permits `main` only while dispatch requires `develop`;
it requires its configured reviewer and disallows administrator bypass. These
are application blockers, not authorization to bypass them. Branch protection
requires one approving code-owner review and repository checks.

The separate least-privilege IAM proposal is in [permissions.md](permissions.md).
It is not applied, included in `infra/iam`, or attached to Build/promotion roles.
An authorized Infra owner must reconcile those prerequisites before dispatch.
No privileged local apply is a substitute. Never apply the local diagnostic plan
under another identity; the protected flow creates its own exact saved plan at
the reviewed integrated revision.

## Tests and future object smoke

```sh
terraform fmt -check -recursive infra
terraform -chdir=infra/ecr init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/ecr validate
terraform -chdir=infra/ecr test -no-color
python3 -B -m unittest discover -s infra/tests -v
make check
```

The native provider mocks test the full root and select the child from root test
files. No child backend/init or second operational state is introduced. Mocks
and a safe real plan are not applied-AWS evidence.

After authorized apply and configuration read-back, an explicitly allowed data
session may smoke-test a harmless public body under a unique test key within the
snapshot area: first conditional PUT, version-specific GET and recalculated
SHA-256, conditional repeat returning 412, unconditional PUT denied by policy,
then original version/current bytes unchanged. Use a separate test key, never a
valid snapshot or table LOCATION. Record VersionIds, bytes/hashes/errors and
cleanup pending. Do not send HTTP credentials to test TLS or delete automatically.
If data permission is unavailable, report configuration separately from
`OBJECT_OPERATIONS_NOT_PROVEN`.

`prevent_destroy` protects Terraform operations; versioning records versions.
Neither proves WORM, administrator resistance, retention or future availability.
No expiration period is decided. This delivery creates no Athena/Glue resources,
automatic ingestion, promotion changes, monitoring platform or productive HGC-04.

Corporate adoption retains dynamically generated backend/provider and its
authorized provider mirror/ARC/UP2 configuration. Do not copy LAB identifiers or
replace FROZEN files; only the child and authorized root linkage are candidates
for a separately reviewed port. No corporate account is applied here.
