# Manual LAB SBOM Analytics POC

The manual executor calls the merged normalizer/snapshot/S3 APIs. It does not add
implicit upload to the offline planner. `sbom-analytics-lab-poc.yml` uses only
workflow_dispatch, this repository, develop and Environment DEV. Its two jobs
use the central role resolved by versioned configuration. Integration requires
review and owner merge; this document does not report a hosted proof in advance.

## Frozen input and execution

The public historical corpus belongs to run 37806495087 / attempt 1, commit
`4c1783e8c2a36e0f79f453b2f080a23a0eeea0d3`, not the new ingestion run. The ZIP
fixture contains data only: original plan.json and every original frozen batch
file. It preserves 19 payload objects / 630308 bytes, including the six raw SPDXs
and existing Parquet bytes. No normalizer retry or Parquet rewrite is involved.

- Batch: `2da32bfa4c095802a7ae7c84cdbf421cedd5529412b2b6b55f0e51119302bd5a`.
- Snapshot: `6ae0d5a463a20961e4431cb86d7d969ff2157bf25428a22dd08aa119632548b6`.
- Package SHA-256: `a713e5e34d1419a9971719fe6ced95c87c1514631984b4512a784411a621b785`.
- Plan SHA-256: `4e901c7ab8d6ce001576387caa5797806161ad154871994d9b58ab28bec1d03c`.
- Package bytes: 643439. ZIP_STORED; member bytes are unchanged. This is a new
  transport package, not an original GitHub artifact ZIP.

`lab-frozen-plan.json` supplies the package/plan hash from reviewed source code.
Before obtaining AWS credentials, prepare checks hashes, bounds, unique safe
regular-file members and the integrated load_plan contract/identity/inventory.
Limits for this small transport are 2 MiB package/aggregate expansion, 1 MiB per
file and 64 files. The original protocol limits also apply. No code is executed
from the package. A changed package fails before cloud access.

Python 3.12 is the hosted target; PyArrow remains 21.0.0. The isolated SDK pins in
requirements-sbom-poc.txt include boto3/botocore 1.40.39, supporting Python 3.12.
SDK/session creation occurs only in explicitly requested publish/recover commands
and requires supplied temporary credentials; identity checks reject an admin user,
wrong account, role, session or RoleId. Functions also accept external low-level
clients for approved corporate integration; importing them does not discover
credentials or initialize a cloud SDK.

After approved integration, the authorized operator runs:

```sh
gh workflow run sbom-analytics-lab-poc.yml \
  --repo alric-corp/alric-containers-image-base --ref develop
```

This is authorization to execute this S3-only POC through the existing workflow
review/Environment controls; it is not permission to change those controls.
The workflow does not call Build & publish, Infra Apply, promotion or recovery of
images. Existing automatic publishers/schedules remain active. **Merging this PR
changes scripts/policies and therefore matches the normal develop publisher.**
The owner must authorize that operational integration/window before merge, without
bypassing existing gates or inferring acceptance of the shared-role risk.

## S3 proof and its boundaries

The publisher uses a session policy allowing only STS identity, exact bucket
configuration reads, prefix-constrained list and Put/Get/GetObjectVersion under
sbom-analytics/poc-v1/snapshots/. The reader session has no PutObject permission.
Neither session allows IAM, ECR, backend/state, bucket administration, deletion
or query-results access. No permanent IAM policy is added or changed.

Before uploading, it checks STS, region (S3 null means us-east-1), public access,
ownership, AES256 and versioning, and records the bucket policy. A public probe
is written under snapshots/_smoke_tests/r<run>-a<attempt>/, outside the valid
snapshot. Conditional write and version read-back must pass, conditional retry
must return 412 and an unconditional write must be denied. The session policy
allows both forms of PutObject on that prefix: it does not enforce the condition.
The error is classified as resource-policy explicit deny only if the service
message identifies that cause; otherwise the JSON marks the denial source
uncertified. No credentials are sent without TLS and no delete test is run.

publish_reported performs the integrated conditional upload, byte/metadata/version
read-back and exact inventory/final-marker verification. It then retries the
same frozen plan and requires SNAPSHOT_ALREADY_PRESENT_IDENTICAL, no additional
PUT calls, unchanged marker bytes/VersionId and current file-version verification.
Manifest JSON records all keys, sizes, hashes and versions. Expected total: 20
snapshot objects; probes are excluded. Failures do not delete or replace anything.

A separate hosted reader job sparse-checks out code, schemas, SQL and policy;
no tests/fixtures, package, original batch, plan or publication artifact is present.
It receives only external target/identity/configuration, assumes a read-only
session and calls recover_snapshot into a new directory. It validates the original
SPDX subjects/hashes, Parquet schema/records and local query semantics. The result
includes 6 observations / 300 records, runtime 22 and dev 123 non-subject records
per platform, and amd64 diagnostic alignment 20 SAME_REPORTED_NAME_VERSION,
2 ONLY_RUNTIME and 103 ONLY_DEV. These values are expectations for this exact
historical corpus, not installed-package counts or cross-document universal IDs.

Artifacts sbom-poc-<run>-<attempt>-publish/recover contain JSON and dependency
versions, including failures. Their 30-day GitHub retention uses the existing
product evidence convention and its versioned health policy. This is not an S3
retention decision or durable custody guarantee. Read-back integrity confers no
publication authority; authenticity remains NOT_REVALIDATED. No WORM, admin
protection, future availability, HGC-04 activation or corporate validation is proven.

