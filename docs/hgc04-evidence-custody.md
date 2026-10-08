# HGC-04: offline evidence custody core, schema v1

Status: **IN_PROGRESS / NOT_ENABLED / hosted proof NOT_PROVEN**. This change
implements an offline protocol and tests, with no workflow integration, cloud
adapter, production signer, infrastructure change or historical backfill.
HGC-01, HGC-02 and HGC-03 retain their technical closure. Independent review
and owner acceptance are separate from technical verification.

## Baseline and compatibility

The implementation starts from consumer `develop` at
`4c1783e8c2a36e0f79f453b2f080a23a0eeea0d3`, also the design baseline. The
live branch and open/closed PR inventory were checked before editing; no
existing HGC-04 implementation or baseline delta was found. Work takes place
in an isolated clone; the preexisting local U1 work is not an input.

`release_store.Store.get/put`, release/candidate manifests v1 and historical
HGC receipts are unchanged. The JSON Store canonicalizes documents and
compares parsed JSON on immutable conflicts. It cannot establish preservation
of original binary or JSON bytes. `EvidenceStore` is a separate interface;
there is no optional binary mode added to the JSON Store.

## Storage interface and frozen requests

`evidence_store.py` defines these operations:

| Operation | Contract |
| --- | --- |
| `get(key, version_id=None)` | Return immutable bytes, application metadata and an opaque nonempty version; `FOUND`, explicit `MISSING`, or operational `ERROR`. |
| `create_once(key, FrozenObject)` | Atomic conditional creation, followed by retrieval and byte/metadata comparison of the returned version. |
| `keys(prefix)` | Complete, sorted, unique inventory, bounded to 4096 keys; failure/incompleteness is `ERROR`. Used only to identify partial custody when commit is absent. |

The transport is mandatory and injected. `MemoryTransport` uses a process
lock around creation, retrieval and inventory; equal and unequal concurrent
writers are tested. It is an isolated simulation, not a durable filesystem or
S3 implementation. No credentials, configuration or cloud client are looked
up on import, construction or test execution.

`FrozenObject` copies application metadata into an immutable sorted tuple.
Content equality means exact bytes **and** exact application metadata.
For custody objects, metadata is `kind`, `schema_version="1"` and `sha256`.
Version IDs, transport request IDs and response timestamps are not content.
No overwrite or delete operation is exposed.

| Write result | Meaning |
| --- | --- |
| `CREATED` | Conditional creation succeeded and that version was read back identically. |
| `ALREADY_PRESENT_IDENTICAL` | Conditional precondition or lost-response reconciliation retrieved the frozen bytes and metadata identically. |
| `CONFLICT` | Same logical key contains different bytes or application metadata. Semantically equal JSON or a new valid signature still conflicts. |
| `ERROR` | Denied access, timeout, unavailable transport, failed/inconclusive reconciliation or failed read-back. |

The conditional PUT is the atomic primitive: an existence check is never its
replacement. A future S3 adapter must use simple `PutObject` with
`If-None-Match: *`, without automatic multipart, and map errors explicitly.
AWS documents `412 PreconditionFailed` for an existing key and operational
`409 Conflict` during conflicting conditional operations; **409 does not
establish different content**. See
[conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html).
Only an explicit missing-object/version response maps to `MISSING`; access
denied is never absence. A requested version must be fetched explicitly and
never fall back to latest. AWS distinguishes these permissions and errors in
[GetObject](https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html).
This PR does not implement or call an S3 adapter.

## Two objects, no hash cycle

The only authoritative paths are derived from **external** expected identity:

```text
releases/r<RUN>-a<ATTEMPT>/evidence/hgc04/v1/payload/<PAYLOAD_SHA256>.zip
releases/r<RUN>-a<ATTEMPT>/evidence/hgc04/v1/commit.json
```

