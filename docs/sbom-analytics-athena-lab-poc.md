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
rows, 128 columns and 8 MiB responses. ColumnInfo/raw pages are journaled before interpretation. SQL
NULL and empty strings stay distinct; integers use declared types; only explicitly
JSON-projected columns use strict JSON parsing. Comparisons are multisets and
retain duplicate counts. DESCRIBE rows are recorded literally as text lines in the
observed shape, without guessing Hive output fields; Glue read-back verifies all
typed physical columns/locations.

The five catalog names are collision-checked using GetTable. Only
EntityNotFoundException denotes absence. Resumption requires this round's exact
successful DDL and compares physical columns/locations and ordinary Presto view
definitions. Views are compared as a restricted v1 structure, described below;
it is not a general SQL equivalence engine. Unknown representations fail closed,
with no replace or delete operation.

After SQL, a fresh complete snapshot read-back must match the initial fingerprint,
including marker/object bytes and current versions. Artifacts retain identity,
dependency versions, catalog/SQL plan, journal, actual pages/results, errors and
pre/post read-back, including failure. They are outside Parquet LOCATIONs and
the snapshot. No cleanup runs automatically.

### Glue view structure (run 38097506220)

The resume stopped at `GLUE_VIEW_SQL_UNSUPPORTED` before any new submission:
Athena stores the authorized inventory SELECT (`FROM obs o JOIN pkg p ON a = b
WHERE x AND y`) as `FROM (obs o INNER JOIN pkg p ON (a = b)) WHERE ((x) AND (y))`.
Both views with SELECT DISTINCT keep the template structure, reformatted only.

`view_structure` parses only `SELECT [DISTINCT] columns FROM source [WHERE
condition]`: one `database.table [[AS] alias]` or one inner join of two such
relations with an equality/AND ON condition, optionally wrapped once in
parentheses; conditions are `column = column|string|true|false` joined by AND.
`INNER` is accepted only between a relation and `JOIN`, `AS` only before a
relation alias. Parentheses are removed only when they return the same node;
nested AND groups are not flattened. Column list/order, qualifiers, DISTINCT,
fully qualified relations (database and snapshot), aliases and their binding,
ON/WHERE operand order and string/boolean literals stay exact; the whole input
must be consumed. Keywords are case-insensitive; unquoted identifiers must be
lowercase and are never case-folded. Subqueries, other joins, OR/NOT, functions,
casts, numbers, other operators, comments, delimited identifiers (never observed
in the real responses), `;`, catalog-qualified names, column aliases, more than
4 nesting levels, 4096 tokens or 64 KiB fail with a specific reason. Identity,
VIRTUAL_VIEW, the Presto envelope, catalog/schema and the round's successful
QueryExecutionId remain required; CreatedBy or a same name is not ownership.

The catalog read-back now runs inside the final snapshot read-back. Each object's
statement, QueryExecutionId, identity and the view's decoded definition/hashes are
recorded before its checks; unread objects stay NOT_OBSERVED and
resources-before.json is written only after success. On any failure
execution-failure.json keeps the original error, `catalog_readback` and a
separate `final_readback` (UNCHANGED, CHANGED or NOT_OBSERVED). snapshot-after.json
exists only when the after-fingerprint was read; a failed final read-back never
replaces the original error and never counts as PASS.
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

Historical source for that resume (run 38097506220 consumed it; see below):

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

### Candidate source after the view-structure correction

Run 38097506220 / attempt 1, executor `dcdbf3151fc85fe2385f059c2d9bc75586a56134`,
restored that six-entry journal and stopped during view-2 catalog reconciliation,
before execute_plan: no Start, no GetQueryResults, no new ID. Its journal keeps
the same six IDs, requests and tokens; the five DDL entries only gained
identity_comparison/recorded_get_attempts updates; the SELECT entry is unchanged
(SUBMITTED, historical QUEUED observation). A later SUCCEEDED/38330-byte read by
the operator is separate administrative evidence, not a journal state: the next
executor must GET the same ID and compare its results before any new Start.

Historical source for that resume (run 38103483249 consumed it; see below):

