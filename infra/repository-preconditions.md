# Repository reconciliation after the greenfield rehearsal

2026-09-20 UTC. Scope: local validation, CI and portability only. No Terraform
apply, infrastructure recreation, catalog change, build, publication or promotion.
The completed [greenfield rehearsal](rehearsal-evidence.md) remains the baseline.

## Baseline and ownership

| Repository | Local HEAD at inventory | Published main at inventory | Local status |
| --- | --- | --- | --- |
| image-base | `22710948ff72d4d1eeecbda81725f23674ef91ce` | same | 18 preserved changes |
| reusable-workflows | `df52144b991dce2be611877a1afabfb40b178a8c` | `b87bda30545041ddb5d35c345ffc155bbc611dc8` | clean; identical trees, merge-only difference |
| registry | `c15f07299cdbeb1d2d3c872df5026ccacbce6ad0` | `e1bea8d937700f2c951bb934cb179df6f239520a` | clean feature branch; retirement notice on main |

Published image-base main already contains Infra colocation (`24413a4`), the
hosted provider checksum (`c8b72e8`) and rehearsal/PR evidence through `2271094`.
Nothing was reset or discarded. The registry remains superseded, not archived.

## Preserved-change inventory

Counts describe the original per-file diffs, not the eventual number of files
in this reconciliation: found 18, retained 17, dropped 1, superseded 0. Dropping
one deletion means restoring a legitimate product test, not discarding data.
No preserved hunk conflicts semantically with the new Infra layout or duplicates
main. Surrounding obsolete topology descriptions were corrected as documentation.

Categories: B = remove local reusable checkout; C = Makefile; D = CRLF;
F = documentation; G = stale/superseded. A (Windows harness), E (explicit UTF-8)
and H (other) have no original local diffs in this inventory.

| File | Change | Category | Still needed? | Reason |
| --- | --- | --- | --- | --- |
| `.gitattributes` | Enforce LF | D | Yes, refined | Protect Makefile, shells and proven byte-sensitive text |
| `.github/workflows/ci.yml` | Remove extra checkout/shared lint | B | Yes | Stale checkout fails before product validation |
| `.gitignore` | Remove obsolete nested-clone rule | B | Yes | No second checkout is needed |
| `CONTRIBUTING.md` | Single-clone validation instructions | F | Yes, refined | Explain local caller-input guarantees and prerequisites |
| `Makefile` | Local-only lint/validation targets | C | Yes | All ordinary checks use this repository alone |
| `README.md` | Correct validation and ownership docs | F | Yes, refined | Product Infra owns ECR, not the publisher |
| `TODO/adjust-certificates.md` | Remove obsolete lint command | F | Yes | Command no longer exists |
| `docs/corporate-production-readiness.md` | Correct checkout/topology assumptions | F | Yes, refined | Root factory, separate reusable and independent Infra |
| `docs/m11-m04-operational-health.md` | Explain retention ownership | F | Yes, refined | Shared upload internals belong to reusable; Infra uploads remain local |
| `docs/repository-architecture.md` | Explain consumer-only checks | F | Yes, refined | Local input bindings remain enforced |
| `docs/wolfi-signing-key.md` | Replace obsolete lint command | F | Yes | Trust/hash verification remains mandatory |
| `policies/operations/health.json` | Remove shared uploader declarations | B | Yes, refined | Keep local upload coverage, including colocated Infra |
| `scripts/pipeline/governance/workflow_dependencies.py` | Remove Git/executor inspection | B | Yes, refined | Keep origin, exact inputs, full SHA, coherent callers and local Trivy pins |
| `scripts/pipeline/operations/operational_health.py` | Enumerate local workflows | B | Yes | No external implementation required |
| `tests/integration/pipeline/governance/test_shared_workflow_contract.py` | Delete duplicated executor checks | B | Yes | Reusable tests its internals; local adapters retain coverage |
| `tests/integration/pipeline/operations/test_retention_policy.py` | Delete local retention test | G | No; deletion dropped | Valid product test restored unchanged |
| `tests/unit/pipeline/governance/test_pr_execution_scope.py` | Use real policy-path fixture | B | Yes | Preserve conservative full validation profile |
| `tests/unit/pipeline/governance/test_workflow_dependencies.py` | Remove synthetic external checkout | B | Yes, refined | Keep local negatives, including missing/extra/unsafe inputs |

Two gaps introduced by the earlier Infra colocation were masked by the failing
checkout: its `TF_VERSION` pins lacked Renovate coverage, and its three artifact
prefixes lacked local retention declarations. Reconciliation covers the existing
versions and retention periods (binary apply plan: 1 day; PR plan/apply evidence:
5 days). No workflow version, retention behavior or Terraform resource changed.

## Read-only Infra regression

`terraform init` reused the active image-base S3 backend; `terraform validate`
passed. A refreshed plan returned detailed exit code 0 and `No changes`.
`verify_plan.py --mode noop` confirmed exactly 48 no-op managed resources:
16 repositories, 16 lifecycle policies and 16 repository policies.
`readback.py --expect-empty` independently confirmed 16 ECRs, identical catalog
sets, zero images, and the complete versioned settings/policies/ownership tags.
The 64 offline Infra tests passed. The PR workflow remains plan-only.

## Local validation before push

`make test-unit`, `make test-integration`, `make lint-local`,
`make lint-workflows`, `make check` and `git diff --check` passed without a
nested reusable checkout or any versioned reference to its obsolete path.
The suite contains 384 unit tests and 31 integration tests. One existing unit
test runs only on Windows (native shim-directory cleanup); its macOS skip is
unchanged and does not replace product or shared-contract coverage. TLS integration
uses a real local socket; the sandbox denied it, then the complete suite passed
with the required socket permission, without changing or skipping that test.

The reusable repository independently passed all 14 tests, `check_contracts.py`
and actionlint. Its working tree stayed clean; its local and published-main trees
are identical. Final committed content must also pass the same product commands
in a fresh single-repository clone before push. Hosted CI results belong to the
resulting PR; local PASS is not a claim of native reusable execution.

## Portability and remaining execution-access boundary

The Windows Git Bash harness fixes in `81d2616` and `cb3e410` remain unchanged;
no WSL dependency was added. Previously proven Windows support is retained,
not claimed as a fresh native Windows run. On macOS, an isolated Git checkout
with `core.autocrlf=true` proved LF and byte-identical SHA-256 for all seven
protected files, while an unprotected control actually converted to CRLF.
The 15 Wolfi trust tests passed in that converted checkout. Certificate extension
wildcards are intentionally absent because those formats may be binary.
No explicit UTF-8 changes were among the 18 diffs; a broad encoding migration
is not included or claimed complete.

[CI run 35483086600](https://github.com/alric-corp/alric-containers-image-base/actions/runs/35483086600)
failed at the additional reusable checkout with `Repository not found`.
The full caller SHA `7a9b055a462eeb8552d3404c26538b44e8ccd83f` exists and remains
unchanged. Removing the obsolete local checkout does not grant remote access.

Read-only GitHub inspection found image-base public, reusable-workflows private,
and reusable Actions access `none`. A public caller can consume only public
reusable workflows under [GitHub's access rules](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations#access-to-reusable-workflows).
Native remote execution therefore remains blocked pending an explicitly approved
visibility/access decision. No visibility change, wider token, secret injection
or moving SHA was introduced. Build/promotion stay paused; Go 1.26 is not started.
