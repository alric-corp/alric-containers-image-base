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

The integrated caller restores an explicitly approved prior run/attempt/artifact,
not the latest artifact. Execute requires `resume_source`; plan mode forbids it.
The `athena_restore` helper performs only GitHub API reads, before OIDC. The
athena job alone gains `actions: read`; GH_TOKEN is scoped to the restore step.
It verifies the originating repository ID, workflow, workflow_dispatch/develop,
source commit and attempt, artifact ID/name/size/digest, and producer upload step.
A failed originating run is valid evidence, not a reason to select another run.

The original incident's approved source input below is historical. Run
38088837347 subsequently advanced the round to six entries; use the explicitly
identified six-entry source in the next subsection for that resumption, unless
a later run advanced it again. Never select a source by latest artifact name.

```json
{
  "run_id": 38080824102,
  "attempt": 1,
  "artifact_id": 11679714087,
  "source_sha": "2702c4010e8d7bff561388bd27e9a6109f878d6d",
  "zip_sha256": "28d12a47b8488dc4ee83511c91f989272900180152271c69509b655093676edf",
  "zip_bytes": 50980,
  "journal_sha256": "714c2e35c113c2f4185892f2431007d0e3ed945e1e5220627528fcc21e71f9ff",
  "journal_bytes": 2414,
  "sql_plan_sha256": "ce1c1ab7079db6bbcbdf91c4d6f1ddfbd6ef9806d9cdbe848e34a8ba8259123e",
  "sql_plan_bytes": 257893
}
```

ZIP parsing is bounded to 16 MiB compressed, 32 MiB actual expanded bytes, 64
members and 512-byte paths, with per-file limits of 16 MiB for journals/source
ZIPs and 4 MiB otherwise. These are margins over the incident's 50,980-byte ZIP,
12 members and 399,143 expanded bytes. Both central/local headers, data descriptors,
CRC, actual decompression length and contiguous listed data are checked. Only
explicit report names are allowed; links, special files, duplicates, traversal,
ZIP64, extras/comments, unsupported methods and unlisted/overlapping bytes fail.
Only journal, SQL plan and authentication metadata are selected as data. Nothing
from the artifact is executed. Preserve the ZIP and original journal/SQL bytes
under the private `athena-resume-source` directory; working copies under
`athena-reports` start byte-identical. The separate resume receipt binds the old
producer SHA to the corrected executor SHA without rewriting history. An invalid
or unavailable source stops the job; it never falls back to an empty journal.
There is no automatic local-evidence fallback. If GitHub evidence expires, an
explicit reviewed recovery route with these same hashes/provenance is required.

Before any uncertain start, validate the entire journal against the frozen plan,
authorization, sequential prefix, request/token and unique query IDs. The CLI
rechecks the restored working bytes before constructing AWS clients. The source
journal has one SUBMITTED entry, table-0, query
`f65fa3ea-3d73-4d3d-a2b6-13637500920d`, token
`80d33f677de36228e9c2d8ed6bf34207f6bd400c2d779fdfcdd42d8e245ca3d8`.
Reconcile it by GET and table read-back, with no Start and no manual VERIFIED
edit. All 18 statements remain in the plan: one reserved/submitted, then 17 new
(4 DDL, 11 SELECT, 2 DESCRIBE). A second pass over a complete journal performs no
Start calls. Unknown submission outcomes may only retransmit the SAME request
and token; they do not receive another budget slot. API calls and new starts are
reported separately from the round's distinct execution IDs and reserved count.
`api_calls` describes execute_plan; `resource_readback_api_calls` separates the
before/after catalog reconciliation. Journal `recorded_get_attempts` counts
observations recorded by this corrected executor, not an invented count for the
old run whose journal did not retain that field. The one-entry/17-new accounting
above describes the first corrected resume, not the current six-entry history.

### Six-entry resume after the final-terminator correction

Run 38088837347 / attempt 1, executor
`20ee0051018eefe94001b9639fd819c4b898ded7`, reconciled the original table and
verified the other four DDLs. It then submitted `01_find_images` and stopped
because Athena omitted its final `;` in the returned Query. The preserved
journal records five VERIFIED DDLs and one SUBMITTED SELECT with a QUEUED
observation. That observation does not establish the SELECT's current state.

Approved source for the next resume, conditional on no later run advancing it:

```json
{
  "run_id": 38088837347,
  "attempt": 1,
  "artifact_id": 11683770809,
  "source_sha": "20ee0051018eefe94001b9639fd819c4b898ded7",
  "zip_sha256": "3929469270e781d57f0489b555cfe21c1a4fd85ab5e155f4a9ad0b07c0132232",
  "zip_bytes": 133908,
  "journal_sha256": "e4a4410fc7f8149f8e7c3b859f028def03b5cfa3bd3133e7dcc2417bc26d5519",
  "journal_bytes": 35270,
  "sql_plan_sha256": "ce1c1ab7079db6bbcbdf91c4d6f1ddfbd6ef9806d9cdbe848e34a8ba8259123e",
  "sql_plan_bytes": 257893
}
```

Select exactly `athena-reports/execution-journal.json` and
`athena-reports/sql-plan.json`. The same ZIP also contains
`athena-resume-source/execution-journal.json` (2414 bytes, one entry) and a nested
historical ZIP. Those are preserved history, not current resume inputs. The
unchanged restorer selects by full member path and approved hash, never basename,
ZIP order or the word "original". Keep this producer source_sha unchanged; the
new integrated executor SHA is recorded separately in the receipt. Originals
stay byte-identical; only the verified private working copy is updated.

