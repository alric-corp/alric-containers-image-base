# Marco 09 — Policy Controller: assinatura, SBOM, CVEs e Admission

> **Origem:** V6, seções **204–229**.
>
> O conteúdo abaixo foi preservado da V6; a divisão em marcos não altera o conteúdo técnico original.

---
# 204. V6: da evidência à decisão

Até a V5, construímos uma cadeia capaz de produzir e verificar:

```text
source
packages
image
SBOM
provenance
vulnerability metadata
signature
identity
```

A V6 adiciona a pergunta operacional mais importante:

> O que o cluster faz quando uma dessas garantias não existe ou não é válida?

Sem enforcement, podemos ter:

```text
SBOM          ✓
Signature     ✓
Provenance    ✓
Policy        documented
Deploy        still allowed
```

Com admission control:

```text
Deploy request
      │
      ▼
Verify evidence
      │
      ▼
Evaluate policy
      │
   ┌──┴──┐
   │     │
 PASS   FAIL
   │     │
   ▼     ▼
ADMIT   DENY
```

Esse é o papel central do **Sigstore Policy Controller**.

---
# 205. Policy Controller como ponto de enforcement

O Sigstore Policy Controller é um admission controller para Kubernetes.

Seu papel é avaliar workloads **antes** de serem admitidos.

Ele pode usar informações como:

```text
image digest
signature
signer identity
attestations
OCI image config
Kubernetes object metadata
Kubernetes object spec
```

e produzir uma decisão:

```text
ALLOW
WARN
DENY
```

A arquitetura passa a ser:

```text
CI/CD
  │
  ▼
Build
  │
  ├── SBOM
  ├── vulnerability report
  ├── provenance
  └── signature
        │
        ▼
     Registry
        │
        ▼
Kubernetes API request
        │
        ▼
Sigstore Policy Controller
        │
        ├── verify identity
        ├── verify signature
        ├── verify attestation
        ├── evaluate CUE/Rego
        └── inspect workload spec
                │
             ┌──┴──┐
             │     │
           PASS   FAIL
             │     │
             ▼     ▼
           ADMIT  DENY
```

---
# 206. O ponto-chave: evidence não é enforcement

É importante separar:

## Evidence

```text
"This image has an SBOM."
"This image was signed."
"This build has provenance."
"This scanner produced this vulnerability report."
```

de:

## Enforcement

```text
"Images without an SBOM cannot enter production."
"Only the trusted release workflow can sign production images."
"Images with disallowed vulnerabilities are rejected."
```

Assim:

```text
Metadata
   +
Verification
   +
Policy
   =
Enforceable Trust
```

---
# 207. Namespace opt-in

O Policy Controller normalmente aplica validação apenas nos namespaces inscritos no enforcement.

Exemplo:

```bash
kubectl label namespace production policy.sigstore.dev/include=true
```

Modelo:

```text
Namespace
   │
   ├── policy.sigstore.dev/include=true
   │        │
   │        ▼
   │   policy enforcement
   │
   └── no label
            │
            ▼
      outside this enforcement scope
```

Esse mecanismo permite adoção gradual.

---
# 208. Rollout gradual de policy enforcement

Uma estratégia segura de adoção é:

```text
Phase 1
observe

Phase 2
warn

Phase 3
enforce

Phase 4
tighten policies
```

Evite começar diretamente com:

```text
glob: "**"
+
strict deny
+
production
```

sem conhecer o inventário real de workloads.

---
# 209. `ClusterImagePolicy`

O recurso central é:

```yaml
apiVersion: policy.sigstore.dev/v1beta1
kind: ClusterImagePolicy
```

Uma policy pode definir:

```text
which images match
which authorities are trusted
which attestations are required
which policy language evaluates metadata
whether violations warn or block
which Kubernetes resource types are evaluated
```

---
# 210. Matching por imagem

Exemplo:

```yaml
spec:
  images:
    - glob: "cgr.dev/chainguard/**"
```

Ou:

```yaml
spec:
  images:
    - glob: "**"
```

O primeiro restringe o escopo.

O segundo é global.

Em produção, prefira escopos intencionais e previsíveis.

---
# 211. Tags são resolvidas para digests

Uma propriedade importante do Policy Controller é resolver referências de imagem para conteúdo identificável.

Conceitualmente:

```text
nginx:latest
    │
    ▼
resolve
    │
    ▼
nginx@sha256:...
```

A decisão de admission deve estar vinculada ao artefato efetivamente verificado.

Isso reduz o risco clássico:

```text
verify tag
      │
tag moves
      │
run different bytes
```

---
# 212. Múltiplas policies formam AND

Quando várias `ClusterImagePolicy` correspondem a uma imagem, a lógica de admission é conceitualmente:

```text
Policy A
AND
Policy B
AND
Policy C
```

Exemplo:

```text
signed by trusted workflow
AND
has SBOM
AND
has provenance
AND
meets vulnerability policy
```

Todas precisam ser satisfeitas.

---
# 213. Múltiplas authorities formam OR

Dentro de uma policy, múltiplas authorities representam alternativas aceitas:

```text
Authority A
OR
Authority B
OR
Authority C
```

Exemplo:

```text
release workflow A
OR
release workflow B
```

Isso permite rotação ou múltiplos builders sem duplicar a policy inteira.

---
# 214. Verificar assinatura não é apenas procurar uma assinatura

Uma policy madura precisa responder:

```text
Is it signed?
```

mas também:

```text
Who signed it?
Which OIDC issuer?
Which workflow?
Which repository?
Which ref?
```

Então:

```text
signature existence
      ≠
trusted signature
```

---
# 215. Policy de assinatura keyless

Exemplo conceitual:

