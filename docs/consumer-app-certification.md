# Consumer application certification

`Distroless - App certification` (`app-certification.yml`) is a manual,
read-only consumer of a successful full-catalog publication. Its required
`source-run-id` input selects one source run in this repository. It has no
default source run, framework override, tag override, or digest override.
An operator may dispatch it on `main` only after this workflow has been
reviewed and merged. Implementation tests do not dispatch certification.

The first intended source is publication run `35571871638`, attempt `1`,
revision `3b68b8b4613f91796ce18285263c9c6216a894eb`. This is an operational
example, not a default or special case in the resolver. The resolver derives
and validates the selected source's identity and fails on incomplete,
ambiguous, expired, mismatched, or unsuccessful publication evidence.

## Two distinct contracts

`Distroless - Runtime contract` remains the Factory's internal candidate
contract. It validates OCI artifacts, runtime/toolchain behavior, default
trust, security settings, and compiled runtime/dev binding before publication.
It is unchanged by app certification.

App certification builds downstream HTTP applications from the **published
ECR digest references**, then actually starts and probes their derived local
containers. It does not rerun the internal contract under a different name,
read `validated-oci-*` as a base image, or infer application success from an
index manifest. Candidate publication is sufficient: no stable tag needs to
exist. The intended lifecycle is candidate publication, app certification,
real soak, then separately authorized promotion.

## Fixed coverage

| Application | Build/preparation stage | Final runtime stage |
| --- | --- | --- |
| .NET 10 | `dotnet10-dev` | `dotnet10` |
| Go 1.25 | `go1-25-dev` | `go1-25` |
| Go 1.26 | `go1-26-dev` | `go1-26` |
| Java 21 | `java21-dev` | `java21` |
| Java 25 | `java25-dev` | `java25` |
| Node.js 22 | `nodejs22-dev` | `nodejs22` |
| Node.js 24 | `nodejs24-dev` | `nodejs24` |
| Python 3.13 | Not applicable | `python3-13` |
| Python 3.14 | Not applicable | `python3-14` |

These nine scenarios cover all sixteen catalog artifacts: seven dev images
perform real build/preparation work and nine runtime images execute the final
HTTP application. Each scenario executes separately on `linux/amd64` and
`linux/arm64`, giving eighteen results. Matrix `fail-fast: false` preserves
independent results when another scenario fails. Node's consumer build-stage
relationship does not change its independent release/promotion semantics.

The Linux hosted runner executes amd64 natively and arm64 through QEMU.
Evidence records native versus emulated execution. QEMU uses the repository's
reviewed action SHA and an explicit binfmt image digest maintained by
Renovate; the mutable action default is not used. The runner's Docker Buildx
installation is checked before resolving indexes or building applications.

## Source identity and consistency

The versioned inventory resolver validates the source GitHub run, attempt,
revision, complete publication artifacts, producer evidence, immutable build
tags, expected ECR repositories, and remote index/platform digests. All sixteen
members must resolve unambiguously; missing members never become a smaller
successful certification. The resulting `candidate-inventory.json` is the
only source of base references for application builds. This first version
accepts only source attempt 1 and rejects rerun sources: a run-ID-only input
must not silently select evidence from a later attempt.

Docker `FROM` references use the complete ECR repository plus `@sha256:...`.
Build tags are audit metadata, not consumer identities. Matrix jobs receive
the inventory from the current certification run with artifact digest
mismatches treated as errors. They never select a newest candidate.

The workflow uses its own concurrency namespace,
`app-certification-${repository}-${source_run_id}`, with
`cancel-in-progress: false`. It does not hold either the publisher or stable
mutation lock. Inventory resolution checks immutable tags against exact
digests; a concurrent new publication cannot replace those identities.
Subsequent application execution uses the resolved immutable digests and
therefore remains independent of new candidate publication. Removal or
unavailability of a required candidate fails certification rather than
falling back to another image.

## Build, HTTP, and runtime checks

Projects under `tests/consumer-apps/` use standard-library HTTP services for
Go, Java, Node, and Python, and the SDK-provided ASP.NET Core framework for
.NET. Builds run without a build-stage network. Node's deterministic local
package/lock exercises npm without registry dependencies; .NET restore uses
local SDK/framework assets without external feeds. No Go module proxy,
Maven/Gradle repository, npm registry, NuGet feed, or PyPI access is required.
Remote base-layer pulls remain necessary and are distinct from build-stage
network access.

The final stage is always the runtime image, never its dev companion. Derived
images stay on the runner and are not pushed. The host harness starts each
container without overriding the inherited runtime user and requires:

- A bounded readiness poll and HTTP 200 from `/health`, `/ready`, and `/info`.
- Semantic runtime family, expected version, and target architecture in JSON.
- Process UID/GID `10000:10000`, read-only root, all capabilities dropped, and
  `no-new-privileges` enabled.
- Explicit writable tmpfs at `/tmp` and `/app/work`.
- A bounded normal SIGTERM shutdown without a successful result from forced
  termination.

The final container has no extra shell, debugging tools, broad host mounts,
host network, host PID, or Docker socket. All HTTP polling and inspection run
from the host. Build time, readiness time, diagnostics, and shutdown outcome
are recorded even when an execution fails.

Java's JVM normally exits with status `143` after SIGTERM. It is accepted only
when the shutdown hook has stopped the HTTP server and workers and emitted
the completion marker. Other fixtures require exit `0`; exit `137`, an OOM
kill, or a missing completion marker fails graceful shutdown certification.

## AWS and GitHub permissions

Inventory and application jobs authenticate with GitHub OIDC; the summary
job does not receive AWS credentials. The current LAB exposes the existing
`AWS_ROLE_ARN`, `AWS_REGION`, and `AWS_ACCOUNT_ID` configuration but no
dedicated consumer ECR role. Each assumption restricts that role with an
inline **read-only session policy**. It allows `GetAuthorizationToken` and
only `DescribeImages`, `DescribeRepositories`, `BatchGetImage`,
`GetDownloadUrlForLayer`, and `BatchCheckLayerAvailability` for the account's
`image-base-*` repositories. The policy is an intersection with the existing
role permissions; it creates or widens no IAM resource.

The workflow does not perform ECR writes, move tags, publish derived images,
change promotion authorization, or run Terraform. No long-lived AWS secret
is introduced. A dedicated read-only consumer-certification role is the
preferred corporate target; provisioning that role belongs to a separately
reviewed infrastructure change.

## Evidence and acceptance

The inventory artifact contains `candidate-inventory.json`. Each matrix leg
preserves `<framework>-<architecture>.json` plus its diagnostic directory;
the summary artifact contains `summary.json`. Artifacts are retained for
thirty days. The GitHub Step Summary compares both architectures for every
application and makes build, runtime, HTTP, and security outcomes visible.
Missing or duplicate results fail the summary rather than reducing its
denominator. Artifact-download integrity failure also fails the summary job.

Results bind the source run/attempt/revision to runtime/dev references and
digests, platform, execution mode, build and startup timing, HTTP assertions,
UID/GID, filesystem/capability checks, and graceful shutdown. Authentication
tokens and credential files are never part of evidence.

Offline tests validate source binding, ambiguity rejection, scenario coverage,
workflow governance, digest references, and result semantics. They prove the
implementation's checks; only a later successful manual hosted run proves
the eighteen real consumer executions against the source candidates.
