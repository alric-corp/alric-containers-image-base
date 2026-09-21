RECONCILE AND IMPLEMENT THE CORPORATE INTEGRATION BETWEEN:

1. itau-xj7-container-image-base
2. itau-xj7-reusable-workflows-containers-products

Use deep/ultra reasoning.

IMPORTANT:

The architecture decisions below are ALREADY DECIDED.

Do not reopen them unless the current code proves that one of them is
technically impossible.

Do not start by changing YAML blindly.

First reconstruct the real dependency graph of both repositories.

Do not merge automatically.

==================================================
1. LOCKED ARCHITECTURE DECISION
==================================================

The final responsibility model is:

PRODUCT =
WHAT + WHEN + DOMAIN-SPECIFIC LOGIC + PRODUCT POLICY

REUSABLE =
GENERIC EXECUTION MECHANISMS SHARED ACROSS PRODUCTS

This is more precise than the previous:

PRODUCT = WHAT + WHEN
REUSABLE = HOW

Not every "HOW" belongs in reusable.

A HOW that only makes sense for the Distroless image-base Factory belongs
to the product.

==================================================
2. PRODUCT REPOSITORY
==================================================

Repository:

itau-xj7-container-image-base

The product owns:

- framework catalog;
- distroless composition;
- Apko configuration;
- Melange configuration;
- certificate/trust policy;
- image-base-specific scripts;
- runtime/dev relationships;
- compiled-pair semantics;
- runtime contracts;
- image trust planning;
- build orchestration;
- publication authorization rules;
- candidate/stable lifecycle policy;
- promotion manifest policy;
- quarantine policy;
- branch/environment mapping;
- schedules;
- product entrypoints;
- Terraform RESOURCE definitions;
- product governance;
- product tests.

The Factory Distroless implementation belongs here.

==================================================
3. REUSABLE REPOSITORY
==================================================

Repository:

itau-xj7-reusable-workflows-containers-products

The reusable repository should contain only mechanisms that another product
could consume without adopting Distroless Factory-specific concepts.

Examples of valid reusable responsibilities:

- Terraform execution;
- Terraform backend/provider bootstrap;
- generic AWS/OIDC setup;
- generic Trivy setup;
- generic QEMU/tool setup;
- generic OCI copy/promotion mechanics;
- generic Cosign verification primitives;
- generic environment-promotion mechanics;
- other primitives demonstrably reusable by multiple products.

A reusable should be:

GENERIC
EXPLICIT
VERSIONED
FAIL-CLOSED

==================================================
4. DECISION RULE
==================================================

For every workflow/action/helper, apply this test:

"Could another product that knows nothing about the Distroless image-base
catalog use this component without adopting image-base-specific rules?"

If YES:
candidate for reusable.

If NO:
belongs in image-base.

Examples:

terraform plan
→ YES
→ reusable

setup Trivy
→ YES
→ reusable

AWS OIDC setup
→ YES
→ reusable

Go runtime/dev pair binding
→ NO
→ image-base

certificate trust fixture planning
→ NO
→ image-base

catalog certification
→ NO
→ image-base

runtime_images publication contract
→ NO
→ image-base

==================================================
5. FACTORY BUILD OWNERSHIP — LOCKED
==================================================

The Factory build orchestration remains in:

itau-xj7-container-image-base

Keep product-owned workflows such as the equivalents of:

workflow.yml
build-base-images.yml
validate-base-images.yml
test-runtime-images.yml
image-trust.yml

when they encode image-base-specific Factory behavior.

The reusable repository must NOT contain a second copy of the Factory.

Do not migrate the image-base build orchestration into reusable.

==================================================
6. CURRENT DUPLICATED BUILD CODE IN REUSABLE
==================================================

The reusable repository currently contains candidates for duplicated
Factory-specific code, including equivalents of:

_core-build-container.yml
build-base-images
validate-base-images
test-runtime
image-trust
validate-apko

These are NOT automatically authorized for deletion yet.

First map their real consumers.

The expected target is:

remove Factory-specific duplication from reusable
while preserving truly generic primitives.

==================================================
7. REQUIRED FIRST PHASE — READ-ONLY INVENTORY
==================================================

Before deleting or editing anything, build an exact inventory.

For every build-related workflow/action/helper in reusable report:

FILE
TYPE
DIRECT CALLERS
INDIRECT CALLERS
TESTS DEPENDING ON IT
OTHER REPOSITORIES CONSUMING IT
IMAGE-BASE-SPECIFIC KNOWLEDGE
GENERIC CAPABILITY
TARGET_OWNER
RECOMMENDED_ACTION

Use classifications:

KEEP_REUSABLE
MOVE_TO_PRODUCT
REMOVE_DUPLICATE
NEEDS_DECISION

