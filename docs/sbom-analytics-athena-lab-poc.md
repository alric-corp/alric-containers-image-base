# Manual Athena complement for the LAB snapshot

This increment prepares a caller and the external IAM contract. It does not
apply IAM, provision resources, dispatch a query or report an Athena hosted proof.
The separate S3 proof remains run **38031426478 / attempt 1**, code
`bae80db06ace33fef29ef3b51ccdb70affbaabaa`. Its snapshot has 20 objects; no new
smoke, upload, normalization or Parquet serialization is required.

## External authorization and provisioning

The owner's instruction describes a proposed authorization. Before cloud writes,
obtain explicit approval identifying the reviewed commit, full inline-policy hash,
two resource definitions and the exact SQL plan/round hash. Approval of this PR
does not grant those operations or accept shared DEV/Infra privilege risks.

Read-only LAB preflight on 2026-10-10 observed the expected administrative user,
role `AROA2LTHQWCU2N3H2OE3L`, unchanged trust, MaxSessionDuration 10800, one inline
policy, no attached managed policies and byte-independent semantic equivalence
with the preceding 11-statement contract. The proposed complete policy has 14
statements / **6277 compact ASCII characters**. Access Analyzer returned no
identity-policy findings; the unchanged trust returned
`CONFIRM_AUDIENCE_CLAIM_TYPE` (suggestion) and
`SPECIFIC_GITHUB_REPO_AND_BRANCH_RECOMMENDED` (warning). The trust uses exact
immutable repository/owner/environment subjects, not wildcard subjects; branch
authorization still depends on workflow/Environment controls. These findings need
owner evaluation, not automatic dismissal or a trust change in this increment.

`ListDataCatalogs` confirmed `AwsDataCatalog` (GLUE, CREATE_COMPLETE).
`GetDataCatalog` returned not-found for that built-in name; the list observation
is preserved separately. No catalog creation is proposed. The POC workgroup was
absent from the complete workgroup list, and Glue returned EntityNotFound for the
POC database. The selected existing infra/ecr default state contained no
Athena/Glue resources, and no such resources were declared in infra. This is
limited ownership evidence for that root/state, not proof about every external
provisioner. The operator must repeat the checks before creation.

Catalog encryption was DISABLED; Lake Formation listed no registered locations
and default database/table grants used IAM_ALLOWED_PRINCIPALS. These reads do not
prove all effective query permissions. An incompatible live control is a blocker,
not permission to disable Lake Formation or encryption.

Follow [the external complement runbook](sbom-analytics-athena-iam-runbook.md).
Only the administrator provisions workgroup/database and updates the existing
inline policy, after approved integration and scoped authorization. The role
contract grants no workgroup/database administration, IAM administration, global
Athena/Glue access, deletion or additional permanent policy. Terraform roots,
states, providers, existing resources and identities remain unchanged.

## Reader and execution workflow

`sbom-analytics-athena-lab-poc.yml` is manual only, develop only, this repository
only, Environment DEV. It uses the operational configuration resolver and existing
pinned Actions. Python 3.12 and requirements-sbom-poc.txt are unchanged. The job
has 45 minutes; OIDC credentials last 3600 seconds (within the role's read-back
maximum). No administrative or static credential fallback is supported.

The SDK is constructed only at the explicit CLI boundary with supplied temporary
environment credentials. All functions accept injected clients. The STS check
requires the expected account, central role, RoleId and exact job session before
reading data. Importing/planning does not discover credentials.

The workflow sparse-checks out reader/configuration/SQL/schema only: no fixtures,
transport package, frozen plan, producer Parquet or publisher artifact. It calls
the existing read_snapshot/recover_snapshot/catalog_plan APIs, validates current
and recorded object versions and the historical marker hash/VersionId, then
inspects recovered records/Parquet/raw SPDXs. All data comes from S3.

`mode=plan` uses a read-only session, prepares SQL and returns PROPOSED/execute=false;
it makes no StartQueryExecution, resource create or S3 PUT. `catalog_plan` always
retains execute=false. In `mode=execute`, the operator supplies the exact reviewed
`authorized_plan_sha256` and a recorded `authorization_reference` **after external
owner authorization**. These inputs bind the request; they are not a signature
or automatic proof that the GitHub dispatcher is the owner. Existing GitHub
review/Environment controls and operator authorization remain required.

The compact session policies are 1382 characters for plan / 1525 for execute.
The builder checks the independent STS 2048-character limit. Read access is
restricted to this snapshot. Only query-results/poc-v1/ permits PutObject. Glue's
session pattern is limited to `poc_snapshot_<full snapshot ID>_*`; the role's
five exact object ARNs further restrict the intersection. There is no snapshot
write, ECR, IAM, state, bucket administration or data deletion access.

Do not dispatch execute until resources and the IAM complement are read back.
Do not use a workflow rerun/new round to bypass a failed/unknown execution. An
existing object requires this round's verified journal and matching definition;
otherwise it is a conflict, never automatic adoption or replacement.

## Frozen SQL and comparisons

The round freezes canonical plan bytes and exact requests, including context,
parameters, result destination, limits, statement hashes, expected rows and
tokens. Acquisition times/signatures are not regenerated on retry. A plan hash
change requires new explicit authorization; it does not change the S3 snapshot ID.

Exactly 18 distinct executions are budgeted: two physical-table DDLs, three
ordinary-view DDLs, five existing demonstration SELECTs, six auxiliary SELECTs
and two DESCRIBEs. No SQL CREATE DATABASE or prepared-statement calls are added.
The auxiliary SELECTs check observations, packages, inventory counts, nullable
arrays, nested types and every package's nested values/licenses. The stronger
full nested-value check replaces the earlier five-row struct sample.

