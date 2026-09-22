THE REUSABLE OWNERSHIP CLEANUP IS APPROVED.

Proceed to the next corporate integration phase:

BRANCH MODEL + CORPORATE IDENTITY MIGRATION

Do NOT implement HOM promotion yet.

The immediate target is:

READY_FOR_DEV_E2E = YES

==================================================
1. LOCKED ARCHITECTURE
==================================================

Product:

itau-xj7-container-image-base

Default branch:
develop

DEV:
develop

HOM:
staging

Future PROD:
main

PROD_ENABLED = false

Factory Distroless remains product-owned.

Terraform Model 2 remains authoritative.

Promotion DEV -> HOM remains DEFERRED in this phase.

==================================================
2. OBJECTIVE
==================================================

Prepare the image-base repository for the first corporate DEV golden path.

Target:

develop
→ Infra DEV
→ Go 1.26 / Go 1.26-dev
→ build
→ validation
→ candidate
→ Cosign
→ SBOM
→ provenance
→ stable DEV

Do not implement staging/HOM promotion yet.

==================================================
3. FIRST — INVENTORY ALL MAIN-BOUND CONTRACTS
==================================================

Before editing, search the entire image-base repository for branch-sensitive
references.

At minimum classify every occurrence of:

refs/heads/main
branches: [main]
branch == main
github.ref comparisons
source-ref main
signer-ref main
OIDC subjects containing main
provenance checks containing main

Classify each occurrence as:

CHANGE_TO_DEVELOP
KEEP_MAIN_FUTURE_PROD
HISTORICAL
DOCUMENTATION_ONLY
NEEDS_DECISION

Do NOT perform global search/replace.

Return the inventory before edits internally, then implement only confirmed
current-runtime contracts.

==================================================
4. DEVELOP BECOMES DEV EXECUTION BRANCH
==================================================

Update the current Factory DEV execution path so that privileged build and
publication occur from:

refs/heads/develop

Review:

workflow.yml
build-base-images.yml
ci.yml
catalog-certification
app-certification
pipeline-health
infra-registry.yml
all branch guards
governance tests

Schedules belong to the product caller.

Do not add schedule support to reusable workflows.

==================================================
5. DEFAULT BRANCH ASSUMPTION
==================================================

The repository's intended default branch is:

develop

Check all scheduled workflows for assumptions about the default branch.

Do not claim schedule behavior is validated until the actual GitHub repository
default branch is changed/configured externally.

If changing the repository default branch is not possible from this task,
report it as:

EXTERNAL_CONFIGURATION_REQUIRED

==================================================
6. INFRA REGISTRY EXPECTED REF
==================================================

The reusable registry workflow now requires explicit:

expected-ref

For DEV, image-base must pass:

refs/heads/develop

Do not hardcode the branch policy back into reusable.

Caller owns:

DEV = develop

Reusable only enforces:

github.ref == expected-ref

==================================================
7. REMOVE LAB OIDC IDENTITY
==================================================

Inventory and replace LAB-specific trust information.

Current LAB residues may include:

alric-corp
712107929769
refs/heads/main
github-actions-image-base
LAB repository IDs
LAB owner IDs

Do NOT invent corporate values.

Use only values actually available in the corporate repository/environment.

For every missing corporate value, record:

EXTERNAL_INPUT_REQUIRED

Do not substitute placeholders into deployable IAM policy while pretending
they are valid.

==================================================
8. SIGNING IDENTITIES
==================================================

Update:

policies/release/signing-identities.json

or its current equivalent.

The trusted corporate build identity must reflect the actual:

corporate repository
corporate repository ID
corporate owner ID
source ref = refs/heads/develop
actual corporate signer workflow

Do not retain trust in alric-corp unless there is an explicitly documented
migration compatibility requirement.

==================================================
9. PROVENANCE VERIFICATION
==================================================

Review verify_promotion and all provenance verification logic.

For the DEV build produced by the corporate Factory, provenance must bind to:

source repository = corporate image-base
source ref = refs/heads/develop

Do not pretend that a DEV artifact was built from main.

Do not implement HOM behavior yet.

==================================================
10. GOVERNANCE POLICY
==================================================

Update:

policies/governance/reusable-workflows.json

Replace the personal reusable origin with:

itau-xj7-reusable-workflows-containers-products

using the approved immutable SHA after reusable PRs are merged.

No:

@main
@develop
@latest

No zero SHA.

==================================================
11. DEPENDABOT
==================================================

Update Dependabot/grouping references that still point to:

alric-corp/alric-containers-reusable-workflows

Use the corporate reusable repository.

Do not alter unrelated dependency strategy.

==================================================
12. CODEOWNERS
==================================================

Remove sandbox/personal ownership such as:

@alric-corp
@vigcf

only after the actual corporate team/user ownership is known.

Do not invent team names.

If the corporate CODEOWNERS target is not confirmed:

STOP that file
and report:

