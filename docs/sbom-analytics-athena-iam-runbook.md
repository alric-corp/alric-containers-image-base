# External LAB Athena complement — operator procedure

Status: proposed procedure, not cloud authorization. Use only after owner review,
approved integration and explicit authorization for this commit and these changes.
Do not rerun the central-role bootstrap. Do not use Terraform or the analytical
workflow to modify IAM. Do not run SQL with the administrative session.

## Scope and checkpoints

Account 712107929769 / us-east-1. Administrative principal must be exactly
`arn:aws:iam::712107929769:user/Tomas-Instructor`. Existing role:
`itau-github-repo-factory-distroless-v1`, RoleId `AROA2LTHQWCU2N3H2OE3L`,
MaxSessionDuration 10800, one inline policy named `factory-distroless-v1`, no
attached managed policies. Trust is unchanged. Stop on any mismatch or access
error; no credential, role, trust, duration, Environment or legacy identity changes.

Use a clean checkout of the specifically approved integrated commit, a private
evidence directory outside Git, and an exclusive operator window for this inline
policy update. IAM PutRolePolicy provides no conditional compare-and-swap; the
live comparison and subsequent read-back are necessary but not an atomic drift
lock. Do not overwrite unknown drift or roll back/delete automatically.

```sh
aws sts get-caller-identity --region us-east-1
aws iam get-role --role-name itau-github-repo-factory-distroless-v1
aws iam get-role-policy --role-name itau-github-repo-factory-distroless-v1 \
  --policy-name factory-distroless-v1
aws iam list-role-policies --role-name itau-github-repo-factory-distroless-v1
aws iam list-attached-role-policies --role-name itau-github-repo-factory-distroless-v1
```

Preserve these JSONs and semantic hashes without credentials. The live inline
policy must equal the first eleven statements of the reviewed 14-statement file,
or already equal the complete approved document. Compare the full statement
objects, not just Sids. Trust must equal the versioned trust JSON. Any other
configuration is a conflict requiring review. Reconcile both lists to exactly
one expected inline policy / zero managed policies.

Run stateless Access Analyzer validation on the complete JSON, not just the delta:

```sh
aws accessanalyzer validate-policy --region us-east-1 --policy-type IDENTITY_POLICY \
  --policy-document file://policies/aws/factory-distroless-v1.inline-policy.json
aws accessanalyzer validate-policy --region us-east-1 --policy-type RESOURCE_POLICY \
  --validate-policy-resource-type AWS::IAM::AssumeRolePolicyDocument \
  --policy-document file://policies/aws/factory-distroless-v1.trust.json
```

Paginate when nextToken exists. Preserve findings and explicit review. Known trust
findings concern audience claim type and branch restrictions; unchanged warnings
are not automatically accepted. Unknown/errors/impediments stop the update.
Compute compact JSON length and SHA-256; expected proposed length is 6277 ASCII
characters, below 10240. The original eleven statements must remain intact and
the last three must equal docs/examples/sbom-lab/athena-policy-delta.json. This
delta is not a complete policy and must never be passed alone to PutRolePolicy.

Only after those checkpoints and scoped authorization, update the same policy:

```sh
aws iam put-role-policy --role-name itau-github-repo-factory-distroless-v1 \
  --policy-name factory-distroless-v1 \
  --policy-document file://policies/aws/factory-distroless-v1.inline-policy.json
```

Repeat GetRole/GetRolePolicy/both policy lists. Compare full semantic documents,
RoleId/duration/trust and inventory, and record before/after hashes and API result.
An uncertain/partial update is preserved and reported; never delete/recreate the
role or attach a second policy to work around it.

## Two analytical resources, only if absent and unowned

Before creation, repeat read-only catalog/workgroup/database checks and current
Terraform ownership inspection for the existing root/state. Do not save raw
tfstate publicly, initialize a second root/state, import or mutate state.

```sh
aws athena list-data-catalogs --region us-east-1
aws athena list-work-groups --region us-east-1
aws athena get-work-group --region us-east-1 --work-group poc_distroless_sbom
aws glue get-database --region us-east-1 --catalog-id 712107929769 \
  --name poc_distroless_sbom
aws glue get-data-catalog-encryption-settings --region us-east-1 \
  --catalog-id 712107929769
aws lakeformation get-data-lake-settings --region us-east-1 --catalog-id 712107929769
aws lakeformation list-resources --region us-east-1
```

Inspect all pages. AwsDataCatalog must already be listed as GLUE; do not create a
catalog. A specific GetWorkGroup not-found response plus complete list absence
confirms missing workgroup. Generic InvalidRequestException, AccessDenied, timeout
or network failure is inconclusive. Glue EntityNotFoundException confirms missing
database; access errors do not. Existing resources require ownership/configuration
review; this procedure does not adopt, replace or alter them. Terraform ownership
requires an approved change in its existing flow, not external provisioning.
Lake Formation/catalog encryption incompatibility is a precise blocker, not a
reason to disable account governance or grant global permissions.

When both missing-resource/ownership checks and **specific creation authorization**
are satisfied, the administrator executes only:

```sh
aws athena create-work-group --region us-east-1 \
  --cli-input-json file://docs/examples/sbom-lab/athena-workgroup-proposal.json
aws glue create-database --region us-east-1 \
  --cli-input-json file://docs/examples/sbom-lab/glue-database-proposal.json
```

Read both back. Require SQL engine 3, workgroup enabled, enforced output
`s3://alric-distroless-sbom-712107929769-us-east-1/query-results/poc-v1/`, SSE_S3,
expected results bucket owner 712107929769, 104857600-byte cutoff, metrics=false
and RequesterPays=false. Record external LAB ownership, timestamp, administrator,
authorization and responses. If only one creation succeeds, preserve the partial
state and stop; no deletes, recreate, import or automatic compensating changes.

No bucket, KMS key, managed policy, second inline policy, role, catalog, crawler,
job, connector, capacity reservation or Lake Formation change is included.

## Handoff to separately authorized OIDC execution

The central OIDC session alone runs the analytics. First use the manual workflow
in plan mode after approved integration. Validate its source SHA, STS identity,
fresh S3 marker/object versions, exact 18-statement plan, round/hash, exclusive
five names and two Parquet locations. Approve execution explicitly for those
bytes, the workgroup/database/output/limits and snapshot, then dispatch execute
with that plan hash and authorization reference. Preserve execute=false in the
catalog proposal. Query reuse stays disabled. No admin fallback is permitted.

Do not use a blind rerun after failure or outcome uncertainty. Preserve the
query journal, results, snapshot and all artifacts in audit-evidence; reconcile
the original tokens and catalog definitions before resumption. New executions
beyond eighteen require another explicit authorization. No cleanup or retention
change is automatic. The owner must designate responsibility for later review
of retained workgroup/database/tables/views and query-results objects.
