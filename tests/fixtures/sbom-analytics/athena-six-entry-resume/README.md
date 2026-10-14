# Six-entry Athena resume — selected public LAB evidence

Origin: alric-corp/alric-containers-image-base, workflow_dispatch/develop,
run 38088837347 / attempt 1, executor
`20ee0051018eefe94001b9639fd819c4b898ded7`, job 114320915808.
The failed run recorded five VERIFIED DDLs and one SUBMITTED SELECT. Its preserved
SELECT observation is QUEUED, not a claim of the query's current AWS state.

The complete original artifact is kept privately in audit-evidence, outside Git:
artifact 11683770809, `sbom-athena-38088837347-1`, 133908 bytes, SHA-256
`3929469270e781d57f0489b555cfe21c1a4fd85ab5e155f4a9ad0b07c0132232`.
The original ZIP digest was checked against the GitHub API and restored using
the integrated helper. No code from the artifact is executed.

Exact selected original bytes:

| File | Source member | Bytes | SHA-256 |
|---|---|---:|---|
| execution-journal.json | athena-reports/execution-journal.json | 35270 | e4a4410fc7f8149f8e7c3b859f028def03b5cfa3bd3133e7dcc2417bc26d5519 |
| authentication.json | athena-reports/authentication.json | 282 | 4b465c58d1798936cb0a431eaeb5c9829b2bedc4337bbd6a664f64be461771d5 |

Reuse `../athena-reconciliation/sql-plan.json`: its exact 257893 bytes also equal
the current artifact's `athena-reports/sql-plan.json`, SHA-256
`ce1c1ab7079db6bbcbdf91c4d6f1ddfbd6ef9806d9cdbe848e34a8ba8259123e`.
Do not use `../athena-reconciliation/execution-journal.json` (one entry) for the
next hosted resume. That older member also exists under athena-resume-source in
the real current ZIP. Tests include both full member paths to guard selection.

`github-metadata.json` contains selected real run/attempt/artifact/job/upload-step
facts, with its own representation/hash. URLs, HTTP headers and unrelated fields
are omitted. `request-fingerprints.json` freezes all 18 SQL/request hashes,
parameters and ClientRequestTokens computed by the baseline executor before the
comparison fix. These fingerprints are regression data, not new authorization.

Test transport ZIPs and their nested ZIP are SYNTHETIC and have their own hashes;
they are never represented as the original GitHub ZIP. Their current journal and
authentication members remain byte-identical to the selected real files above.
Five known DDL responses come from the saved journal. The successful SELECT
terminal response/timing, catalog descriptions and query result pages used by
the resume simulation are explicitly SYNTHETIC. The fake client returns frozen
expected rows; it is not an SQL engine. Simulation journals stay in temporary
test directories and must never be supplied to a hosted resume.

The original token/ID remain intact. Tests reconcile six known IDs with no Start,
then simulate exactly 12 starts (10 SELECT, 2 DESCRIBE) and a second complete pass
with zero starts. Failures, timeout, result differences, wrong/truncated/missing
history and the old nested journal cannot authorize new starts.

No credentials, private keys, OIDC tokens, Terraform state, complete cloud
dossiers or corporate material are versioned here. These fixtures do not prove
hosted Athena results, independent review, SPDX authenticity or image publication
authority. The complete evidence and separate current metadata read remain in
the private audit-evidence directory.