```json
{
  "run_id": 38097506220,
  "attempt": 1,
  "artifact_id": 11686421115,
  "source_sha": "dcdbf3151fc85fe2385f059c2d9bc75586a56134",
  "zip_sha256": "d43567eb8fb2293a37b754cb110fe8bc73213d6a7db374596439c1415c93418a",
  "zip_bytes": 213530,
  "journal_sha256": "e621e60802bd9e7017460a012ec783ea17478cf0df0c26892c99624d03906101",
  "journal_bytes": 36155,
  "sql_plan_sha256": "ce1c1ab7079db6bbcbdf91c4d6f1ddfbd6ef9806d9cdbe848e34a8ba8259123e",
  "sql_plan_bytes": 257893
}
```

The ZIP also keeps `athena-resume-source/execution-journal.json` (the 35270-byte
ancestor, same six entries) and its nested source ZIP. Select only
`athena-reports/execution-journal.json`; keep this source_sha, and record the new
executor SHA separately in the receipt. The budget does not restart: six reserved
plus at most 12 new (10 SELECT, 2 DESCRIBE), 18 in total.

### Candidate source after the DESCRIBE correction

Run 38103483249 / attempt 1, executor `bfb0f474756035a7d36b80c4454f138214feae8c`,
passed the catalog gate (three views EQUIVALENT), reconciled the six known IDs
without Start, verified 01_find_images and started 11 new requests. The 10 new
SELECTs are VERIFIED; all 11 SELECT result sets match the plan as multisets.
It then stopped at `ATHENA_EXECUTION_IDENTITY_DIFFERS` on `describe_observations`
(`e3264498-d19b-428a-80a8-a8f90a0ddce2`, token `4fb38e95…ca72e5`): Athena returned
`DESCRIBE <table>` for the sent `DESCRIBE poc_distroless_sbom.<table>`, with the
same context database. Its last observation is QUEUED; its terminal state and
results are NOT_OBSERVED. `describe_packages` was never reserved. The snapshot
final read-back was UNCHANGED (20 objects). Budget: 17 reserved, 1 remaining.

Historical source for that resume (run 38109412318 consumed it; see below):

```json
{
  "run_id": 38103483249,
  "attempt": 1,
  "artifact_id": 11688034210,
  "source_sha": "bfb0f474756035a7d36b80c4454f138214feae8c",
  "zip_sha256": "c303c6531dd824e06cd959144241a5960d099b6be11d6ae268668d2eba5bfcb6",
  "zip_bytes": 360130,
  "journal_sha256": "ff09f07e1754bd7bce21e1b76eba04b65158e257b0bb6636eef099e9b4551983",
  "journal_bytes": 605578,
  "sql_plan_sha256": "ce1c1ab7079db6bbcbdf91c4d6f1ddfbd6ef9806d9cdbe848e34a8ba8259123e",
  "sql_plan_bytes": 257893
}
```

Select only `athena-reports/execution-journal.json` (17 entries); the ZIP also
keeps the 36155-byte six-entry ancestor under `athena-resume-source/`. A new
dispatch with the integrated executor (never a rerun) performs GET only for the
17 known IDs, compares the eleven SELECT result sets again, reconciles
`e3264498…` by GET/GetQueryResults and only then makes at most one Start, for
`describe_packages`. FAILED/CANCELLED, a real timeout (including the historical
QUEUED observation past its original deadline, which is cancelled, not promoted),
a divergent context/table or empty/invalid DESCRIBE results stop before that
Start. PASS requires 18/18 VERIFIED, including both DESCRIBE result sets.

### Candidate source after the DESCRIBE results correction

Run 38109412318 / attempt 1, executor `7cc3a5165490d6c3b1f0b7b0d3991914a6125f8b`,
did the following:
- restored that 17-entry journal before OIDC and passed the catalog gate;
- reconciled the 17 known IDs without Start, and re-read and matched the eleven
  SELECT result sets;
- read `e3264498…` as SUCCEEDED (948 ms, 0 bytes, within the deadline).

It then stopped with `ATHENA_ROW_WIDTH_DIFFERS` in GetQueryResults and kept no
page. `describe_packages` was never prepared. The snapshot final read-back was
UNCHANGED. Budget: 17 reserved, 1 remaining.