Two syntactic changes to the proposal are explicit and tested: remove
IF NOT EXISTS and OR REPLACE for first creation, and wrap only queries 03/04 to
encode their array columns with `json_format(CAST(... AS JSON))`. Their joins,
parameters, row selection and diagnostic SPDXID semantics stay unchanged. Nested
struct values use an explicit named-map JSON projection, not textual guesses
about Athena's native array/row display. Original SQL templates and data bytes
are preserved. The earlier 18-statement proposal hash is not reused.

ExecutionParameters contain properly quoted string or integer literals; values
are never substituted into SQL text. Every request has an explicit token derived
from the round, statement ID and all Start request fields. The journal is written
before submission. A lost response leaves a reserved request with its original
token; retry retrieves that same execution instead of creating a new one.

Requests run sequentially. The 120-second deadline includes submission/waiting
and is retained on restart. Timeout cancels only that round's identified query,
records the cancellation observation and stops. Failed/unknown outcomes do not
advance or receive a new token. A verified restart reads prior executions/results
again without new Start calls. A genuine failure requires review, not unlimited
retries. The 100 MiB enforced per-query cutoff is not a global cost ceiling.

Every succeeded query is reconciled against SQL/parameters/context/workgroup,
effective engine/output/encryption/owner, scan bytes and actual reuse status.
GetQueryResults is paginated fully within explicit limits: 16 pages, 4096 data
rows, 128 columns and 8 MiB responses. ColumnInfo/raw pages are preserved. SQL
NULL and empty strings stay distinct; integers use declared types; only explicitly
JSON-projected columns use strict JSON parsing. Comparisons are multisets and
retain duplicate counts. DESCRIBE rows are recorded literally, without guessing
Hive output fields; Glue read-back verifies all typed physical columns/locations.

The five catalog names are collision-checked using GetTable. Only
EntityNotFoundException denotes absence. Resumption requires this round's exact
successful DDL and compares physical columns/locations and ordinary Presto view
definitions. The view comparison permits formatting, identifier quoting, optional
AS and parentheses in the simple v1 SELECT/JOIN/equality/AND grammar; it preserves
literals/columns/tables/predicates. It is not a general SQL equivalence engine.
Unknown representations fail closed, with no replace or delete operation.

After SQL, a fresh complete snapshot read-back must match the initial fingerprint,
including marker/object bytes and current versions. Artifacts retain identity,
dependency versions, catalog/SQL plan, journal, actual pages/results, errors and
pre/post read-back, including failure. They are outside Parquet LOCATIONs and
the snapshot. No cleanup runs automatically.
The new sbom-athena- artifact uses the existing 30-day GitHub product-evidence
convention, registered in policies/operations/health.json for its mandatory lint
and code-owner review. Existing retentions, health thresholds and schedules do
not change; this is not an S3 lifecycle or corporate retention decision.

## Restart and evidence procedure

The API/CLI can resume from its same reports directory after restoring the exact
sql-plan.json and execution-journal.json. Validate an artifact's originating
repository/workflow/event/ref/commit/run/attempt and ZIP/hash before restoring it;
only data is loaded. Preserve the prior artifact and external authorization.
Recover into a new output directory. Never delete/recreate catalog resources,
remove a journal, generate a new token/round or increase 18 to hide a partial run.
The initial manual workflow does **not** automatically fetch a previous attempt's
journal. If an initial hosted attempt fails, preserve its artifacts and stop for
review; an authorized caller must supply the validated journal for resumption.
Blind workflow reruns encounter catalog conflicts and cannot approve them.

Retrieve artifacts into the persistent audit-evidence directory, verify ZIP
digests with the GitHub API, and reconcile run/attempt/commit/job/STS evidence.
The local tests use real public historical bytes but fake clients/results. They
prove API/codec/guard behavior, not Athena syntax or IAM enforcement in production.

Expected historical results are 6 observations / 300 SPDX records; runtime 22
and dev 123 non-subject records per platform; amd64 diagnostic comparison 20
SAME_REPORTED_NAME_VERSION, 2 ONLY_RUNTIME, 103 ONLY_DEV. They do not prove installed
packages, dependency direction, vulnerabilities, consumers, stable or security
approval. Empty arrays are absent: EMPTY_ARRAY_FROM_PARQUET=NOT_EXERCISED.
SPDX authenticity remains NOT_REVALIDATED; publication_authority=false.

## Integration impact and exclusions

This PR changes scripts/policies and therefore matches the existing develop
Build & publish trigger on merge. The owner must approve that integration/window
and evaluate shared DEV/Infra privileges before merging; the merge may publish
normal DEV images through unchanged gates. This analytics workflow itself does
not call image publication, promotion, recovery, Infra Apply or the S3 publisher.

No corporate writes or infrastructure rewrite, IAM bootstrap/cutover, HGC-04
activation, automatic ingestion, Glue crawler/job, Spark, Iceberg, Lake Formation
changes, observability, lifecycle or retention configuration is included. The
approved corporate caller/configuration/dependency channel remains separate.

References: [StartQueryExecution](https://docs.aws.amazon.com/athena/latest/APIReference/API_StartQueryExecution.html),
[GetQueryResults](https://docs.aws.amazon.com/athena/latest/APIReference/API_GetQueryResults.html),
[STS session policies](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRoleWithWebIdentity.html),
[Glue resource hierarchy](https://docs.aws.amazon.com/athena/latest/ug/fine-grained-access-to-glue-resources.html),
[workgroup configuration](https://docs.aws.amazon.com/athena/latest/APIReference/API_WorkGroupConfiguration.html).