Example table:

| Component | Consumers | Factory-specific? | Generic primitive? | Target | Action |
|-----------|-----------|-------------------|--------------------|--------|--------|
| _core-build-container.yml | ... | YES | NO | image-base | REMOVE_DUPLICATE |
| setup-trivy/action.yml | ... | NO | YES | reusable | KEEP_REUSABLE |

Do not infer "no consumer" from filename alone.

Search:

- both local repositories;
- workflow `uses:`;
- composite actions;
- tests;
- governance policies;
- documentation/contracts;
- dependency manifests;
- any accessible organization/repository references if available.

==================================================
8. CLEANUP GATE
==================================================

Factory-specific duplicate build code may be removed from reusable ONLY if:

EXTERNAL_CONSUMERS = 0

or every remaining consumer has an explicit migration plan.

If an unknown consumer exists:

STOP deletion for that component.

Do not break an existing reusable API silently.

==================================================
9. TERRAFORM — MODEL 2 IS LOCKED
==================================================

Terraform Model 2 is selected.

Responsibility split:

IMAGE-BASE:
owns Terraform RESOURCE definitions.

REUSABLE / UP2:
owns Terraform execution and backend/provider bootstrap.

Therefore:

image-base:

infra/ecr/
→ resource definitions
→ locals
→ variables
→ outputs
→ policies
→ Terraform tests

reusable / UP2:

→ backend generation/bootstrap
→ provider generation/bootstrap
→ terraform init
→ terraform validate
→ terraform plan
→ terraform apply

Do NOT duplicate backend/provider ownership.

==================================================
10. TERRAFORM ROOT
==================================================

Current issue:

.iupipes.yml references:

./infra

while the ECR resource root is:

infra/ecr

Do NOT merely change:

./infra
→ ./infra/ecr

until ownership duplication has been resolved.

First inspect whether infra/ecr currently contains:

backend.tf
providers.tf

or equivalent definitions that UP2 already generates.

Target under Model 2:

image-base resource root must not fight UP2-generated backend/provider config.

Required sequence:

1. inspect UP2/action contract;
2. identify generated files;
3. remove/adjust duplicate backend/provider definitions;
4. validate Terraform tests;
5. set the correct terraform root;
6. run plan;
7. require NO unintended resources/drift.

==================================================
11. LAB STATE MUST NOT BE IMPORTED
==================================================

Do NOT use LAB:

terraform.tfstate
lab.tfvars
backend identifiers
AWS account IDs
role ARNs

as the corporate environment state.

Corporate DEV/HOM must get new state/configuration.

Do not copy Terraform state as migration strategy.

==================================================
12. TERRAFORM EXECUTION ENTRYPOINT
==================================================

The current model where image-base consumes something like:

infra-registry.yml
→ registry.yml@IMMUTABLE_SHA
→ _core-infra-terraform.yml

is architecturally valid if:

registry.yml is generic
and
Terraform resource policy remains in image-base.

Keep this general model.

==================================================
13. BUILD ENTRYPOINT
==================================================

The image-base product may continue:

workflow.yml
→ local build-base-images.yml

This is intentional.

Do NOT replace the local Factory call with `_core-build-container.yml`
merely for the sake of consuming reusable.

Reusable consumption is not a goal by itself.

Only generic mechanisms belong there.

==================================================
14. GENERIC BUILD PRIMITIVES
==================================================

Do NOT interpret "Factory stays in product" as:

"reusable can contain no build-related code."

Generic primitives may remain in reusable if they pass the reuse test.

Possible examples:

setup-trivy
setup-qemu
setup-apko
setup-melange
generic OCI copy
generic ECR login
generic Cosign verify

But only keep them if their current implementation is genuinely generic.

A composite/action that secretly assumes:

frameworks/
runtime_images.py
Melange CA contract
compiled pairs

is not generic.

==================================================
15. PROMOTION OWNERSHIP
==================================================

Promotion follows the same split.

IMAGE-BASE owns:

- environment policy;
- branch → environment mapping;
- promotion manifest schema/policy;
- allowed source;
- signing identities;
- compiled-pair policy;
- quarantine policy;
- when promotion occurs.

REUSABLE may own:

- generic manifest validation mechanics;
- generic source digest verification;
- generic Cosign/provenance verification;
- generic cross-environment OCI copy;
- target stable mutation;
- independent read-back;
- generic promotion locking.

==================================================
16. CURRENT PROMOTION CONTRACT DEFECT
==================================================

The reusable currently invokes modules such as:

scripts.pipeline.operations.deployment
scripts.pipeline.release_promotion_source

which are absent from the current image-base caller.

This is an invalid implicit contract.

Rule:

A reusable MUST NOT depend on undeclared caller modules.

Resolve this deliberately.

