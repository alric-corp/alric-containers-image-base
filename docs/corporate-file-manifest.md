# Corporate file manifest

Exact list of what to copy **by hand** into the corporate monorepo from the
three sandbox repositories, after the production minimization completed on
17–18/09/2026. No `git clone` is used at the destination: files are copied
individually or by directory, from each repository's working tree as it
exists after that cleanup.

This manifest reflects the FINAL tree, not the full sandbox history. Every
path under **Copy** exists in the corresponding repository today. Every path
under **Do not copy** either does not belong in the corporate destination or
must never leave the sandbox. If a path is not listed under Copy, treat it as
excluded by default — this manifest is the allowlist, not a starting point to
prune from.

Source repositories (sandbox):

| Repository | Role | Files after cleanup |
| --- | --- | --- |
| `alric-corp/alric-containers-image-base` | Image factory (product) | 189 |
| `alric-corp/alric-containers-registry` | Infrastructure (Terraform/IAM/ECR) | 31 |
| `alric-corp/alric-containers-reusable-workflows` | Shared execution (validation/runtime/Trivy) | 16 |

## Copy

### Image factory (`alric-containers-image-base`)

Root:

- `README.md`, `RFC-013-Image-Base-Completa-com-Mermaid.md`, `CONTRIBUTING.md`
- `Makefile`, `requirements-dev.txt`, `renovate.json`
- `.editorconfig`, `.gitattributes`, `.gitignore`

`.github/` (19 files):

- `CODEOWNERS`, `dependabot.yml`, `pull_request_template.md`
- `workflows/` — all 9: `build-base-images.yml`, `ci.yml`, `image-trust.yml`,
  `pipeline-health.yml`, `promote-stable.yml`, `recover-stable.yml`,
  `test-runtime-images.yml`, `validate-base-images.yml`, `workflow.yml`
- `scripts/` — all 7: `README.md`, `oci_artifact.py`, `report_unfixed_cves.py`,
  `runtime_images.py`, `scan_images.py`, `tool_versions.py`,
  `validate_inputs.py` (temporary adapters consumed by the published
  reusable-workflow contract — see `docs/repository-architecture.md`)

`distroless/` — all 3 files (`image-base.yaml`, `java.yaml`, `runtime.yaml`).

`frameworks/` — all 16 definitions (the active catalog).

`melange/`:

- `image-base-ca-certificates.yaml`
- `certificates/manifest.json`, `certificates/anchors/.gitkeep`
- `keys/wolfi-signing-key.json`, `keys/wolfi-signing.rsa.pub` — the real
  Wolfi public signing key pin; not sandbox-specific, verifies the same
  upstream in corporate

`policies/`:

- `README.md`
- `aws/github-actions-image-base-trust.json` — mechanism and shape; the
  corporate trust policy will carry different account/repository IDs
- `governance/reusable-workflows.json`
- `operations/ecr-lifecycle.json`, `operations/health.json`
- `release/promotion-quarantine.json`, `release/signing-identities.json`

`img/distroless-logo.svg` — referenced by `README.md`, not decorative-only.

`scripts/` (root level): `__init__.py`, `README.md`, `verify-image.sh`.

`scripts/certificates/` — mechanism, **with one caveat**:

- `certificados.sh`, `prepare_anchors.py` — the acquisition/verification
  mechanism; already parameterized by env vars
  (`CERTIFICADOS_BUCKET_CLOUDSEC`, `CERTIFICADOS_BUCKET_CACERTCORP`), no
  sandbox-specific values hardcoded
- `certificados.sha256`, `certificados.metadata.txt` — copy so the script has
  a lockfile to run against, but **regenerate both immediately against the
  real corporate CA buckets before the first corporate build**. Their current
  content pins a bundle whose certificates are explicitly labeled
  `Mock Test Fixture - NAO USAR EM PRODUCAO`; it is fixture data for the LAB,
  not a trustworthy corporate pin, even though the lockfile *mechanism*
  (pin + drift detection) is exactly what corporate should keep using

`scripts/pipeline/` — all 38 files (the five domains: `artifacts/`,
`catalog/`, `governance/`, `operations/`, `release/`, `runtime/`, plus
`__init__.py` files).

`docs/` (13 files):

- `README.md`, `repository-architecture.md`, `image-composition.md`
- `consumer-verification-contract.md`, `corporate-production-readiness.md`
- `iam-permission-contract.md`, `m11-m04-operational-health.md`
- `wolfi-signing-key.md`
- `adr/README.md`, `adr/0002-sigstore-trust-model.md`,
  `adr/0003-controles-seguranca-workflows-federados.md`,
  `adr/0004-v1-referencia-go126.md`,
  `adr/0005-stable-lifecycle-realinhamento-rfc013.md` (the currently-in-force
  ADRs only — ADR-0001/0006/0007 were removed as closed decisions; see
  `docs/adr/README.md`)

`tests/`:

- `__init__.py`, `README.md`
- `unit/` — all 41 files (mirrors `scripts/pipeline/` domains, no
  infrastructure dependency)
- `integration/` — all 14 files (certificates, TLS, adapters, shared
  workflow contract)