An owner-authorized administrative read (GetQueryExecution and GetQueryResults
of that ID only, no Start) supplied the real page described above. That read is
not hosted proof.

Latest inspected evidence (not an automatic "latest" selection). Use it only after
review/integration and after confirming that no later run advanced the round:

```json
{
  "run_id": 38109412318,
  "attempt": 1,
  "artifact_id": 11690561959,
  "source_sha": "7cc3a5165490d6c3b1f0b7b0d3991914a6125f8b",
  "zip_sha256": "935e69060b25e94727eab1e512d4bfac28dc5de3e4916fc4e47c6b11c935165c",
  "zip_bytes": 555455,
  "journal_sha256": "a921dad4d384f17275a97b702f1141876e98bacd39804b2deda7dc6e23aa7b4c",
  "journal_bytes": 607331,
  "sql_plan_sha256": "ce1c1ab7079db6bbcbdf91c4d6f1ddfbd6ef9806d9cdbe848e34a8ba8259123e",
  "sql_plan_bytes": 257893
}
```

Select only `athena-reports/execution-journal.json` (17 entries, describe_observations
SUCCEEDED). The ZIP also keeps the 605578-byte journal of run 38103483249 under
`athena-resume-source/`, which also has 17 entries. A new dispatch with the
integrated executor (never a rerun):
- GETs the 17 known IDs and compares the eleven SELECT result sets again;
- reads and validates the DESCRIBE lines of `e3264498…` through the central OIDC
  role;
- only then makes at most one Start, for `describe_packages`.

After that Start the balance is zero. A later failure is reconciled by reading
the 18 IDs, never by a 19th ID. PASS requires 18/18 VERIFIED, including both
DESCRIBE result sets read by the hosted executor.

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

A second directional exception, `DESCRIBE_DATABASE_QUALIFIER_OMITTED`, applies
only to plan statements of kind DESCRIBE (execute_plan passes the kind; catalog
read-back does not). Workgroup, QueryExecutionId and the returned context are
checked first, so the exception never relies on unvalidated fields. The
authorized tokens must be exactly `DESCRIBE <db> . <table>` with `<db>` equal to
the sent and returned context database, an unquoted table, and the response
exactly `DESCRIBE <table>`. Table and snapshot stay exact; case, quotes,
EXTENDED/FORMATTED/TABLE, columns, partitions, catalog qualifiers, comments,
`;`, another statement or a combined terminator omission still fail. The
comparison records the rule, both SQL hashes and `validated_database`.
SELECT, CREATE VIEW and table DDL never use it.

GetQueryResults pages are journaled as they arrive. After the byte-limit check,
each page goes to the entry's `results_capture` (query ID and pages) BEFORE its
columns, header, width, types or values are interpreted. A failure therefore
keeps every page received so far. The error names the QueryExecutionId, page,
row, expected and observed width, page hash and the journal location of the
kept page. A page over the byte limit is not kept, and an incomplete chain
fails as an incomplete capture.

A capture is diagnostic only. It exists only on a SUCCEEDED, non-DDL entry, has
exactly those two fields and at most 16 pages. It never makes an entry VERIFIED
and is never read instead of GetQueryResults. After a successful read, the same
pages move to `results`. A failed capture write stops the run before any further
call.

DESCRIBE results follow the real response of `e3264498…`, captured read-only on
2026-10-11. ColumnInfo declares `col_name`, `data_type` and `comment` (string),
but every row has ONE text cell such as `name<pad>\ttype<pad>\t<pad>`. The
executor requires that exact ColumnInfo and one present VarCharValue per row.
It stores the rows as `results.lines`, unchanged: no split, strip, header
removal or dropped empty line. An empty result fails `ATHENA_DESCRIBE_EMPTY`; any
other shape fails `ATHENA_DESCRIBE_COLUMNS_DIFFER` or
`ATHENA_DESCRIBE_LINE_INVALID`. SELECT keeps its header, width, type and
multiset checks. A text cell is never accepted in a SELECT.

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
