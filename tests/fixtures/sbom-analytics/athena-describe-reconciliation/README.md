# DESCRIBE reconciliation incident — selected public LAB evidence

Origin: alric-corp/alric-containers-image-base, workflow_dispatch/develop,
run 38103483249 / attempt 1, executor `bfb0f474756035a7d36b80c4454f138214feae8c`,
job 114364038710. The resume passed the catalog gate, reconciled six known IDs
without Start, verified 11 SELECTs and started describe_observations, then
stopped with `ATHENA_EXECUTION_IDENTITY_DIFFERS` (field Query.tokens): Athena
returned `DESCRIBE <table>` for the sent `DESCRIBE poc_distroless_sbom.<table>`.

The complete artifact is kept privately in audit-evidence, outside Git:
artifact 11688034210, `sbom-athena-38103483249-1`, 360130 bytes, SHA-256
`c303c6531dd824e06cd959144241a5960d099b6be11d6ae268668d2eba5bfcb6`
(equal to the GitHub API digest).

Exact selected original bytes (from the ZIP above):

| File | Source member | Bytes | SHA-256 |
|---|---|---:|---|
| execution-journal.json | athena-reports/execution-journal.json | 605578 | ff09f07e1754bd7bce21e1b76eba04b65158e257b0bb6636eef099e9b4551983 |
| authentication.json | athena-reports/authentication.json | 282 | 705e6c18b42fcfc808029825b876911f5654c387b3ab78fc14a1199baad53449 |

The journal has 17 entries: 16 VERIFIED and describe_observations SUBMITTED
(`e3264498-d19b-428a-80a8-a8f90a0ddce2`, token
`4fb38e95b4363447f9690faa5d15617ff88885bc3c4e3dc16dfb74f904ca72e5`). Its last
observation is QUEUED; the terminal state and results of that ID were never
read, so they are NOT_OBSERVED. describe_packages is absent. It also contains the
real GetQueryExecution responses and the real GetQueryResults pages of the 11
SELECTs. The ZIP keeps the six-entry ancestor
`athena-resume-source/execution-journal.json` (36155 bytes,
`e621e60802bd9e7017460a012ec783ea17478cf0df0c26892c99624d03906101`), versioned as
`../athena-view-reconciliation/execution-journal.json`; it is history, not the
current source. Reuse `../athena-reconciliation/sql-plan.json` (257893 bytes,
`ce1c1ab7079db6bbcbdf91c4d6f1ddfbd6ef9806d9cdbe848e34a8ba8259123e`) and the real
catalog in `../athena-view-reconciliation/glue-tables.json`.

`github-metadata.json` holds selected run/attempt/artifact/job/upload-step facts
from the API responses saved by the operator (run, jobs and artifacts listing);
URLs, node ids, headers and unrelated fields are removed. It has its own hash.

SYNTHETIC in tests: every mutation, transport ZIPs and their hashes, the
terminal state/timing of e3264498 (built on its real QUEUED observation), the
describe_packages execution, and both DESCRIBE result pages (real Glue column
names/types in an assumed `name<TAB>type<TAB>` layout). The real DESCRIBE result
format has not been observed; these tests do not prove it. Simulation journals
stay in temporary directories and must never be supplied to a hosted resume.

No credentials, OIDC tokens, signed URLs, Terraform state or corporate material
are versioned here. ATHENA_HOSTED_PROOF remains NOT_PROVEN.