CODEOWNERS_CORPORATE_OWNER = EXTERNAL_INPUT_REQUIRED

Do not leave an invalid fabricated owner.

==================================================
13. TERRAFORM MODEL 2
==================================================

Preserve the already approved structure:

infra/ecr
→ resources only

Reusable / UP2:
→ backend/provider
→ init/plan/apply

infra-registry.yml must call the corporate reusable using an immutable SHA.

Expected DEV ref:

refs/heads/develop

Do not restore backend.tf/providers.tf/lab.tfvars/state.

==================================================
14. CORPORATE REUSABLE PIN
==================================================

After reusable PR #3/#4/#5 are merged, obtain the authoritative reusable main
SHA.

Update image-base consumers to that exact SHA.

Do not pin against a PR branch SHA that will not be the intended reviewed
integration revision unless explicitly approved.

Record:

CORPORATE_REUSABLE_SHA = <sha>

==================================================
15. ARC / LINUX EXECUTION
==================================================

Authoritative corporate CI runtime:

Linux self-hosted
Actions Runner Controller
Kubernetes

Inventory every:

runs-on:

Do not mechanically replace labels until the approved corporate ARC labels /
runner scale-set are known.

Where unknown:

ARC_LABELS = EXTERNAL_INPUT_REQUIRED

Do not add Windows CI.

==================================================
16. WINDOWS LOCAL FAILURES
==================================================

Windows-only local test failures are not a corporate blocker.

Do not spend this phase modifying production code to satisfy Git Bash unless
the same defect reproduces on Linux/ARC.

Corporate gate:

Linux/ARC.

==================================================
17. PROMOTION
==================================================

Do NOT connect:

promote-environment.yml

in this phase.

Do NOT copy:

scripts.pipeline.operations.deployment
scripts.pipeline.release.promotion_source

into image-base.

Promotion remains:

DEFERRED_FOR_HOM_PHASE

Current DEV stable logic inside image-base may remain where required for the
DEV golden path.

Cross-environment promotion is out of scope.

==================================================
18. CURRENT PROD
==================================================

Do not activate main.

Do not create a production deployment flow.

main remains:

FUTURE_PROD_RESERVED

==================================================
19. VALIDATION
==================================================

Run all possible offline/Linux-compatible repository checks.

Require:

image-base unit tests
integration tests
workflow hardening tests
Terraform contract tests
git diff --check
actionlint where available

For checks requiring:

AWS
UP2
ARC
GitHub repository settings
OIDC role

report:

REMOTE_E2E_PENDING

Do not fake PASS.

==================================================
20. SECURITY REVIEW
==================================================

Search for remaining sandbox values after migration.

At minimum:

alric-corp
712107929769
refs/heads/main
personal reusable repository name
personal CODEOWNERS
LAB role names
lab.tfvars
terraform.tfstate

Classify every remaining occurrence.

A historical document may legitimately retain old values.

An active execution/policy path may not.

==================================================
21. DO NOT MERGE
==================================================

Create focused PR(s).

Do not merge automatically.

Prefer separation such as:

PR A:
branch/default DEV execution model

PR B:
corporate identity/governance migration

unless their tests/contracts are too tightly coupled to separate safely.

==================================================
22. FINAL REPORT
==================================================

Return:

BRANCH_MODEL =
PASS / FAIL

DEV_REF =
refs/heads/develop

HOM_REF =
refs/heads/staging

MAIN_ACTIVE =
NO

DEFAULT_BRANCH_CHANGE_REQUIRED_EXTERNALLY =
YES / NO

INFRA_EXPECTED_REF =
refs/heads/develop

LAB_OIDC_REFERENCES_ACTIVE =
0 / OTHER

LAB_ACCOUNT_REFERENCES_ACTIVE =
0 / OTHER

LAB_REUSABLE_REFERENCES_ACTIVE =
0 / OTHER

CORPORATE_SIGNING_IDENTITY =
PASS / EXTERNAL_INPUT_REQUIRED / FAIL

CORPORATE_REUSABLE_SHA =
<sha / pending>

GOVERNANCE_POLICY =
PASS / FAIL

DEPENDABOT =
PASS / FAIL

CODEOWNERS =
PASS / EXTERNAL_INPUT_REQUIRED / FAIL

TERRAFORM_MODEL2 =
PRESERVED / BROKEN

ARC_LABELS =
CONFIGURED / EXTERNAL_INPUT_REQUIRED

WINDOWS_CI_ADDED =
NO

PROMOTION_INTEGRATION =
DEFERRED

IMAGE_BASE_TESTS =
PASS / FAIL

ACTIONLINT =
PASS / NOT_AVAILABLE / FAIL

REMOTE_E2E =
PENDING

READY_FOR_DEV_E2E =
YES / NO

READY_FOR_DEV_HOM_E2E =
NO

REMAINING_DEV_BLOCKERS =
<list>

PR =
<url(s)>

MERGE =
NOT_EXECUTED