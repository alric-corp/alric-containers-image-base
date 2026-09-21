# Integração Corporativa da Factory Distroless — Modelo 2

## Objetivo

Este documento descreve o desenho recomendado para integrar o repositório corporativo de imagem base com o repositório corporativo de reusable workflows, preservando a separação arquitetural já adotada no LAB.

A decisão principal é:

> **Modelo 2 para Terraform:** o reusable/UP2 é responsável por bootstrap de `backend` e `provider`; o repositório `image-base` mantém apenas os recursos e módulos Terraform do produto.

Este documento deve ser usado como contexto técnico para a IA responsável pela adaptação corporativa.

---

# 1. Repositórios envolvidos

## Produto

```text
itau-xj7-container-image-base
```

Responsável por:

- catálogo de imagens;
- configurações Apko;
- configurações Melange;
- certificados e trust;
- políticas;
- scripts específicos do produto;
- testes;
- Terraform dos recursos;
- entrypoints de GitHub Actions;
- mapeamento de branch → ambiente;
- regras de promoção;
- release/promotion manifests;
- governança do produto.

Resumo:

```text
image-base = WHAT + WHEN + PRODUCT POLICY
```

## Reusable corporativo

```text
itau-xj7-reusable-workflows-containers-products
```

Responsável pela execução compartilhada:

- setup de ferramentas;
- execução de validação;
- execução de build;
- publicação;
- helpers genéricos;
- promoção entre ambientes;
- execução Terraform/UP2;
- mecanismos de verificação reutilizáveis.

Resumo:

```text
reusable = HOW / EXECUTION
```

---

# 2. Princípio de ownership

A regra principal da integração é:

> Um reusable workflow nunca deve depender silenciosamente de um arquivo, módulo, script ou política do caller.

Se conteúdo do consumidor for necessário, ele deve fazer parte de uma interface explícita e versionada.

Evitar:

```text
reusable chama:
scripts.pipeline.alguma_coisa

mas esse módulo "talvez exista" no caller
```

Preferir:

```text
caller passa:
environment
source-ref
catalog
policy-path
promotion-manifest
terraform-root

reusable executa:
mecânica genérica
```

---

# 3. Modelo de branches e ambientes

O modelo inicial corporativo é:

| Branch | Ambiente | Papel |
|---|---|---|
| `develop` | DEV | default branch, build e publicação |
| `staging` | HOM | promoção do mesmo digest, sem rebuild |
| `main` | PROD futuro | inicialmente fora do fluxo |

Não utilizar `release/*` como HOM no primeiro desenho.

Fluxo inicial:

```text
develop
  ↓
DEV
  ↓
build + candidate + stable DEV
  ↓
promoção por digest
  ↓
staging
  ↓
HOM stable
```

`main` fica reservada para uma futura produção real.

---

# 4. Stable por ambiente

Cada ambiente possui seu próprio `stable`.

Exemplo:

```text
DEV
image-base-go1-26:stable
→ sha256:AAA

HOM
image-base-go1-26:stable
→ sha256:AAA
```

Depois DEV pode avançar:

```text
DEV stable → sha256:BBB
HOM stable → sha256:AAA
```

Isso é esperado.

`stable` significa:

> versão aprovada naquele ambiente.

A identidade imutável continua sendo o digest.

---

# 5. Build only in DEV

Apenas DEV constrói.

```text
develop
  ↓
Melange
  ↓
Apko
  ↓
Trivy
  ↓
Trust
  ↓
Runtime Contract
  ↓
Publication Gate
  ↓
ECR DEV
  ↓
Cosign
  ↓
SBOM
  ↓
Provenance
  ↓
Candidate
  ↓
Soak
  ↓
DEV stable
```

HOM não deve executar novo build.

Nunca:

```text
staging
→ Apko
→ novo digest
```

Correto:

```text
DEV digest
→ promoção
→ HOM digest idêntico
```

---

# 6. Promoção DEV → HOM

A promoção deve trabalhar com uma release exata.

Não usar:

```text
latest
```

Não consultar apenas:

```text
"qual é o stable DEV agora?"
```

A promoção precisa estar vinculada a um manifesto.

Exemplo conceitual:

```json
{
  "schema_version": 1,
  "source_environment": "DEV",
  "target_environment": "HOM",
  "source_ref": "refs/heads/develop",
  "source_sha": "<sha>",
  "build_run_id": "<run-id>",
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
```

