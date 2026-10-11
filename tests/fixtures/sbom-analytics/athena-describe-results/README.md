# DESCRIBE results — real page and current 17-entry journal

Journal origin: alric-corp/alric-containers-image-base, workflow_dispatch/develop,
run 38109412318 / attempt 1, executor `7cc3a5165490d6c3b1f0b7b0d3991914a6125f8b`,
job 114381660912. The resume restored the 17-entry journal of run 38103483249,
passed the catalog gate, reconciled the 17 known IDs without Start (the eleven
SELECT result sets unchanged) and read `e3264498-d19b-428a-80a8-a8f90a0ddce2` as
SUCCEEDED (948 ms, 0 bytes scanned). GetQueryResults then stopped with
`ATHENA_ROW_WIDTH_DIFFERS`; that executor kept the page only in memory, so the
artifact has no DESCRIBE page. describe_packages was never prepared: 17 reserved,
1 remaining.

The complete artifact is kept privately in audit-evidence, outside Git:
artifact 11690561959, `sbom-athena-38109412318-1`, 555455 bytes, SHA-256
`935e69060b25e94727eab1e512d4bfac28dc5de3e4916fc4e47c6b11c935165c`
(equal to the GitHub API digest).

| File | Source | Bytes | SHA-256 |
|---|---|---:|---|
| execution-journal.json | athena-reports/execution-journal.json, byte-identical | 607331 | a921dad4d384f17275a97b702f1141876e98bacd39804b2deda7dc6e23aa7b4c |
| authentication.json | athena-reports/authentication.json, byte-identical | 282 | c7bbf418bdff0ed0870fcbb107d7ce4621d6628f45dceb7ade51875d143d6c10 |
| describe-observations-results.json | derived, see below | 7041 | 3cdd3f191e0e969ba2b310ce9022b060b9c442d1de365d6b7c2cd46b49a95fc1 |
| github-metadata.json | selected API facts | 1184 | d229667bc6af6253d939f9168b379b8ec286edabe61da8aa426b18f0e3bd9e7e |

The ZIP's `athena-resume-source/execution-journal.json` is the 605578-byte
journal (`ff09f07e…`) versioned in `../athena-describe-reconciliation`. It also
has 17 entries; it is history, not the current source.

`describe-observations-results.json` comes from an ADMINISTRATIVE, read-only
capture outside the workflow, authorized by the owner on 2026-10-11 for this one
query. Principal: IAM user Tomas-Instructor, account 712107929769, us-east-1.
Calls: STS GetCallerIdentity, then GetQueryExecution and GetQueryResults
(MaxResults 1000; one page, no NextToken) for e3264498 only. No Start, Stop, DDL
or S3 GetObject. SDK: boto3/botocore 1.40.39, the workflow versions. The file is a
one-page list holding the botocore-parsed response with ResponseMetadata removed;
ResultSet is unchanged. The raw HTTP body, the parsed response and the capture
manifest stay private. The raw body also carries unmodeled `Output`,
`ColumnInfos` and `ResultRows` fields, which botocore drops. This is not hosted
OIDC evidence: the hosted executor still has to read and validate the page.

Observed shape:
- ColumnInfo declares `col_name`, `data_type` and `comment`, all `string`.
- Each of the 43 rows has exactly ONE VarCharValue: the name padded to 20
  characters, TAB, the type padded to 20, TAB, then 20 spaces.
- There is no header row, no blank line and no partition section.
- Names and types equal the Glue columns.

The executor keeps each line as text. It does not split, strip or compare
lines with the schema.

SYNTHETIC in tests:
- every mutation, page split and transport ZIP;
- the describe_packages execution, and its page in the observed shape, built from
  the real Glue names and types;
- the interrupted-attempt scenario.

Simulation journals stay in temporary directories and must never be supplied to
a hosted resume. No credentials, OIDC tokens, signed URLs, HTTP headers,
Terraform state or corporate material are versioned here. ATHENA_HOSTED_PROOF
remains NOT_PROVEN.