A caller cannot select an arbitrary URI from an unauthenticated document.
Each attempt has its own release ID. The payload is a **new custody ZIP**,
not an original GitHub artifact, with this layout:

```text
originals/melange-repo.zip
originals/melange-reproduction-reference.zip
originals/melange-reproducibility.zip
acquisition/context.json
source/<source paths recorded by HGC-02>
git/source/commit
git/source/trees/<object ID>
git/reusable/commit
git/reusable/trees/<object ID>
verifier/verify_reproducibility.py
candidates/<framework>/<selected publication, SBOM, trust and receipt files>
release/<optional store/artifact candidate/manifest copies>
```

The three original ZIPs are inserted intact with ZIP_STORED. Each incorporated
receipt, APK, APKINDEX, public key, SPDX and selected external document keeps
its original bytes. No gzip/tar/SBOM/timestamp normalization is performed.
Envelope members are sorted, regular files mode 0644, Unix ZIP metadata,
1980-01-01 00:00:00, no comments/extra fields and no compression. Predictable
envelope metadata does not modify metadata inside original ZIPs.

The canonical **new** manifest is schema_version `1`, kind `hgc04-custody`,
with exactly these fields:

| Field | Contents |
| --- | --- |
| `identity` | Repository and immutable repository/owner IDs; source registry; release/run/attempt/event/ref/source SHA; distinct caller, reusable, archiver, publisher and reviewer; expected candidate index/platform digests. |
| `acquisition` | Fixed path `acquisition/context.json`. |
| `producers` | Original artifact metadata and actual producer job/runner/attempt for each core artifact. |
| `inventory` | Every payload file: `path`, `type=file`, `size`, `sha256`, in sorted order. |
| `core_archives` | Each original ZIP: path, size, SHA-256 and complete member inventory with original member sizes/hashes. |
| `materials` | Exact additional-material list: path, role and origin. |
| `verifier` | Repository, commit, source path, payload path and script SHA-256. |
| `policy` | Externally named policy, `TEST_ONLY` profile and exact v1 limits. |
| `limitations` | Explicit read-back, hosted-job-only and out-of-scope boundaries. |
| `payload` | Confirmed expected key, original payload size, SHA-256 and specific VersionId. |

`PreparedPayload.plan` contains all these fields except `payload`.
The payload contains neither its own hash nor a future commit/signature hash.
The manifest references the confirmed payload. `commit.json`, kind
`hgc04-commit`, contains exactly `schema_version`, `kind`, `manifest`, `bundle`.
Both byte fields have `{encoding: "base64", size, sha256, data}`; canonical
base64, exact length and separate digest are checked. Manifest and bundle are
never reserialized after signing. `FrozenCommit.sha256` is calculated outside
the envelope. A new PSS signature over the same manifest produces different
commit bytes and is not an identical retry.

For a selected file from an artifact whose complete ZIP is omitted, inventory
SHA-256 is recalculable on recovery. Origin `source_zip_sha256` records the
archiver's acquisition digest; `zip_preserved=false` explicitly means the
reader **cannot recalculate that source ZIP digest**. Core ZIP digests are
recalculable. S3 and artifact copies of a candidate/manifest occupy distinct
paths, preserve distinct original bytes and are never treated as byte-equal
on the basis of parsed JSON equality.

## Parsing, completeness and limits

Custody and acquisition schemas reject unknown versions/fields, missing
fields, duplicate JSON keys, invalid types, nonfinite values, invalid digests,
sizes and identity links. Canonicalization applies only to newly generated
custody documents. API responses and other historical documents need not be
canonical. Existing receipt schemas remain governed by the pinned HGC-03
verifier as well as the wrapper's identity and inventory checks.