Esse documento pode ser chamado de:

```text
promotion-manifest.json
```

---

# 7. Promotion Manifest como contrato entre ambientes

O manifesto resolve uma race importante.

Exemplo:

```text
10:00 DEV stable = A
10:10 solicitação HOM criada para A
11:00 DEV stable = B
12:00 HOM aprova
```

HOM deve receber A, não B.

Por isso:

```text
promotion request
→ fixa os digests
→ aprovação
→ promoção dos mesmos digests
```

---

# 8. Runtime/dev pair

Para frameworks compilados:

```text
runtime
+
runtime-dev
```

formam uma release lógica.

Exemplos:

```text
go1-26 + go1-26-dev
java21 + java21-dev
dotnet10 + dotnet10-dev
```

Nunca promover:

```text
runtime do build A
+
dev do build B
```

O reusable pode implementar a mecânica de pair verification.

A policy que define quais pares são válidos pertence ao produto.

---

# 9. Interface esperada do reusable — build

O reusable de build deve receber inputs explícitos.

Exemplo conceitual:

```yaml
with:
  environment: DEV
  source-ref: refs/heads/develop
  aws-region: ...
  aws-role-arn: ...
  expected-account-id: ...
  frameworks: [...]
```

Responsabilidade do reusable:

```text
validate
→ build
→ scan
→ functional contracts
→ publish
→ attest
```

Responsabilidade do caller:

```text
quando chamar
qual ambiente
qual branch
qual catálogo
qual política
```

---

# 10. Interface esperada do reusable — promoção

O reusable de promoção deve receber:

```text
source environment
target environment
promotion manifest
expected source account
expected target account
signing policy
source ref
signer workflow
```

Ele não deve depender de módulos Python não declarados no caller.

Evitar:

```text
scripts.pipeline.operations.deployment
scripts.pipeline.release_promotion_source
```

sem contrato explícito.

Se esses módulos forem genéricos, movê-los para o reusable.

Se forem policy do produto, expor o resultado como input versionado.

---

# 11. verify_promotion — contrato alvo

O verificador atual do LAB não deve permanecer rigidamente preso a:

```text
refs/heads/main
```

ou a um único workflow antigo.

No corporativo, o build oficial vem de:

```text
refs/heads/develop
```

A interface precisa aceitar explicitamente:

```text
source-ref
signer-workflow
signer-ref
repository
digest
```

A mecânica de verificação pode ficar no reusable.

A policy de identidades confiáveis deve permanecer versionada no produto.

---

# 12. Terraform — Modelo 2

## Decisão

Adotar:

> **UP2/reusable gera e controla bootstrap de backend/provider.**

O `image-base` mantém somente os recursos Terraform do produto.

---

# 13. O que o image-base deve possuir em Terraform

Exemplo:

```text
infra/ecr/
├── main.tf
├── locals.tf
├── variables.tf
├── outputs.tf
├── policies/
└── tests/
```

Responsabilidades:

- ECR repositories;
- lifecycle;
- immutability;
- stable exclusion;
- repository policies;
- encryption;
- demais recursos do produto.

Evitar no root de recursos:

```text
backend.tf
providers.tf
```

se o core UP2 já os gera.

---

# 14. O que o reusable/UP2 deve possuir

Responsabilidade de execução:

```text
terraform init
terraform validate
terraform plan
terraform apply
```

Bootstrap:

```text
backend
provider
credentials
region
account
state configuration
```

O caller fornece:

```text
terraform-root
environment
account
region
variables
```

---

# 15. `.iupipes.yml`

O path não deve simplesmente ser trocado de:

```text
./infra
```

para:

```text
./infra/ecr
```

sem antes remover o ownership duplicado de backend/provider.

Fluxo correto:

```text
1. adaptar infra/ecr ao Modelo 2
2. remover backend/provider locais conflitantes
3. confirmar contrato UP2
4. só então configurar terraform-root = infra/ecr
```

---

# 16. Backend corporativo

Não reutilizar:

```text
terraform.tfstate
```

do LAB.

Não reutilizar:

```text
lab.tfvars
```

O ambiente corporativo deve criar estado novo.

Exemplo:

```text
DEV backend
HOM backend
PROD backend futuro
```

