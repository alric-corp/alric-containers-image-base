# Build artifacts — `sbom-<framework>-<attempt>` contract

These are two real LAB build artifacts, kept as GitHub returned them (the ZIP
from `archive_download_url`). They come from `alric-corp/alric-containers-image-base`,
run `37806495087`, attempt `1`, push to `refs/heads/develop`, commit
`4c1783e8c2a36e0f79f453b2f080a23a0eeea0d3`.

| File | Artifact ID | Bytes | SHA-256 (equal to the API digest) |
| --- | ---: | ---: | --- |
| `sbom-go1-26-1.zip` | 11562328737 | 18330 | `3d4f92aa57234511ecbcc0d570e1fcbfef3cb4ceaf7f07c20ae1c4ebf97ef2ca` |
| `sbom-go1-26-dev-1.zip` | 11562923040 | 36170 | `dfab594f4a2685ec9918d6ef6349da2801d4c7770f3b348b7612703a64070e48` |

Every member of both ZIPs is already versioned byte for byte in
`../../hgc04/materials.zip`:
- the SPDX documents, `apko.lock.json`, `build-inputs.json` and
  `validated-index.json` are under `candidates/<framework>/`;
- the three `*-evidence.json` files are under
  `candidates/<framework>/receipts/sbom/`.

These two ZIPs therefore add only the container format of a real artifact. The
SPDX documents are the same six documents as the S3/Athena LAB batch
(`../lab-frozen-plan.zip`).

Tests are split in two modules:
- `test_artifact_input.py` uses only these ZIPs and carries no LAB destination
  or account. It is the portable part.
- `test_artifact_input_lab.py` is LAB-only. It compares the result with the
  frozen LAB batch, compares `spdx.checksum` with `release_manifest`, and checks
  that no LAB destination or round value is present.

## Corporate contract

The corporate collection (02) reports the same artifact name and the same six
members:
- `sbom/sbom-index.spdx.json`, `sbom/sbom-x86_64.spdx.json`, `sbom/sbom-aarch64.spdx.json`;
- `apko.lock.json`, `build-inputs.json`, `validated-index.json`.

The LAB artifacts also carry three HGC-03 evidence files. The staging adapter
does not read them and lists them as `unconsumed` in its receipt.

## What the tests derive

These cases are built in temporary directories and are not corporate bytes:
- the six-member, corporate-shaped ZIP;
- the extracted directories;
- every mutation;
- every selection that uses another run, attempt or registry.

No corporate sample, credential, registry account or destination is
versioned here.