The exact core member set derives from each target's recorded output list,
not a fixed APK count. Both `x86_64` and `aarch64` require their own APKINDEX;
the reference and rebuild keys and required receipts/version file are explicit.
Extra/missing files are rejected. Candidate membership reuses the unchanged
complete runtime/dev unit contract. Selected publication files include raw
index/digest evidence, candidate identity, build inputs and lock, runtime gate,
three subject-specific SPDXs, publication evidence, retained cryptographic
verification material, and byte-equal HGC receipt propagation from validated
and SBOM artifacts. Complete OCI layers and indiscriminate caches are omitted.

| v1 bound | Value |
| --- | --- |
| Each ZIP, including inner ZIPs | 64 MiB |
| Each expanded file | 32 MiB |
| Aggregate expanded bytes across outer and all inner ZIPs | 128 MiB |
| Aggregate member count across outer and all inner ZIPs | 4096 |
| Relative path depth / UTF-8 bytes | 16 / 512 |
| Each parsed JSON document / complete commit envelope | 4 MiB |

The observed historical runtime/dev fixture produces approximately 1 MiB of
payload, 67 outer members and 15 core members. These limits provide margin
without claiming measurement of every future catalog release. Supporting a
larger set requires an explicit versioned contract decision, not silently
accepting limits from a manifest. Packer input is bounded before allocation;
central-directory counts are checked before ZipFile allocates members.
Expansion is streamed with bounded raw-deflate chunks; actual byte counts,
CRC, declared lengths and shared budgets are checked, rather than trusting
ZIP header sizes. Local headers, descriptors and central entries must agree;
overlapping/unlisted ZIP data are rejected.

Absolute paths, traversal, backslashes, duplicate/case-colliding paths,
file/directory collisions, symlinks, directory entries, special types,
encryption and ZIP extensions are rejected. ZIP has no portable hardlink
type: all extra fields that could encode link extensions are rejected.
Private-key PEM markers and credential/cache paths are rejected; an exact
allowlist/inventory is additionally required. This is not a general secret
scanner or a license to add arbitrary materials.

Recovery reserves a **new**, absolute destination in a caller-owned private
parent and rejects symlink ancestors and existing destinations. Callers on
systems with symlinked temporary roots must supply the canonical private
parent path. There is no overwrite/reuse of an extraction directory. This
assumes the caller controls that private parent; it is not a sandbox against
another process that can replace its ancestors concurrently. Reports and the
authorized script are outside the three exact-set verifier directories.

## Identity reconciliation and authentication

`ExpectedIdentity` and `TrustPolicy` must come from the caller's external
configuration. A receipt, manifest, bundled key or `release_id` is not the
authority for expected identity. The acquisition snapshot is preserved input
with a strict schema; this PR has **no GitHub acquisition client** and does
not claim that a fixture is an authenticated API response.

The snapshot records native run event/ref/source, resolved reusable and
publisher workflow paths/SHAs, actual producer job IDs/runner IDs/attempts,
artifact IDs/digests/dates and checkout observations. Those facts must be
collected/reconciled by the future trusted archiver. Receipt producer fields
are checked against this snapshot and external run identity, not used to
bootstrap them. Reference and rebuild require distinct native jobs and
runners and remain `CROSS_JOB_SAME_RUN`. Earlier-attempt producers may be
represented explicitly under a later audited attempt; they are not relabeled.

Caller workflow SHA, source SHA and reusable executor SHA are separate
fields. A caller workflow_ref alone cannot satisfy the resolved reusable
binding. Raw Git commit/tree/blob path proofs bind source/configuration and
verifier bytes to the authorized commits. The exact Git committer ISO date,
including offset, is compared to BUILD_DATE. Index/platform digests, runtime
unit digests, publication subjects, SPDX/provenance statements and receipt
copies reconcile candidates/publication with the native run. Tags and artifact
names alone never establish these associations.

Optional release/candidate copies additionally pass the unchanged v1 release
validator; their tags and SPDX predicate digests must match the preserved
candidate identity and original SPDX content. Calculating the existing v1
predicate digest does not rewrite the preserved document bytes. Selected
trust/release material must originate from the native approval job and its
release artifact, not another successful job with a convenient artifact name.