Chaves e buckets devem seguir convenção corporativa.

---

# 17. Separação IAM

Preservar fronteiras mesmo se os workflows estiverem no mesmo repo.

Conceitualmente:

```text
Infra Plan Role
Infra Apply Role
Build/Publication DEV Role
Promotion HOM Role
Read-only Consumer/App Certification Role
```

Não transformar uma única role em "super role" apenas para facilitar integração.

---

# 18. OIDC

Atualizar os contratos de trust para:

```text
organização corporativa
repository ID corporativo
owner ID corporativo
refs/heads/develop
GitHub Environments
workflows corporativos
```

Não copiar diretamente IDs/claims do LAB.

---

# 19. GitHub Environments

Inicialmente:

```text
DEV
HOM
```

Futuro:

```text
PROD
```

Cada ambiente pode conter:

```text
AWS_ROLE_ARN
AWS_REGION
EXPECTED_ACCOUNT_ID
reviewers
protection rules
```

---

# 20. Schedule

O schedule pertence ao caller.

Isso é:

```text
WHEN
```

Logo deve ficar no `image-base`.

Exemplo:

```yaml
on:
  schedule:
```

no entrypoint de DEV.

O reusable não precisa possuir trigger `schedule`.

Ele apenas executa a operação pedida.

---

# 21. Reusable pins

Antes da integração real:

```text
@0000000000000000000000000000000000000000
```

precisa desaparecer.

Sequência obrigatória:

```text
1. corrigir reusable
2. CI verde
3. merge
4. obter SHA real
5. consumir por SHA
```

Não utilizar branch móvel como pin operacional do primeiro E2E.

---

# 22. Private → Private

No ambiente corporativo, confirmar:

```text
image-base privado
→ reusable privado
```

com GitHub Actions access configurado.

Sem PAT estático.

O caller deve poder executar os reusables corporativos por configuração de Actions da organização/repositório.

---

# 23. Governance

Atualizar em conjunto:

```text
policies/governance/reusable-workflows.json
Dependabot
CODEOWNERS
signing-identities.json
OIDC policy
repository IDs
owner IDs
branch refs
workflow identities
```

Não trocar somente o `uses:`.

---

# 24. CODEOWNERS

O time pessoal não deve permanecer no repositório corporativo.

Confirmar:

```text
team corporativo
review obrigatório
acesso ao repo
branch protection
```

Antes do primeiro merge operacional.

---

# 25. Runner corporativo

O runtime oficial será Linux.

Target:

```text
GitHub Actions
→ self-hosted
→ Actions Runner Controller
→ Kubernetes
```

Validar previamente:

- Docker/BuildKit;
- QEMU;
- Melange;
- Apko;
- espaço em disco;
- artifacts grandes;
- permissões necessárias;
- arquitetura do node;
- network;
- timeouts;
- ephemeral runners.

Windows é somente experiência local opcional.

---

# 26. Fluxo de PR

PR:

```text
CI
+
validação
```

Sem publicação.

Sem credencial de escrita AWS.

Sem stable.

---

# 27. Fluxo DEV

```text
develop
  ↓
Infra DEV
  ↓
Build Factory
  ↓
candidate
  ↓
soak
  ↓
stable DEV
```

Primeiro E2E:

```text
go1-26
go1-26-dev
```

Não começar pelo catálogo inteiro.

---

# 28. Fluxo HOM

Depois do golden path DEV:

```text
promotion manifest
  ↓
staging
  ↓
Infra HOM
  ↓
verify source digest
  ↓
copy/promote without rebuild
  ↓
stable HOM
```

Requisito:

```text
DEV digest == HOM digest
```

---

# 29. main / PROD

No primeiro estágio:

```text
main = reservado
```

Sem fluxo operacional.

Depois, quando PROD for habilitado:

```text
staging
→ main
→ PROD promotion
```

---

# 30. Contrato de responsabilidades

| Capability | Target owner |
|---|---|
| Branch → environment | image-base |
| Catalog | image-base |
| Apko/Melange config | image-base |
| Certificates/trust policy | image-base |
| Build execution | reusable |
| Trivy setup | reusable |
| Runtime execution mechanics | reusable |
| Publication mechanics | reusable |
| Signing policy | image-base |
| Cosign verification mechanics | reusable |
| Promotion manifest | image-base |
| Promotion mechanics | reusable |
| Environment mapping | image-base |
| Schedule | image-base |
| Terraform resources | image-base |
| Terraform backend/provider bootstrap | reusable/UP2 |
| Terraform execution | reusable/UP2 |
| IAM resources/policies | image-base/Cloud ownership conforme contrato |
| Operational health policy | image-base |