If the logic is generic:
move/implement it inside reusable.

If it is product policy:
have image-base produce/pass explicit versioned data.

Do not simply copy missing Python modules into image-base to make the
workflow green unless their ownership is genuinely product-specific.

==================================================
17. PROMOTION MANIFEST
==================================================

Use an explicit release/promotion manifest between environments.

Conceptually:

{
  "schema_version": 1,
  "source_environment": "DEV",
  "target_environment": "HOM",
  "source_ref": "refs/heads/develop",
  "source_sha": "...",
  "build_run_id": "...",
  "run_attempt": 1,
  "images": {
    "go1-26": {
      "digest": "sha256:..."
    },
    "go1-26-dev": {
      "digest": "sha256:..."
    }
  }
}

HOM must promote the exact approved release.

Do NOT select "latest".

Do NOT rebuild.

==================================================
18. VERIFY PROMOTION CONTRACT
==================================================

The current LAB verifier may still assume:

refs/heads/main

and a fixed signer workflow.

The corporate contract must support explicit trusted context such as:

source-ref
signer-workflow
signer-ref
repository
digest

The verification MECHANICS may be reusable.

The trusted identity POLICY belongs to image-base.

Do not fake an artifact as having been produced from `staging`.

A HOM promotion must verify the original DEV provenance.

==================================================
19. BRANCH / ENVIRONMENT MODEL — LOCKED
==================================================

Initial corporate model:

develop
→ DEV
→ DEFAULT BRANCH

staging
→ HOM

main
→ reserved for future real PROD

PROD_ENABLED = false