Original producer, archiver, publisher and reviewer have separate identity
fields. The archiver's signature vouches for acquisition assertions, subject
to its external trust policy; it does not turn those assertions into certified
run/attempt or reusable claims. Retained normalized OCI signature/provenance
verification outputs preserve hosted observations and digest links, **not a
fresh offline verification of the production image signer**. Production
claims, trust roots and their adequacy remain unproven.

Only native develop contexts are eligible in this profile: push, schedule or
workflow_dispatch on `refs/heads/develop`; PR events/refs are rejected even
when their receipt has `r<run>-a<attempt>`. No PR namespace or privileged
collector is activated, and pull_request_target is not introduced.

`Authenticator.authenticate(manifest_bytes, bundle_bytes, external_policy,
expected_identity)` must return a typed affirmation bound to both byte hashes.
Exceptions/boolean success do not approve origin. There is no unsigned or
hash-only fallback. The core currently accepts only the explicit `TEST_ONLY`
profile and **refuses every production profile**, even with an injected
authenticator. Tests use disposable RSA-PSS/SHA-256 keys generated at runtime;
the trusted public key is supplied externally, not taken from the package.
Joint replacement of document and key fails against the original trust.
Private keys are never fixture/repository members. These signatures are not
Sigstore and grant no production authority to historical evidence.

The verifier has independent external authorization, not just archiver
authorization. Supported pin:

```text
repository: alric-corp/alric-containers-reusable-workflows
commit: fd44ef512cf2e3ef9c65d0c005a9aa878ee26a69
path: scripts/verify_reproducibility.py
sha256: 93504d7fd1b887b29c318c8e75eb0a41e282fd37453410e5ab7c6b9b19f1ca1a
```

Even a valid custody signature cannot authorize arbitrary bundled code.
Recovery authenticates manifest/bundle first, retrieves the specified payload
version, verifies inventories/origin/Git proofs and external script identity,
then executes that script with isolated Python (`-I -B`), explicit expected
identity arguments, bounded timeout and an environment without cloud tokens.
The script's legitimate dependency is local OpenSSL. No Docker, Melange,
network collector or build is invoked. Exit 0 **and** READBACK_VERIFIED and
expected report bindings are required; stdout/stderr/exit code are preserved.

## Sequence, retry and reader states

The public operations enforce this order:

1. `prepare_payload`: validate inputs, freeze deterministic payload and plan.
2. `store_payload`: conditional create/reconcile and exact-version read-back.
3. `manifest_bytes`: reference those confirmed bytes and VersionId.
4. Explicit external signer/authenticator: no production implementation here.
5. `freeze_commit`: authenticate and freeze exact manifest, bundle and envelope.
6. `commit_record`: authenticate/recover payload and run HGC-03 before conditional
   commit creation; do not expose a complete record prematurely.
7. Recover commit and referenced payload again, authenticate and execute HGC-03
   from fresh directories before reporting successful finalization.

On restart, `commit_record` first authenticates/recovers an existing commit
without writing anything. Frozen requests are reused across retries: no new
ZIP metadata, acquisition time, manifest or signature is generated. Lost
success responses are reconciled by reading and comparing exact content.
Payloads without commits remain partial; no orphan is promoted or deleted.
Concurrent commits of different valid signatures conflict at the same key.
Read failures do not trigger replacement or fallback to latest.

| Reader state | Meaning |
| --- | --- |
| `COMPLETE_VERIFIED` | Authenticated complete payload and successful pinned read-back, explicitly `profile=TEST_ONLY`, `production_authority=false` in this PR. |
| `PARTIAL` | Payload inventory exists but final commit is absent. |
| `INVALID` | Present commit has missing/wrong payload, unsupported schema, failed authentication, inconsistent identity, inventory or read-back. |
| `REQUIRED_MISSING` | Both objects absent and external adoption policy explicitly requires custody. |
| `LEGACY_NO_CUSTODY` | Both objects absent and external adoption policy explicitly classifies this repository ID/release as legacy. |
| `ADOPTION_UNKNOWN` | Both objects absent without an applicable external adoption decision; absence is not approved. |
| `ERROR` | Access/transport/local execution failure prevents a conclusion. |

