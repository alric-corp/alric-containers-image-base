# HGC-04 historical test inputs

These files are **HISTORICAL_TEST_INPUT**, not a production custody record.
Signing them with disposable local TEST_ONLY keys does not grant retrospective
HGC-04 authority. No production signing key, private key, credential, complete
cloud API response, cache or OCI layer is included.

Source: public
[consumer run 37806495087](https://github.com/alric-corp/alric-containers-image-base/actions/runs/37806495087),
attempt 1, push / refs/heads/develop, consumer commit
`4c1783e8c2a36e0f79f453b2f080a23a0eeea0d3`, reusable commit
`fd44ef512cf2e3ef9c65d0c005a9aa878ee26a69`.

| Original GitHub ZIP | Bytes | SHA-256 |
| --- | ---: | --- |
| melange-repo.zip | 12293 | eaa8c662e7f91d37ba4e9bde024309f3fea5116ed7eb6ef7f53c137c1f436d99 |
| melange-reproduction-reference.zip | 3737 | c0e9b871ff0a24f7b5dcfd947b056a47b89a49fdb04943d23f4718b5a31b0964 |
| melange-reproducibility.zip | 16458 | cc07c1ef2391bf6bd9097c2a74fe2b870fb535bcbe54cb3349db2c6a7ed2fdba |

The three originals are byte-preserved from the prior HGC-03 read-back, with
their independently recorded API digests. `materials.zip` is a **new fixture
container**, with deterministic ZIP_STORED members. It holds a curated
acquisition snapshot, source/configuration and raw Git path proofs, exact
authorized verifier, and selected original candidate/publication/SBOM/trust
documents for the complete go1-26 runtime/dev unit. Raw Git objects allow
verification without a GitHub query or a local checkout fallback.

`expected.json` and `origins.json` are curated test configuration. The expected
archiver is explicitly `hgc04-offline-test`, not an assertion that a historical
archiver job existed. The snapshot records native producer job/runner IDs,
artifact metadata and checkout observations; it is not represented as an
original API response. Candidate copies from the earlier read-only release
audit preserve S3-object and artifact bytes separately, with no new S3 access.
The only S3 material is selected release JSON; unnecessary service responses
are omitted.

Origins of selected artifact files record the ZIP digest seen at acquisition
and `zip_preserved=false`. Their file digests can be recalculated; their
original ZIP digests cannot. Three core ZIPs and all their member bytes can be
recalculated. The complete member inventory is generated and checked by the
package contract; no fixed APK count is assumed.

The preserved verifier comes from
[scripts/verify_reproducibility.py at fd44ef5](https://github.com/alric-corp/alric-containers-reusable-workflows/blob/fd44ef512cf2e3ef9c65d0c005a9aa878ee26a69/scripts/verify_reproducibility.py),
SHA-256 `93504d7fd1b887b29c318c8e75eb0a41e282fd37453410e5ab7c6b9b19f1ca1a`.
Its independent external pin and Git path proof are both checked before
execution. The repository does not distribute a private fixture signing key;
tests generate and discard keys at runtime.