---

# 31. Regra arquitetural para o reusable

O reusable deve ser:

```text
generic
explicit
versioned
fail-closed
```

Não deve conhecer detalhes implícitos do produto.

Inputs necessários devem ser documentados.

Outputs importantes também.

---

# 32. Regra arquitetural para o image-base

O produto deve conter:

```text
WHAT
WHEN
POLICY
```

e não duplicar mecânica genérica já oferecida pelo reusable.

---

# 33. Primeiro plano de implementação

## P0 — Reusable

- [ ] substituir zero SHAs;
- [ ] corrigir self-pins;
- [ ] CI verde;
- [ ] publicar SHA imutável;
- [ ] documentar inputs/outputs.

## P0 — Interface

- [ ] remover dependência silenciosa de módulos do caller;
- [ ] definir ownership de deployment;
- [ ] definir ownership de promotion source;
- [ ] atualizar verify_promotion;
- [ ] definir promotion manifest.

## P0 — Terraform Modelo 2

- [ ] confirmar contrato UP2;
- [ ] retirar backend/provider duplicados do root de recursos;
- [ ] apontar `.iupipes.yml` para root correto;
- [ ] criar backend corporativo novo;
- [ ] não importar state do LAB.

## P0 — Consumer

- [ ] trocar reusable pessoal por corporativo;
- [ ] atualizar governance;
- [ ] Dependabot;
- [ ] CODEOWNERS;
- [ ] signing identities;
- [ ] OIDC;
- [ ] remover caminhos legados de publicação.

## P0 — DEV

- [ ] `develop` default;
- [ ] GitHub Environment DEV;
- [ ] role DEV;
- [ ] runner ARC Linux;
- [ ] Terraform DEV;
- [ ] Go 1.26 golden path;
- [ ] candidate;
- [ ] stable DEV.

## P1 — HOM

- [ ] `staging`;
- [ ] GitHub Environment HOM;
- [ ] role HOM;
- [ ] Terraform HOM;
- [ ] promotion manifest;
- [ ] promotion sem rebuild;
- [ ] stable HOM;
- [ ] confirmar digest idêntico.

---

# 34. Primeiro critério de aceite

O primeiro E2E corporativo deve provar:

```text
develop
→ build go1-26/go1-26-dev
→ candidate DEV
→ Cosign
→ SBOM
→ provenance
→ runtime contract
→ stable DEV
```

Depois:

```text
DEV stable
→ promotion manifest
→ staging/HOM
→ same digest
→ stable HOM
```

Sem rebuild.

---

# 35. Não fazer

Não:

```text
trocar todos os `uses:` e testar
```

Não:

```text
apontar .iupipes.yml para infra/ecr sem resolver backend/provider
```

Não:

```text
copiar state LAB
```

Não:

```text
hardcodar develop/staging dentro de um reusable genérico sem necessidade
```

Não:

```text
rebuildar para HOM
```

Não:

```text
usar latest
```

Não:

```text
usar pin zero ou branch móvel como dependência final
```

---

# 36. Frase guia

> **O produto decide o que construir, quando executar e quais políticas aplicar; o reusable implementa como executar essas operações. Infra Terraform pertence ao produto, enquanto backend/provider bootstrap e execução Terraform pertencem ao core UP2/reusable.**

---

# 37. Estado alvo inicial

```text
DEFAULT_BRANCH = develop

DEV_BRANCH = develop
HOM_BRANCH = staging
PROD_BRANCH = main

PROD_ENABLED = false

BUILD_ENVIRONMENT = DEV

PROMOTION_ENVIRONMENTS =
- HOM

STABLE_PER_ENVIRONMENT =
- DEV
- HOM

TERRAFORM_MODEL = 2

TERRAFORM_RESOURCE_OWNER =
image-base

TERRAFORM_BACKEND_PROVIDER_OWNER =
UP2/reusable

BUILD_ONCE = true
PROMOTE_BY_DIGEST = true
REBUILD_ON_HOM = false
```
