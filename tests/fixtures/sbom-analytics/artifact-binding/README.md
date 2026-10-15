# Artifact binding — GitHub REST artifact records (LAB real)

`go1-26-1.artifact-api.json` and `go1-26-dev-1.artifact-api.json` are the
GitHub REST responses (`GET /repos/{owner}/{repo}/actions/artifacts/{id}`)
saved, byte for byte, with the two ZIPs already versioned in
`../build-artifacts/`. They come from `alric-corp/alric-containers-image-base`,
run `37806495087`, attempt `1`, commit `4c1783e8c2a36e0f79f453b2f080a23a0eeea0d3`,
and were preserved privately in the 2026-10-11 corporate handoff inputs.

| File | Artifact ID | SHA-256 of the record | `digest` field (= ZIP SHA-256) |
| --- | ---: | --- | --- |
| `go1-26-1.artifact-api.json` | 11562328737 | `1780400af55f6cbbabca736a31a67b94af81ab4909ed5e20fe16e83df0f9975c` | `3d4f92aa…f2ca` |
| `go1-26-dev-1.artifact-api.json` | 11562923040 | `81273413bde83845e6e8f2839085dc201be201646a286931362e34baf915a256` | `dfab594f…0e48` |

Their names avoid the repository-wide `sbom-*.json` ignore rule. Only
`test_artifact_binding_lab.py` reads them; it is LAB-only, like
`test_artifact_input_lab.py`, and not part of a corporate port. The portable
adapter tests (`test_artifact_binding.py`) generate a SYNTHETIC sample and use
no LAB identity. These records prove the field names and the digest semantics
of github.com; a GitHub Enterprise Server record is NOT_VERIFIED here.
