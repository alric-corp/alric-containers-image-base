# Athena reconciliation incident — selected public LAB evidence

Origin: alric-corp/alric-containers-image-base, workflow_dispatch/develop,
run 38080824102 / attempt 1, source 2702c4010e8d7bff561388bd27e9a6109f878d6d,
job 114297196683. This failed run submitted only table-0. These fixtures do not
claim a new query, successful hosted resume, independent review, SPDX authenticity,
corporate compatibility or authority to publish/promote an image.

The operator's persistent evidence is under
`audit-evidence/sbom-lab-s3-pr123-20261010T062053Z/athena-authorized-20261010T185242Z/execution-20261010T193408Z/`.
The original ZIP remains there, outside Git: artifact 11679714087,
50,980 bytes, SHA-256
`28d12a47b8488dc4ee83511c91f989272900180152271c69509b655093676edf`.
Its GitHub API digest was checked. The ZIP is not replaced by the synthetic ZIPs
made by tests; those have their own explicitly frozen test hashes.

Exact selected original bytes:

| File | Bytes | SHA-256 |
|---|---:|---|
| execution-journal.json | 2414 | 714c2e35c113c2f4185892f2431007d0e3ed945e1e5220627528fcc21e71f9ff |
| sql-plan.json | 257893 | ce1c1ab7079db6bbcbdf91c4d6f1ddfbd6ef9806d9cdbe848e34a8ba8259123e |
| authentication.json | 282 | 90eacf39ec2519098490484646d5bcedadfbbadd03e0d03ed59f25348f9f1a7b |

The journal's trailing newline is intentional. It remains SUBMITTED, with query
f65fa3ea-3d73-4d3d-a2b6-13637500920d and token
80d33f677de36228e9c2d8ed6bf34207f6bd400c2d779fdfcdd42d8e245ca3d8.
The SQL plan includes public historical expectations from the existing golden
corpus, not newly produced Parquets or a changed authorization. No private keys,
credentials, OIDC tokens, state, restricted corporate files or complete cloud
dossiers are included.

Selected/reformatted API content (these files have their own hashes and are not
the original complete API response bytes):

- query-execution.json: QueryExecution object from
  `failed-query-metadata-readback.json`; HTTP/ResponseMetadata removed. Actual
  SUCCEEDED, Catalog awsdatacatalog, SQL whitespace difference, total 438 ms,
  engine 359 ms, timezone-aware submission/completion timestamps retained.
- glue-table.json: only the created table's Table object from
  `catalog-after-failure.json`; HTTP/ResponseMetadata and other objects removed.
  Actual Location lacks the final slash; columns/Parquet formats/CreatedBy kept.
- github-metadata.json: selected artifact/run/attempt/job/upload-step facts from
  execute/run.json, artifacts-api.json and jobs-api.json. API download URLs,
  HTTP headers and unrelated fields removed. Tests use an injected client;
  metadata fixtures do not independently authenticate a GitHub response.

Negative mutations and missing-parameter responses are SYNTHETIC, based on these
fixtures and the documented API contract. Test clients return frozen expected
rows; they are not SQL engines. Separate tests rebuild the exact approved plan,
compare requests/tokens, reconcile the real first response and simulate the 17
remaining starts, interruption and a complete second pass with zero starts.