Do NOT introduce release/* as HOM.

==================================================
20. BUILD ENVIRONMENT
==================================================

Only DEV builds new base-image artifacts.

develop:

build
→ validate
→ publish candidate
→ supply-chain evidence
→ soak
→ stable DEV

HOM does not rebuild.

==================================================
21. STABLE PER ENVIRONMENT
==================================================

Each environment owns its own stable.

Example:

DEV:
image-base-go1-26:stable → digest A

HOM:
image-base-go1-26:stable → digest A

Later:

DEV stable → digest B
HOM stable → digest A

This is valid.

==================================================
22. DEV → HOM
==================================================

HOM must receive the SAME digest that was approved in DEV.

Required invariant:

DEV digest == HOM digest

No Apko/Melange rebuild in staging.

No package re-resolution.

No new OCI composition.

==================================================
23. SCHEDULE OWNERSHIP
==================================================

Schedule is:

WHEN

Therefore schedule belongs to image-base entrypoints.

The reusable does NOT need to support `schedule` as an event.

Example:

image-base workflow:

on:
  schedule:

then:

uses reusable operation

A workflow_call does not need to know whether its caller came from push,
manual dispatch or cron unless the operation contract explicitly requires it.

==================================================
24. REUSABLE IMMUTABLE PINS
==================================================

Current zero SHAs such as:

@0000000000000000000000000000000000000000

are P0 blockers.

Before consumer integration:

1. finish reusable implementation;
2. run reusable CI;
3. merge;
4. obtain real commit SHA;
5. use immutable SHA from image-base.

Do not use:

@main
@develop
@latest

as the final integration reference.

==================================================
25. PRIVATE TO PRIVATE
==================================================

Target repositories are private.

Require supported private-to-private GitHub Actions access.

Do not introduce PATs/static GitHub credentials merely to call reusables.

Use repository/organization Actions access controls.

==================================================
26. GOVERNANCE MIGRATION
==================================================

Do NOT update only `uses:`.

The integration includes:

policies/governance/reusable-workflows.json
Dependabot
CODEOWNERS
signing-identities
OIDC trust
repository IDs
owner IDs
branch refs
workflow identities
workflow hardening tests

Replace personal/sandbox ownership with confirmed corporate ownership.

==================================================
27. RUNNER TARGET
==================================================

Corporate authoritative execution target:

Linux
self-hosted
Actions Runner Controller
Kubernetes

Do NOT add Windows CI to fix local Windows failures.

Windows is optional local developer support.

Before first E2E validate ARC runner capabilities:

Docker
BuildKit
QEMU
Apko
Melange
disk
network
permissions
artifact sizes
timeouts

==================================================
28. WINDOWS TEST FAILURES
==================================================

Do not classify current Windows-only failures as a corporate release blocker
until they are reproduced on the authoritative Linux/ARC target.

Classify:

Linux/ARC failure
→ blocker

Windows-only local failure
→ optional developer-experience issue

==================================================
29. TARGET ARCHITECTURE
==================================================

Desired topology:

itau-xj7-container-image-base
│
├── .github/workflows/
│   ├── product entrypoints
│   ├── build-base-images.yml
│   ├── validate-base-images.yml
│   ├── test-runtime-images.yml
│   ├── image-trust.yml
│   └── infra-registry.yml
│
├── frameworks/
├── distroless/
├── melange/
├── scripts/
├── policies/
├── tests/
│
└── infra/ecr/
    └── Terraform resources
             │
             │ generic execution
             ▼
itau-xj7-reusable-workflows-containers-products
│
├── registry.yml
├── _core-infra-terraform.yml
├── promote-environment.yml
└── actions/
    └── generic reusable primitives

No duplicate Factory implementation in reusable.

==================================================
30. IMPLEMENTATION ORDER
==================================================

Follow this order.

PHASE A — INVENTORY, READ ONLY

Map duplicated build workflows and all consumers.

Deliver the component ownership matrix.

Do not delete yet.

PHASE B — REUSABLE P0

- replace zero SHAs;
- fix self-pins;
- remove implicit caller-module dependencies;
- define public reusable contracts;
- keep generic primitives;
- CI green;
- obtain immutable SHA.

PHASE C — TERRAFORM MODEL 2

- inspect UP2;
- resolve backend/provider ownership;
- adapt infra/ecr;
- set correct Terraform root;
- no LAB state;
- validate plan.

PHASE D — REMOVE FACTORY DUPLICATES

Only after consumer mapping proves safe:

- remove unused Factory-specific copies from reusable;
- update tests/contracts;
- preserve generic primitives.

PHASE E — IMAGE-BASE INTEGRATION

- point generic reusable dependencies to corporate SHA;
- update governance;
- update OIDC/signing identities;
- configure corporate owners;
- eliminate personal reusable references;
- preserve local Factory orchestration.

PHASE F — DEV E2E

Start only with:

go1-26
go1-26-dev

Prove:

develop
→ build
→ candidate DEV
→ runtime contract
→ Cosign
→ SBOM
→ provenance
→ stable DEV

PHASE G — HOM E2E

Prove:

DEV approved release
→ promotion manifest
→ staging/HOM
→ exact same digest
→ stable HOM

NO rebuild.

Only after this:
expand catalog.

==================================================
31. FIRST ACCEPTANCE TARGET
==================================================

Corporate Golden Path #1:

develop
→ go1-26/go1-26-dev
→ build
→ validation
→ publication
→ candidate DEV
→ supply-chain evidence
→ stable DEV

Corporate Golden Path #2:

stable/release DEV
→ promotion manifest
→ HOM
→ SAME digest
→ stable HOM

==================================================
32. DO NOT DO
==================================================

Do NOT:

- migrate Factory build orchestration into reusable;
- leave two copies of Factory code indefinitely;
- remove duplicate reusable build code before mapping consumers;
- fix `.iupipes.yml` path without resolving backend/provider ownership;
- import LAB terraform state;
- use zero SHAs;
- use movable refs as final reusable pins;
- use `latest`;
- rebuild in HOM;
- treat `main` as current PROD;
- introduce `release/*` as current HOM;
- copy missing caller modules only to satisfy an accidental reusable dependency;
- weaken security gates merely to complete integration.

==================================================
33. DELIVERABLE AFTER PHASE A
==================================================

Before implementation, return:

BUILD_COMPONENT_INVENTORY =
<table>

FACTORY_DUPLICATES =
<list>

GENERIC_PRIMITIVES =
<list>

UNKNOWN_CONSUMERS =
<list>

SAFE_TO_REMOVE =
<list>

KEEP_IN_REUSABLE =
<list>

KEEP_IN_IMAGE_BASE =
<list>

PROMOTION_IMPLICIT_DEPENDENCIES =
<list>

TERRAFORM_DUPLICATED_OWNERSHIP =
<list>

UP2_EXPECTED_CONTRACT =
<summary>

P0_BLOCKERS =
<list>

==================================================
34. STOP GATE
==================================================

After Phase A:

STOP.

Do not delete duplicated build workflows yet.

Present the findings and proposed exact file-by-file plan.

Wait for operator approval before Phase B/D cleanup.

==================================================
35. FINAL PRINCIPLE
==================================================

Use this as the architectural test for every decision:

PRODUCT =
WHAT
WHEN
DOMAIN-SPECIFIC LOGIC
PRODUCT POLICY

REUSABLE =
GENERIC EXECUTION MECHANISMS

Terraform:

RESOURCE DEFINITIONS
→ image-base

BACKEND / PROVIDER BOOTSTRAP
INIT / PLAN / APPLY
→ reusable / UP2

Factory:

DISTROLESS FACTORY ORCHESTRATION
→ image-base

GENERIC PRIMITIVES
→ reusable

Promotion:

PROMOTION POLICY / RELEASE IDENTITY
→ image-base

GENERIC PROMOTION MECHANICS
→ reusable