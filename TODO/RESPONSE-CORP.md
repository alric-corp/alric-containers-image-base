PHASE A REVIEW IS APPROVED.

Proceed with the next implementation phase using the following rulings.

Do NOT reopen these architectural decisions.

==================================================
1. APPROVED OWNERSHIP
==================================================

Factory Distroless orchestration belongs to:

itau-xj7-container-image-base

Generic execution primitives belong to:

itau-xj7-reusable-workflows-containers-products

Terraform Model 2 remains authoritative:

Terraform resource definitions
→ image-base

backend/provider bootstrap + init/plan/apply
→ reusable / UP2

==================================================
2. APPROVED FACTORY DUPLICATE CLEANUP
==================================================

EXTERNAL_CONSUMERS = 0 was confirmed.

You are authorized to remove the Factory-specific duplicate implementation
from the reusable repository.

Target removal set:

_core-build-container.yml
duplicate build-base-images workflow
duplicate validate-base-images workflow
duplicate validate-apko-images workflow
duplicate test-runtime-images workflow
duplicate image-trust workflow

Also remove or adapt test_factory_workflows.py in the same change because its
contract is tied exclusively to the removed Factory copy.

Before deletion, take one final fresh dependency search.

If a new/unknown consumer is found:

STOP.

Otherwise proceed.

Do not modify the actual Factory implementation in image-base as part of this
cleanup.

==================================================
3. KEEP THESE REUSABLE COMPONENTS
==================================================

Keep:

registry.yml
_core-infra-terraform.yml
_source-control.yml
actions/setup-trivy
3-close-stale-issues.yml
test_registry_workflows.py

Preserve setup-trivy immutable pinning.

==================================================
4. DO NOT IMPLEMENT PROMOTION YET
==================================================

promote-environment.yml is NOT part of this implementation phase.

Current state is known invalid because it depends on undeclared caller
modules:

scripts.pipeline.operations.deployment
scripts.pipeline.release.promotion_source

Do NOT copy these missing modules into image-base.

Do NOT connect promote-environment.yml to image-base yet.

Target architecture for a later phase is:

image-base:
promotion policy + promotion manifest + trusted identities

reusable:
generic promotion mechanics

For now:

PROMOTION_INTEGRATION = DEFERRED

==================================================
5. REGISTRY BRANCH POLICY
==================================================

Do NOT replace:

hom → release/*

with another hardcoded product policy:

hom → staging

inside a supposedly generic reusable.

Branch-to-environment mapping belongs to image-base.

Refactor the generic Terraform reusable contract so the caller provides an
explicit expected ref/branch contract.

Conceptually:

environment
expected-ref

Reusable must fail closed when:

github.ref != expected-ref

Image-base will later pass:

DEV:
refs/heads/develop

HOM:
refs/heads/staging

Do not implement PROD use yet.

main remains reserved for future PROD.

==================================================
6. TERRAFORM MODEL 2
==================================================

Review the existing feature/terraform-model2 work.

Expected target:

infra/ecr contains Terraform resource definitions only.

No local backend/provider ownership that conflicts with UP2.

.iupipes.yml points to:

./infra/ecr

Do not import LAB state.

Do not use lab.tfvars.

Confirm the UP2 runtime-generated provider/backend behavior.

Require Terraform tests and plan validation to pass.

==================================================
7. REUSABLE VALIDATION
==================================================

After cleanup run the complete reusable test suite.

Update governance/tests only where required by the approved removal.

Require:

no dangling workflow references
no deleted workflow callers
no zero SHAs
no movable reusable pins
actionlint PASS
repository checks PASS

==================================================
8. DO NOT TOUCH IMAGE-BASE FACTORY BEHAVIOR
==================================================

During the reusable cleanup do NOT change:

framework catalog
Melange/Apko behavior
runtime contracts
image trust
publication gates
stable lifecycle
catalog certification
app certification
promotion implementation
recovery

This phase cleans ownership, not Factory behavior.

==================================================
9. DELIVERY
==================================================

Use focused commits.

Prefer separate PRs for:

A. reusable Factory duplicate cleanup
B. Terraform Model 2 / generic expected-ref contract

unless current branch structure already makes a single reviewed PR clearly
safer.

Do not merge automatically.

==================================================
10. FINAL REPORT
==================================================

Return:

FACTORY_DUPLICATES_REMOVED =
<list>

FACTORY_DUPLICATE_COUNT =

UNKNOWN_CONSUMERS_FOUND =
0 / OTHER

SETUP_TRIVY_PRESERVED =
YES / NO

TERRAFORM_CORE_PRESERVED =
YES / NO

SOURCE_CONTROL_CORE_PRESERVED =
YES / NO

REGISTRY_EXPECTED_REF_CONTRACT =
IMPLEMENTED / PENDING

HARDCODED_RELEASE_BRANCH_POLICY =
REMOVED / PRESENT

TERRAFORM_MODEL2 =
PASS / FAIL

PROMOTION_INTEGRATION =
DEFERRED

ZERO_SHA_REFERENCES =
0 / OTHER

MOVABLE_REUSABLE_PINS =
0 / OTHER

REUSABLE_TESTS =
PASS / FAIL

ACTIONLINT =
PASS / FAIL

IMAGE_BASE_FACTORY_CHANGED =
NO / YES

PR =
<url>

MERGE =
NOT_EXECUTED

READY_FOR_IMAGE_BASE_CORPORATE_INTEGRATION =
YES / NO