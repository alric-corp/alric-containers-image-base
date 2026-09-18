Quero implementar no ambiente corporativo a primeira fase da hardened-image factory que já foi validada no LAB pessoal.

IMPORTANTE:
NÃO quero reabrir arquitetura, POC ou redesign.
Quero portar/adaptar a implementação de referência para o ambiente corporativo e provar primeiro o golden path em DEV.

==================================================
CONTEXTO DA REFERÊNCIA VALIDADA
==================================================

A implementação de referência no LAB está fechada e validada.

Estado final:

REFERENCE_IMPLEMENTATION_READINESS = READY
LAB REFERENCE IMPLEMENTATION = CLOSED

ACTIVE CATALOG = 16

Wolfi-only
Melange + Apko
runtime / -dev
amd64 + arm64
build once
Trivy blocking gate
functional contracts
Cosign keyless
SPDX SBOM
provenance
candidate
stable
soak
promotion
recovery
Terraform-owned ECR
OIDC
preprovisioned-only publisher
Terraform no drift

Catálogo ativo:

dotnet10
dotnet10-dev

go1-25
go1-25-dev
go1-26
go1-26-dev

java21
java21-dev
java25
java25-dev

nodejs22
nodejs22-dev
nodejs24
nodejs24-dev

python3-13
python3-14

dotnet8:
REMOVED

Alpine/multi-source:
NOT ACTIVE

==================================================
CONTEXTO CORPORATIVO
==================================================

A implementação corporativa será em MONOREPO.

Não consigo fazer git clone dos repositories externos usados no LAB.
Vou copiar/adaptar os arquivos manualmente.

Portanto:
usar o LAB apenas como referência de mecanismos, contratos, testes e arquitetura.

NÃO copiar cegamente:
- account IDs
- repo IDs
- role names
- OIDC subjects
- bucket names
- org IDs
- URLs internas/externas do LAB
- CA paths
- runners
- backend Terraform
- environment names
- CODEOWNERS
- registry policies específicas
- tfstate
- evidência histórica

==================================================
ESTRATÉGIA DE AMBIENTES
==================================================

No corporativo:

develop
→ AWS DEV