Account for all 18 instructions: six already submitted/reserved, then at most
12 new (10 SELECT, 2 DESCRIBE). The original SELECT ID is
`05c1e7d8-7ef4-4208-ab26-56552e29b7ef`, token
`64ed26cb6d228b79251721bbc4a8df7cb636ea3d52eddba3c4cdffda82f1f03b`.
Reconcile all six known IDs by GET without Start; verify the five existing
catalog definitions and compare the SELECT's results by its existing ID before
any remaining Start. FAILED/CANCELLED, actual timeout or mismatching results
stop the sequence. JSON key order is canonical serialization, not submit order;
the frozen plan defines the logical sequence. Keep the same round, authorization,
SQL, parameters, tokens, destinations and limits. No new DDL or object replacement
is needed if the catalog read-back matches.

Before the next hosted dispatch, inspect runs/attempts and identified journals
for further progress. If another run advanced the round, reconcile its provenance
and hashes explicitly instead of restoring these six entries as current truth.
After owner-reviewed integration use a new dispatch in develop with resume_source;
do not rerun the old executor. This preparation performs no dispatch or new SQL.
The persisted authorization remains applicable to the same plan/budget; it is not
renewed per attempt. Any SQL/hash, permission, resource or limit change needs a
separate decision. Final proof still requires all SELECT/DESCRIBE results, all
five catalog definitions and an unchanged complete S3 snapshot before/after.

After owner-reviewed integration, check whether another hosted attempt advanced
this round before choosing a source. Reconcile its journal/IDs; do not knowingly
restore stale history. Use the same round `lab-sbom-athena-v1`, unchanged SQL hash
and persisted authorization `TomasAlric-PR124-lab-sbom-athena-v1`. That reference
points to the owner's recorded authorization, not a newly inferred approval.
The correction does not increase scope or require a duplicate SQL authorization.
Do not dispatch while preparing this PR. After integration, provide the source
JSON via `resume_source`, together with the existing execute inputs. New SQL,
permissions/resources, a different hash or more than 18 distinct executions
requires a separate decision. No query, catalog object, result or snapshot is
deleted automatically. Failed/cancelled/TIMED_OUT history requires review; it is
not silently converted to success on restoration.

### Delimited response reconciliation

Outgoing SQL, context, parameters, round and token stay exact. Execution identity
compares lexical SQL tokens, ignoring only ASCII whitespace outside tokens;
case, quoted strings/identifiers, numbers, operators, parentheses and comments
(including line-comment termination) stay exact. Unsupported syntax fails closed.
This is deliberately more restrictive than a SQL equivalence engine, and separate
from the existing limited view comparison. Only the expected AwsDataCatalog may
be returned as awsdatacatalog; database/workgroup/query ID stay exact.

One directional response-only exception records `TRAILING_TERMINATOR_OMITTED`:
the authorized token list ends in exactly one standalone `;`, contains no other
standalone semicolon, and the response equals every preceding token exactly.
Normal token equality retains `EXACT_TOKENS_ASCII_WHITESPACE_ONLY`. A semicolon
inside a quoted string/identifier or comment stays within that token. An added
terminator, two terminators, an intermediate delimiter, another instruction or
a final comment after the semicolon cannot use this exception. The lexer,
outgoing QueryString, SQL plan/hash and token preimage remain unchanged. Both
SQL texts and their separate byte hashes are preserved in the journal observation
and comparison metadata; these hashes do not replace the authorized plan hash.

GetQueryExecution does not promise to return ExecutionParameters. Missing values
are recorded as NOT_RETURNED, not empty or remotely verified; exact submission
parameters remain bound by the frozen request/token and verified journal origin,
then actual results are compared. Returned parameters must match exactly. A
service Query with substituted literals is not guessed into equivalence with `?`.
Safe observed response fields and comparison rules are saved before an identity
failure, together with the diverging field and hashes, without SDK headers,
credentials, unrestricted error messages or signed URLs.

Only Glue StorageDescriptor.Location may equal the exact expected S3 URI minus
one terminal slash. Both strings and the rule are preserved. Bucket/key/snapshot
remain case-sensitive; no parent/sibling URI, `%2F`, `//`, dot segment, query or
fragment is accepted. SQL keeps its final slash. Column/type/order, partitions,
Parquet input/output/SerDe and successful round query identity remain required;
CreatedBy alone does not prove ownership. No UpdateTable/CREATE workaround runs.

Terminal states are reconciled before treating observation age as active-query
time. SUCCEEDED requires timezone-aware submission/completion timestamps,
nonnegative coherent total/engine statistics and completion within the original
120-second deadline, including initial submission time. Millisecond statistics
and timestamp duration may differ by at most 1 ms of rounding. Missing timing
is inconclusive; engine time alone cannot prove the deadline. The incident's
438 ms is TotalExecutionTimeInMillis (engine: 359 ms). The delay until a later GET
is reported separately and does not cancel an already timely completed query.
RUNNING/QUEUED keep the original persistent deadline; process intervals also use
a monotonic clock. Expiration cancels only the identified active query and stops;
a real terminal overrun is recorded as TIMED_OUT without cancelling completed
work. Invalid timing, FAILED and CANCELLED cannot yield verification.

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
