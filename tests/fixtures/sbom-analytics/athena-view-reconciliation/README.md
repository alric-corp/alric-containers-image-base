# Glue view reconciliation incident — selected public LAB evidence

Origin: alric-corp/alric-containers-image-base, workflow_dispatch/develop,
run 38097506220 / attempt 1, executor `dcdbf3151fc85fe2385f059c2d9bc75586a56134`,
job 114346366994. The resume restored six entries, then stopped with
`GLUE_VIEW_SQL_UNSUPPORTED` while reconciling `view-2` (sbom_inventory_v1), before
execute_plan: no StartQueryExecution, no GetQueryResults, no snapshot-after.json.

The complete artifact is kept privately in audit-evidence, outside Git:
artifact 11686421115, `sbom-athena-38097506220-1`, 213530 bytes, SHA-256
`d43567eb8fb2293a37b754cb110fe8bc73213d6a7db374596439c1415c93418a`
(GitHub API digest checked by the operator). That ZIP does NOT contain the full
Glue view responses or resources-before.json.

Exact selected original bytes (from the ZIP above):

| File | Source member | Bytes | SHA-256 |
|---|---|---:|---|
| execution-journal.json | athena-reports/execution-journal.json | 36155 | e621e60802bd9e7017460a012ec783ea17478cf0df0c26892c99624d03906101 |
| authentication.json | athena-reports/authentication.json | 282 | 303f9009a2e3696501211e5a98810f365863439b6942828aaa864b40cc1ccbaf |

The same ZIP keeps the ancestor `athena-resume-source/execution-journal.json`
(35270 bytes,
`e4a4410fc7f8149f8e7c3b859f028def03b5cfa3bd3133e7dcc2417bc26d5519`), already versioned byte-identically as
`../athena-six-entry-resume/execution-journal.json`. Both have six entries, the
same IDs, requests and tokens; only the five DDL entries differ, in
identity_comparison and recorded_get_attempts. Reuse
`../athena-reconciliation/sql-plan.json` (257893 bytes,
`ce1c1ab7079db6bbcbdf91c4d6f1ddfbd6ef9806d9cdbe848e34a8ba8259123e`).

Selected/reformatted API content (own hashes; not the original response bytes):

- glue-tables.json: the `Table` object of each of the five GetTable responses,
  keyed by catalog name, with ResponseMetadata (request id, HTTP headers)
  removed and no other field changed. Source: the operator's separate
  read-only administrative collection (Tomas-Instructor, GetTable only, after
  the failure), `read-only-diagnosis/<name>-get-table.json`:

  | Name | Bytes | SHA-256 |
  |---|---:|---|
  | sbom_observation_rows_v1 | 5882 | 563a1c23690b43cefb81b628ab3c0cb5012a831ec3351e3ffd1eec1dc50a2058 |
  | sbom_package_rows_v1 | 3433 | 06cb62aa2cd417ca7ed02ccef23667a6ae0f6a04ed18e2d35c6da7b62c3195c1 |
  | sbom_observations_v1 | 9431 | c626a78ae64cccdebf19b90f4e4d0c30db03bfba578bb1cbec4068899367368f |
  | sbom_packages_v1 | 4478 | 04e6480f7b12e2265540b37e6228b8554a7c14b54075ee94b0f63d00eebbd149 |
  | sbom_inventory_v1 | 12000 | f79bbdf8e6358e7aa37a97f48e4c33503299ef2006a1dfc34e549c271801432e |

  These are not workflow outputs. Decoded originalSql SHA-256:
  observations `a725ca32817d1beb55ebe7b4343d785358073655cb118798edd79ecf0d09bd2e`,
  packages `099ef49239c71337f9d7791528b6205542e751e7787228756f7cffb552733f47`,
  inventory `589973a7f6aaa6c671af4ed8d88a7c199240a946f90a868d96371b0df1ac9a2d`.
- github-metadata.json: selected run/attempt/artifact/job/upload-step facts
  from resume-run-final.json, resume-artifact-api.json and
  resume-jobs-final.json; URLs, node ids, headers and unrelated fields removed.

SYNTHETIC in tests: every view mutation (a real Presto envelope with only the
named field replaced), transport ZIPs and their hashes, the SELECT terminal
response/timing, the query result pages (fake client returns frozen expected
rows; not an SQL engine) and the test-round run() catalog/journal. Simulation
journals stay in temporary directories and must never be supplied to a hosted
resume.

No credentials, OIDC tokens, signed URLs, Terraform state or corporate material
are versioned here. CreatedBy ARNs are kept as returned; they do not prove
ownership. These fixtures do not prove hosted Athena results, SPDX authenticity
or image publication authority (ATHENA_HOSTED_PROOF=NOT_PROVEN).
