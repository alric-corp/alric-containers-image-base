# Separate Infra IAM proposal (not applied)

The existing LAB apply policy permits S3 administration only on the state bucket.
It grants nothing on the new analytics bucket. Keep that state/lock policy and
all OIDC subjects unchanged. No Build/promotion role changes are proposed.

Authorize only the exact ARN obtained from the reviewed bucket configuration:
`arn:aws:s3:::<AUTHORIZED_ANALYTICS_BUCKET>`, in its configured region. No `s3:*`,
AdministratorAccess, unrelated buckets, account-wide enumeration or bucket deletion.

For Infra plan and apply, the pinned provider and independent read-back need:

```text
s3:ListBucket
s3:GetBucketLocation
s3:GetBucketAcl
s3:GetBucketCORS
s3:GetBucketWebsite
s3:GetBucketVersioning
s3:GetBucketLogging
s3:GetBucketTagging
s3:ListTagsForResource
s3:GetBucketRequestPayment
s3:GetAccelerateConfiguration
s3:GetReplicationConfiguration
s3:GetLifecycleConfiguration
s3:GetEncryptionConfiguration
s3:GetBucketObjectLockConfiguration
s3:GetBucketPublicAccessBlock
s3:GetBucketOwnershipControls
s3:GetBucketPolicy
```

Some reads cover defaults inspected by `aws_s3_bucket`, not extra resources.
Granting a read does not enable that feature. Verify the role's complete effective
permissions/boundary/SCP separately before first use; policy inspection alone is
not proof that a call is allowed. Denied reads fail rather than presume absence.

For Infra apply only, initial creation additionally needs these exact-bucket actions:

```text
s3:CreateBucket
s3:PutBucketPublicAccessBlock
s3:PutBucketOwnershipControls
s3:PutEncryptionConfiguration
s3:PutBucketVersioning
s3:PutBucketPolicy
s3:TagResource
s3:PutBucketTagging
```

AWS provider 6.64.0 tags on creation with `s3:TagResource` and has a legacy
PutBucketTagging fallback. Tag reading uses the service tagging APIs; keep their
scope on this bucket. Updates/deletes remain rejected by the adoption plan gate;
no DeleteBucket, DeleteBucketPolicy, DeleteObject or DeleteObjectVersion is proposed.
Any later tag removal or infrastructure change requires its own reviewed scope.
Source: [the pinned provider](https://github.com/hashicorp/terraform-provider-aws/blob/v6.64.0/internal/service/s3/bucket.go).

Separate optional smoke/ingestion permissions, not supplied by this delivery:
`s3:PutObject`, `s3:GetObject`, `s3:GetObjectVersion` on an authorized isolated
snapshot/test prefix; `s3:ListBucket` with the relevant prefix restriction. Use
conditional object creation and retain test objects for a cleanup decision.
No data permission or read-back success grants Athena authority. Athena result
permissions must be scoped separately to `query-results/poc-v1/`; never copy
the conditional snapshot requirement onto the results area.

No role or policy is created/changed by this document. The IAM increment must be
approved and applied through the existing IAM ownership process before Infra
dispatch can manage this bucket. The current Environment branch/reviewer gate
also remains an independent prerequisite.