## Athena complement — proposed, not applied

The versioned central inline policy now includes the **proposed** Athena complement;
the observed live 11-statement policy had no Athena/Glue/query-results writes.
Versioning this contract does not apply it. Keep the S3 proof independently when
this complement is pending. See [the manual Athena caller](sbom-analytics-athena-lab-poc.md)
and [external operator runbook](sbom-analytics-athena-iam-runbook.md).
`docs/examples/sbom-lab/athena-policy-delta.json` proposes three additional
statements in the **same** external inline policy: the exact POC workgroup, the
catalog/database/five exact table or view resources, and query-results/poc-v1/
objects. Existing statements are preserved; proposed total minified size is 6277
characters. No IAM administration, additional role or permanent second policy is
proposed. The operator must read current IAM, reconcile drift and validate the
full merged JSON with Access Analyzer, then obtain specific authorization before
external IAM update/read-back. These files do not apply it automatically.

The workgroup/database JSON proposals reserve AwsDataCatalog,
poc_distroless_sbom and the exact result prefix in the same analytics bucket.
They propose SSE_S3, expected owner, engine 3, enforced result configuration and
100 MiB per-query cutoff, with CloudWatch metrics disabled. A successful read is
not proof of write permission; AccessDenied is not resource absence. Only confirmed
missing resources plus specific provision authorization justify creation. If
Terraform owns them in LAB, a separate authorized increment must use infra/ecr's
existing root/state; no alternative backend/root is introduced here.

After S3 completes, catalog_plan must do another remote read-back. Keep execute=false
as a proposal. Review its exact SQL/hash, external authorization, snapshot,
workgroup, output and exclusive names before any statement execution. Check all
five names for collisions; do not rely on IF NOT EXISTS or CREATE OR REPLACE to
replace an existing resource. No active table LOCATION is changed. Raw, markers,
probes and results remain outside the two Parquet LOCATIONs.

Execution budget: 18 statements total (5 DDL, 5 original queries, 2 counts,
2 DESCRIBEs, inventory count, null/empty-array count, nested type check, full
nested-value read-back). One at a time; 120-second operational timeout and cancellation;
reuse a persisted ClientRequestToken for the identical SQL/context/parameters.
Disable result reuse and verify effective output/engine/reuse status and results
against the recovered local dataset. Supply ExecutionParameters with correctly
encoded literals, never textual substitution of user components into SQL. Preserve
IDs, SQL SHA-256, parameters, states, scan bytes, duration and diagnostics. The scan
cutoff is not a global financial ceiling. The corpus has no empty-array rows:
mark that data boundary NOT_EXERCISED instead of modifying historical data.

SQL result -> observation/framework/platform -> image subject digest -> SPDX hash
-> snapshot root + raw_spdx_path -> original bytes is the demonstration chain.
No CVE, deployed application, stable or security approval is inferred.

## Minimal corporate integration for Monday

| Reusable material | Caller responsibility / limit |
| --- | --- |
| analytics/spdx.py, normalize.py, parquet.py | Explicit source paths and external expected index/platform identities; preserve raw bytes |
| analytics/snapshot.py, s3_ingestion.py, ingest.py | Completed local batch, authorized destination and injected low-level client; frozen retry |
| analytics/poc.py functions | Expected identity and diagnostics supplied externally; CLI's temporary env-credential path is LAB-specific |
| analytics/catalog.py and sql/sbom-analytics/ | Explicit verified snapshot and separately authorized POC namespace/SQL |
| schemas/sbom-analytics/v1.json | Versioned observation/package types, including nullable arrays/structs |
| test_poc.py corporate layout test | Synthetic structure only; real validated-index schema and full compatibility remain unproven |
| requirements-sbom-poc.txt | Python 3.12 / Arrow 21 / SDK pins through the approved corporate dependency channel |

The synthetic test uses sbom/sbom-index.spdx.json, sbom-x86_64.spdx.json,
sbom-aarch64.spdx.json plus structural apko.lock.json/build-inputs.json/
validated-index.json placeholders explicitly labeled schema-not-claimed. Only
explicitly selected SPDX paths and external expected subjects are consumed. It
requires no LAB release manifest, LAB account, uppercase DEV or HGC-04. The
normalizer's existing release-model imports remain a documented portability
coupling; the test does not prove the corporate source schemas or hosted runner.
No corporate originals or identifiers are copied into this public fixture.

Propose one separate manual analytics caller after the corporate artifact is
available. Its approved configuration supplies source paths, repository/run/attempt/
SHA/ref/event, expected OCI subjects and optional validation/publication references,
then S3 destination/client and later catalog/workgroup/result/cost controls. It does
not alter build/publication/infra callers. Corporate bucket/prefix/account, resources,
permissions and dependencies remain corporate decisions, not LAB defaults.

Do not replace .iupipes.yml, pipeline-config.json precedence, FROZEN files,
base-sync classification, ARC/EKS, mirrors, the role provisioner, UP2,
_core-infra-terraform.yml, setup-backend, dynamic backend/provider or shared state.
Do not integrate verify_plan.py. Infrastructure/governance collection findings
remain separate follow-up; this POC neither resolves nor erases them.