External adoption sets are immutable, disjoint and keyed by repository ID plus
release ID. No cutover date, retention duration or risk acceptance is invented.
Existing releases/receipts are not rewritten. A future publication link must
be a new explicit record, never an edit to frozen custody.

## Integrity, origin, retention and future activation

These are four separate properties:

* **Integrity:** byte/size/inventory checks and signed-manifest bindings are
  implemented and locally tested.
* **Origin/authorization:** the mandatory interface and external TEST_ONLY trust
  are tested; trusted acquisition and production keyless authorization are
  pending. No certificate claims about run/attempt/executor are invented.
* **Create-once/conflicts:** lock-based atomic simulation and strict retries are
  implemented. Conditional writes alone do not prevent deletion/recreation;
  AWS allows creation when the current version is a delete marker. Applied
  permissions, versioning and deletion protections are **NOT_VERIFIED**.
* **Availability:** this simulation does not prove durable service availability,
  retention, lifecycle, legal/WORM guarantees or administrator restrictions.

Activation requires separately approved production authentication/acquisition,
an S3 adapter and isolated hosted tests, applied IAM/bucket/delete/version
enforcement evidence, owner retention/cutover decisions and workflow
integration. No trust wildcard, permissions or roots are widened here.
No publication gate, hold/DEV stable/HOM/PROD/recovery behavior, build-once
publication, proving/U3A or validation selection changes in this PR.

The future hosted proof must recover only through durable storage into a new
directory and execute the authorized pin with external identity. It must not
query the original GitHub artifact, reuse scratch, rebuild outputs, wait for
real expiration or delete historical artifacts. Real conditional-write races,
lost-response recovery, exact-version reads and policy-protected attempted
overwrite/deletion require an isolated namespace and explicit write
authorization. Never mutate valid release records to test these protections.

## Local validation

```sh
python3 -B -m unittest tests.unit.pipeline.release.test_evidence_store \
  tests.unit.pipeline.release.test_evidence_archive \
  tests.unit.pipeline.release.test_evidence_custody
make check
```

Tests exercise original JSON/binary/ZIP preservation, strict inventories and
expansion bounds, idempotence/metadata conflicts, concurrent writers/commits,
lost responses, denied/timeout/version failures, premature/altered records,
joint document/key substitution, unauthorized code, native origin and
candidate/runtime bindings, adoption states, and real pinned HGC-03 recovery.
The invalid-signature test includes successful controls before and after;
recovery tests prohibit network tools/original scratch and use no cloud calls.
Selected local guard mutations are supplementary test evidence, not CI runs
or proof of deployed enforcement. See the PR validation record for results.

Implementation validation: baseline `make check` passed 637 unit and 39
integration cases. Final `make check` passed 718 unit and 39 integration
cases, with the same single preexisting Windows-only skip; all repository and
workflow lints passed. The 81 new HGC-04 cases passed without a skip. The
selected local mutation campaign detected removal of exact-byte comparison,
application-metadata comparison, requested-version selection, external
authentication, inventory-hash verification and verifier-exit enforcement:
6 detected, 0 survivors, 0 equivalent mutations. The complete positive control
passed afterward. These are local results, separate from the PR's normal CI.

`READBACK_VERIFIED` covers CA outputs, indices, public keys, signatures, original
control/data streams and recovered bindings. Historical cache and
RESOLUTION_INDEX remain `VERIFIED_BY_HOSTED_JOB`; dependency replay, full OCI
layers, CROSS_RUN and other work outside HGC-03 remain `NOT_PROVEN`.
