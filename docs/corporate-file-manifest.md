# Corporate file manifest

Allowlist of what to copy **by hand** from the two active LAB repositories
into their two corporate counterparts. The greenfield rehearsal colocates
product and Infra in image-base and keeps shared execution in its own
repository. No `git clone` is used at the destination: copy the listed files
or directories from the reviewed working tree.

This manifest reflects the current product topology. Every
path under **Copy** exists in the corresponding repository today. Every path
under **Do not copy** either does not belong in the corporate destination or
must never leave the sandbox. If a path is not listed under Copy, treat it as
excluded by default — this manifest is the allowlist, not a starting point to
prune from.

Active sources and corporate destinations:

| LAB source | Corporate destination | Role |
| --- | --- | --- |
| `alric-corp/alric-containers-image-base` | `itau-xj7-container-image-base` | Product + its Infra |
| `alric-corp/alric-containers-reusable-workflows` | `itau-xj7-reusable-containers-products` | Shared execution (validation/runtime/Trivy) |

The factory stays at the image-base repository root: keep `frameworks/`,
`distroless/`, `melange/`, `scripts/`, and the root build files in place.
Place Infra under `infra/`; do not introduce a `factory/` relocation.
The superseded registry repository is not an active source for this copy.

## Copy

### Product + Infra (`alric-containers-image-base`)

Root:

- `README.md`, `RFC-013-Image-Base-Completa-com-Mermaid.md`, `CONTRIBUTING.md`
- `Makefile`, `requirements-dev.txt`, `renovate.json`
- `.editorconfig`, `.gitattributes`, `.gitignore`

`.github/`:

- `CODEOWNERS`, `dependabot.yml`, `pull_request_template.md`
- `workflows/` — `build-base-images.yml`, `ci.yml`, `image-trust.yml`,
  `infra-pr.yml`, `infra-apply.yml`,
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

`scripts/pipeline/` — the six domains: `artifacts/`,
`catalog/`, `governance/`, `operations/`, `release/`, `runtime/`, plus
`__init__.py` files.

`docs/`:

- `README.md`, `repository-architecture.md`, `image-composition.md`
- `consumer-verification-contract.md`, `corporate-production-readiness.md`
- `corporate-file-manifest.md`
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
- `unit/` — mirrors `scripts/pipeline/` domains, no
  infrastructure dependency
- `integration/` — certificates, TLS, adapters and product integration contracts
- `runtime/` — all 14 files: `README.md`, `certificate_contract.py`,
  `probe.cjs`, `probe.py`, `projects/dotnet/*` (4), `projects/go/*` (3),
  `projects/java/*` (3) — the functional-contract fixtures exercised against
  real candidate images; no dated evidence JSON remains in this tree

`infra/` — copy the product-owned Infra from this same repository:

- `README.md`, `.gitignore`, `backend.py`, `readback.py`
- `ecr/` — `backend.tf`, `locals.tf`, `main.tf`, `outputs.tf`,
  `providers.tf`, `variables.tf`, `versions.tf`, `.terraform.lock.hcl`,
  `verify_plan.py`, `policies/ecr-lifecycle-7-days.json`,
  `policies/ecr-repository-org-pull.json`, `tests/catalog.tftest.hcl`
- `iam/` — `README.md`, `.gitignore`, `main.tf`, `outputs.tf`,
  `variables.tf`, `versions.tf`, `.terraform.lock.hcl`,
  `build-publication-policy.json`, `tests/boundaries.tftest.hcl`
- `tests/` — `test_backend.py`, `test_ecr_catalog.py`, `test_ecr_plan.py`,
  `test_iam.py`, `test_readback.py`, `test_workflows.py`

The ECR root derives its catalog from the root `frameworks/` definitions.
Its backend is ensured by the pipeline before init and remains independent
of the ECR Terraform state. `infra/iam` is a separate bootstrap root; build
and Infra roles keep separate permissions and explicit OIDC subjects.

Before corporate execution, substitute the LAB account, repository/owner
IDs and subjects, backend identity, regions, environment, Source tags and
organization policy with the corporate values in code, workflows, reviewed
policy documents and their fixtures. In particular,
`build-publication-policy.json` is a LAB policy document to adapt, not a
corporate account grant ready to apply. Supply corporate IAM input values
separately; do not copy `infra/iam/lab.tfvars` as deployment configuration.
See `infra/README.md` and `infra/iam/README.md` for the bootstrap sequence.

Provision all 16 catalog repositories. Publication remains a separate
phase limited initially to `go1-26` and `go1-26-dev`; copying or applying
Infra does not authorize publishing the full catalog.

### Shared execution (`alric-containers-reusable-workflows`)

Copy the following shared-execution files into its separate corporate
repository:

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

- `.git/` in either source repository — the destination is populated by manual
  copy, not by cloning history.
- `alric-containers-registry/` — no active Terraform root, workflows, IAM
  bootstrap, state, or policies are copied from the superseded repository.
  Its retirement evidence stays in the LAB; archiving requires separate
  explicit approval.
- `drift-remediation/` — the legacy mechanism does not migrate, including
  its README and temporary-permission policy.
- `infra/iam/lab.tfvars` and any other LAB deployment inputs or credentials.
- `troubleshooting/` — **moved to an independent operational troubleshooting
  image**, not part of this factory's product. It has been removed from
  `alric-containers-image-base` entirely (not relocated to another folder in
  this repository); its content is staged separately for a future,
  independent `alric-containers-troubleshooting` repository with its own
  lifecycle and security posture. Do not copy it into the corporate
  corporate image-base repository under any path.
- Any local Terraform working state or plan output: `.terraform/`,
  `*.tfstate`, `*.tfstate.*`, `*.tfplan`, `tfplan`, `tfplan.bin`,
  `tfplan*.json`, `tfplan*.txt`, `plan.json`, `plan.txt`, `post-apply.*`,
  `crash*.log`, `*.tfbackend`, `override.tf*` — a manual copy does not respect
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
  the LAB repositories in the prior minimization as AI-assisted-development
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