```yaml
apiVersion: policy.sigstore.dev/v1beta1
kind: ClusterImagePolicy
metadata:
  name: trusted-release-signer
spec:
  images:
    - glob: "registry.example.com/**"
  authorities:
    - keyless:
        identities:
          - issuer: "https://token.actions.githubusercontent.com"
            subject: "https://github.com/example/platform/.github/workflows/release.yaml@refs/heads/main"
```

A confiança está vinculada à identidade do workload de release.

---
# 216. Signer identity é parte da policy de produção

Uma organização pode ter vários workflows:

```text
PR validation
nightly
development
release
production release
```

Nem todos deveriam possuir a mesma authority.

Exemplo:

```text
dev image
→ dev workflow accepted

prod image
→ only production release workflow accepted
```

Assim:

```text
environment
+
artifact identity
+
signer identity
```

podem ser correlacionados.

---
# 217. Enforcing SBOM attestation

Uma das policies mais interessantes exige que a imagem tenha uma attestation do tipo SPDX.

Fluxo:

```text
Image
  │
  ├── signature
  └── SBOM attestation
          │
          ▼
Policy Controller
          │
          ├── attestation exists?
          ├── expected predicate type?
          ├── trusted signer?
          └── policy passes?
                  │
               ┌──┴──┐
               │     │
              yes    no
               │     │
               ▼     ▼
             ADMIT  DENY
```

---
# 218. SBOM existente não significa SBOM confiável

Uma policy que valida somente:

```text
predicateType == SPDX
```

prova muito pouco sozinha.

Precisamos também considerar:

```text
Who created the SBOM?
Who signed the attestation?
Is the attestation bound to this digest?
Is the signer trusted?
```

Portanto:

```text
SBOM presence
      <
trusted SBOM attestation
```

---
# 219. SBOM attestation policy

Exemplo conceitual:

```yaml
authorities:
  - name: trusted-builder
    keyless:
      identities:
        - issuer: "https://token.actions.githubusercontent.com"
          subject: "https://github.com/example/repo/.github/workflows/release.yaml@refs/heads/main"
    attestations:
      - name: sbom-required
        predicateType: https://spdx.dev/Document
```

Aqui estamos dizendo:

```text
trusted signer
AND
expected attestation type
```

---
# 220. Predicate type

Attestations possuem tipos.

Exemplos conceituais:

```text
SPDX SBOM
SLSA provenance
vulnerability report
custom compliance statement
```

Uma policy deve declarar exatamente o tipo esperado.

Isso reduz ambiguity.

---
# 221. Vulnerability attestation

Outra possibilidade é produzir um scan, transformar o resultado em attestation e avaliá-lo no admission.

Fluxo:

```text
Image
  │
  ▼
Scanner
  │
  ▼
Vulnerability Report
  │
  ▼
Signed Attestation
  │
  ▼
Registry
  │
  ▼
Policy Controller
```

A policy pode perguntar:

```text
HIGH == 0?
CRITICAL == 0?
```

---
# 222. Scanner result também precisa de trust

Uma vulnerability attestation não deve ser tratada como verdade apenas porque existe.

Perguntas necessárias:

```text
Who ran the scanner?
Which scanner?
Which version?
Which vulnerability database?
When was the scan produced?
Which image digest was scanned?
```

Assim:

```text
signed scanner output
```

é muito mais útil que:

```text
unsigned JSON uploaded somewhere
```

---
# 223. Vulnerability attestation é snapshot

Uma limitação fundamental:

```text
scan at T0
```

não garante:

```text
still vulnerability-free at T1
```

porque novas CVEs aparecem continuamente.

Portanto uma policy baseada em scan deveria considerar também:

```text
attestation freshness
rescan cadence
database freshness
rebuild cadence
```

---
# 224. CVSS threshold não deve ser a única decisão

Uma policy simplista:

```text
deny if HIGH or CRITICAL
```

é útil como exemplo.

Mas em produção, decisões podem precisar considerar:

```text
CVSS
exploitability
EPSS
known exploitation
runtime reachability
VEX
package context
business exception
fix availability
```

Logo:

```text
severity-only policy
```

é uma base, não o modelo final.

---
# 225. VEX + vulnerability policy

Um modelo mais maduro:

```text
Scanner
   │
   ▼
Vulnerability findings
   │
   ├── exploitable
   ├── not affected
   ├── fixed
   └── investigation
        │
        ▼
       VEX
        │
        ▼
Admission decision
```

Isso reduz bloqueios inúteis por CVEs presentes mas não exploráveis.

---
# 226. Maximum image age

Também podemos impor:

```text
maximum image age
```

Exemplo:

```text
image older than 30 days
        │
        ▼
DENY
```

Objetivo:

```text
force freshness
```

---
# 227. Image age não é sinônimo de segurança

Uma imagem:

```text
1 day old
```

pode ter vulnerabilidades.

Uma imagem:

```text
45 days old
```

pode ainda estar segura.

Então maximum age é um controle indireto.

Ele incentiva:

```text
regular rebuild
fresh dependency resolution
fresh security metadata
```

mas não substitui scanning.

---
# 228. Reproducible builds e `created`

Existe uma nuance importante.

Builds reproduzíveis podem usar timestamps fixos, inclusive:

```text
Unix epoch
```

Uma policy baseada em:

```text
OCI config.created
```

poderia interpretar incorretamente a imagem como extremamente antiga.

Uma alternativa é usar:

```text
SOURCE_DATE_EPOCH
```

alinhado ao commit ou ao source state relevante.

---
# 229. Freshness policy deve usar evidência adequada

Idealmente, freshness não deveria depender de um único campo.

Podemos considerar:

```text
build timestamp
source commit timestamp
provenance timestamp
attestation timestamp
package update state
base image freshness
```

A policy de `created` é útil, mas simplificada.

---