- `runtime/` — all 14 files: `README.md`, `certificate_contract.py`,
  `probe.cjs`, `probe.py`, `projects/dotnet/*` (4), `projects/go/*` (3),
  `projects/java/*` (3) — the functional-contract fixtures exercised against
  real candidate images; no dated evidence JSON remains in this tree

### Infrastructure (`alric-containers-registry`)

Root:

- `README.md`, `backend.tf`, `locals.tf`, `main.tf`, `outputs.tf`,
  `providers.tf`, `variables.tf`, `versions.tf`
- `.terraform.lock.hcl`, `.gitignore`

`.github/workflows/` — both: `terraform-apply.yml`, `terraform-pr.yml`.

`bootstrap/iam/` — `main.tf`, `outputs.tf`, `variables.tf`, `versions.tf`,
`README.md`, `.terraform.lock.hcl`. **Not** `terraform.tfstate` — see Do not
copy.

`iam/` — `README.md`, `policies/containers-registry-ecr-permanent.json`,
`policies/containers-registry-terraform-backend.json`,
`policies/containers-registry-trust.json`.

`policies/` — `ecr-lifecycle-7-days.json`, `ecr-repository-org-pull.json`.

`drift-remediation/` — `README.md`, `policy.json`. This is the generic,
reusable one-off mutability-drift mechanism (attach once, use once, detach);
the closed `dotnet8`/`dotnet8-dev` destroy episodes and their policy files
were removed as closed history — see `drift-remediation/README.md`.

`tests/` — all 5 files: `test_ecr_catalog.py`, `test_iam_policies.py`,
`test_lifecycle_policy.py`, `test_repository_policy.py`,
`test_terraform_workflows.py`.

### Shared execution (`alric-containers-reusable-workflows`)

Everything in this repository's final tree (16 files) is Copy — there is no
partial-copy case here:

- `README.md`, `renovate.json`, `.gitignore`
- `.github/CODEOWNERS`, `.github/dependabot.yml`,
  `.github/pull_request_template.md`
- `.github/workflows/ci.yml`, `.github/workflows/test-runtime-images.yml`,
  `.github/workflows/update-v1-tag.yml`,
  `.github/workflows/validate-apko-images.yml`
- `actions/setup-trivy/action.yml`
- `docs/apko-contract.md`, `docs/governance.md`
- `policies/main-protection.json`
- `scripts/check_contracts.py`, `tests/test_contracts.py`

## Do not copy

- `.git/` in all three repositories — the destination is populated by manual
  copy, not by cloning history.
- `alric-containers-registry/bootstrap/iam/terraform.tfstate` —
  **`EXCLUDE: bootstrap/iam/terraform.tfstate`**. Legitimate local LAB
  Terraform state, already gitignored and untracked; it describes sandbox
  AWS resources and must never reach the corporate destination.
- `troubleshooting/` — **moved to an independent operational troubleshooting
  image**, not part of this factory's product. It has been removed from
  `alric-containers-image-base` entirely (not relocated to another folder in
  this repository); its content is staged separately for a future,
  independent `alric-containers-troubleshooting` repository with its own
  lifecycle and security posture. Do not copy it into the corporate
  image-factory monorepo under any path.
- Any local Terraform working state or plan output: `.terraform/`,
  `*.tfstate`, `*.tfstate.*`, `*.tfplan`, `tfplan`, `crash*.log`,
  `*.tfbackend`, `override.tf*` — a manual copy does not respect
  `.gitignore`, so these must be excluded explicitly if present on disk in
  the sandbox checkout at copy time.
- Any local Python/tooling cache or environment: `__pycache__/`,
  `.pytest_cache/`, `.venv/`, `*.egg-info/`, `.DS_Store` — none of these are
  tracked, but the same manual-copy caveat applies.
- Any locally generated evidence, report, or build output not listed under
  Copy: `reports/`, generated `*.spdx.json` SBOMs, OCI layouts produced by
  `make build`/`make oci`, APK/Melange build outputs, and any private signing
  key material generated at build time. None of these exist as tracked files
  in the final tree; this entry exists so a manual copy of a working
  directory (rather than a clean checkout) does not sweep them in.
- Historical specs, process templates, and AI-development scaffolding
  (`specs/`, `prompts/`, `playbooks/`, `docs/ai/`, `docs/fundamentals/`,
  `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`,
  `.github/agents/`, `.github/aw/`, and their dedicated tests) — removed from
  all three repositories in this minimization as AI-assisted-development
  tooling and spec-driven-process artifacts, not product requirements. They
  do not exist in the final tree; nothing to exclude going forward unless
  reintroduced.
- Closed POC/decision documents and their proposal-only support files
  (`docs/corporate-adoption.md`, `docs/corporate-migration-manifest.md`,
  `docs/adr/0001-dotnet8-fora-do-lote-padrao.md`,
  `docs/adr/0006-java21-zlib-blocker-remediation-options.md`,
  `docs/adr/0007-multi-source-alpine-recusado.md`,
  `policies/aws/proposals/`, `policies/aws/corporate-like/`,
  `tools/render_iam_proposal.py`) — removed; their durable conclusions are
  consolidated in `RFC-013` and `docs/corporate-production-readiness.md`,
  with the original text preserved in sandbox Git history only.