release/**
→ hoje representa AWS HOM no fluxo corporativo tradicional

main
→ AWS PROD

Mas para ESTA factory, no primeiro momento quero simplificar.

FASE INICIAL:

default branch = develop

develop
→ AWS DEV

main
→ reservado para PROD, ainda não utilizado

HOM:
não implementar agora

Objetivo inicial:
provar apenas o ambiente DEV.

Motivo:
o schedule do GitHub Actions executa a partir da default branch.
Quero que o scheduled build rode inicialmente em develop e publique/valide somente em AWS DEV.

==================================================
REGRA DE ARTIFACT PROMOTION
==================================================

NÃO quero rebuild por ambiente.

Princípio obrigatório:

BUILD ONCE
PROMOTE MANY

Ou seja:

develop / DEV
→ constrói artifact
→ valida
→ publica candidate
→ assina
→ gera SBOM
→ gera provenance

Futuramente:

DEV
→ promote SAME OCI DIGEST
→ HOM

e depois:

HOM
→ promote SAME OCI DIGEST
→ PROD

NÃO fazer:

DEV = sha256:AAA
HOM = rebuild sha256:BBB

==================================================
GOLDEN PATH INICIAL
==================================================

Nesta primeira rodada corporativa, provar somente:

go1-26
go1-26-dev

Não expandir para as 16 definições ainda.

Golden path esperado:

1. build
2. amd64
3. arm64
4. Trivy
5. functional contract
6. ECR preflight
7. candidate publication
8. remote digest read-back
9. Cosign
10. SPDX SBOM
11. provenance
12. consumer verification
13. soak
14. stable promotion
15. stable verification
16. recovery
17. Terraform no drift

==================================================
ARQUITETURA DE MONOREPO
==================================================

Propor e implementar uma estrutura lógica equivalente a:

containers-image-factory/
├── infra/
│   ├── ecr/
│   └── iam/
├── factory/
│   ├── frameworks/
│   ├── distroless/
│   └── melange/
├── scripts/
├── policies/
├── tests/
├── docs/
└── .github/
    └── workflows/

Mesmo em monorepo, preservar boundaries:

Infra job
→ Infra role

Build/publish job
→ Containers role

Princípio:

Infra provides the destination.
Containers provides the trusted artifact.

==================================================
CERTIFICADOS CORPORATIVOS
==================================================

Fluxo esperado:

S3 corporativo
→ certificados.sh
→ validação de integridade / validade
→ prepare_anchors.py
→ Melange package
→ Apko composition
→ distroless runtime

Responsabilidades:

certificados.sh
= aquisição + validação de integridade

prepare_anchors.py
= normalização + validação CA

Melange
= empacotamento das CAs corporativas

Apko
= composição final da imagem e integração do trust store

Não instalar certificados em runtime.

==================================================
SCHEDULE
==================================================

Nesta fase:

default branch = develop

schedule de build:
executa em develop
→ AWS DEV

Não criar schedule separado para HOM.

Não criar build por branch de ambiente.

Não implementar ainda:

homolog
release/**
main/PROD deployment

Esses entram em fase posterior.

==================================================
SEMANTIC RELEASE
==================================================

O fluxo corporativo existente usa semantic release e release/**.

Para esta factory:

NÃO acoplar cada scheduled rebuild à criação de uma release branch.

Separar:

factory code version
!=
base image rebuild identity

Imagem deve manter identidade própria:

immutable build tag
OCI digest
stable

Semantic release pode continuar existindo para o código da factory se a governança corporativa exigir.

==================================================
ESCOPO DESTA RODADA
==================================================

Quero que você primeiro faça:

1. inventário do monorepo corporativo atual;
2. identifique convenções já existentes;
3. mapeie:
   - GitHub Actions
   - runners
   - branch protection
   - environments
   - OIDC
   - IAM
   - ECR
   - network/proxy
   - CA/certificados
   - Terraform backend
   - organization policies
4. compare com a referência do LAB;
5. proponha o menor port necessário para provar Go 1.26 em DEV;
6. implemente somente essa primeira fase.

==================================================
NÃO FAZER
==================================================

NÃO:

- ativar as 16 imagens;
- criar HOM;
- criar PROD;
- usar main para scheduled build;
- usar release/** para cada rebuild;
- reabrir Alpine;
- reabrir dotnet8;
- criar custom zlib;
- redesenhar supply chain;
- relaxar Trivy;
- publicar antes dos contratos;
- criar ECR no publisher;
- adicionar permissões IAM amplas;
- copiar IDs/nomes do LAB.

==================================================
PRIMEIRO OUTPUT QUE EU QUERO
==================================================

ANTES de implementar, me entregue:

## 1. Corporate Environment Inventory

O que existe hoje no monorepo.

## 2. Gaps vs Reference Implementation

Tabela:

| Capability | Corporate Current | Reference | Action |
|---|---|---|---|

## 3. Proposed DEV Architecture

Fluxo:

develop
→ schedule
→ build
→ scan
→ contracts
→ ECR DEV
→ sign/SBOM/provenance
→ stable

## 4. Files to Port/Create

Lista exata de arquivos/diretórios.

## 5. External Decisions Needed

Somente decisões realmente externas:
- IAM
- OIDC
- runner
- network
- CA
- backend
- GitHub policy

## 6. Risks

Somente riscos concretos.

## 7. Execution Plan

Pequeno, sequencial, com gates.

==================================================
IMPLEMENTATION RULE
==================================================

Só depois do inventário:

CONTEXT
→ SPEC
→ PLAN
→ IMPLEMENT
→ VERIFY
→ EVIDENCE

Não avançar para o próximo estágio se o gate anterior falhar.

==================================================
DEV ACCEPTANCE
==================================================

A fase DEV só fecha se:

DEVELOP_IS_DEFAULT_BRANCH = YES

SCHEDULE_RUNS_ON_DEVELOP = YES

AWS_ENVIRONMENT = DEV

GO126_BUILD = PASS
GO126_DEV_BUILD = PASS

AMD64 = PASS
ARM64 = PASS

TRIVY = PASS
FUNCTIONAL_CONTRACT = PASS

ECR_PREPROVISIONED_ONLY = PASS

CANDIDATE_PUBLISH = PASS
REMOTE_DIGEST_READBACK = PASS

COSIGN = PASS
SPDX_SBOM = PASS
PROVENANCE = PASS

CONSUMER_VERIFY = PASS

STABLE_PROMOTION = PASS
RECOVERY = PASS

TERRAFORM_DRIFT = NONE

SECURITY_GATE_RELAXED = NO

==================================================
FINAL DA PRIMEIRA FASE
==================================================

Esperado:

CORPORATE_DEV_GOLDEN_PATH = PASS

DEFAULT_BRANCH = develop

AWS_DEV = VALIDATED

GO126 / GO126_DEV = VALIDATED

BUILD_ONCE = PRESERVED

PROMOTE_SAME_DIGEST = PRESERVED

HOM = NOT_IMPLEMENTED
PROD = NOT_IMPLEMENTED

NEXT STEP =
DESIGN DEV → HOM PROMOTION WITHOUT REBUILD