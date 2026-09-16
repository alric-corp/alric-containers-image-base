# Marco 08 — Cosign, Sigstore, Fulcio/Rekor, bootstrap trust e Air-gap

> **Origem:** V6, seções **168–203**.
>
> O conteúdo abaixo foi preservado da V6; a divisão em marcos não altera o conteúdo técnico original.

---
# 168. Cosign assina mais do que imagens

Cosign pode ser utilizado com:

```text
container images
SBOMs
blobs
files
Helm charts
other OCI-distributed artifacts
```

---
# 169. Keyless signing como abordagem moderna

```text
Workload
   │
   ▼
OIDC identity
   │
   ▼
Fulcio
   │
   ▼
short-lived certificate
   │
   ▼
Cosign signature
   │
   ▼
Transparency record
```

A vantagem principal é reduzir a dependência de uma signing key permanente.

---
# 170. Signing key rotation vs ephemeral identity

Modelo clássico:

```text
private key
  │
  ├── protect
  ├── rotate
  ├── revoke
  └── audit
```

Modelo keyless:

```text
OIDC identity
      │
      ▼
ephemeral key/certificate
      │
      ▼
sign
      │
      ▼
expire
```

---
# 171. Fulcio e Rekor têm papéis diferentes

## Fulcio

Emite certificado baseado em identidade OIDC.

```text
Who is signing?
```

## Rekor

Mantém transparency information para os eventos de assinatura.

## Cosign

Orquestra assinatura e verificação dos artefatos.

---
# 172. Verification precisa validar identidade

Verificar apenas que existe uma assinatura não é suficiente.

Precisamos validar:

```text
expected OIDC issuer
+
expected signer identity
+
expected artifact digest
```

---
# 173. Workflow identity como signer

Em CI, a identidade pode representar:

```text
repository
workflow path
branch/ref
```

Isso permite políticas como:

```text
ALLOW image
IF signer == trusted release workflow on main
```

---
# 174. Sign by digest, not by tag

```text
image@sha256:...
```

é a identidade preferível do artefato para signing e attestation.

```text
tag
→ mutable pointer

digest
→ immutable content identity
```

---
# 175. SBOM attestation

Podemos representar:

```text
Subject:
image@sha256:...

Predicate:
SPDX SBOM

Signer:
OIDC identity
```

O resultado é uma afirmação verificável sobre o conteúdo de um digest específico.

---
# 176. in-toto attestation

O modelo de attestation pode ser representado como:

```text
subject
+
predicate type
+
predicate
+
signature
```

Isso permite expressar:

```text
SBOM
SLSA provenance
VEX
custom policy metadata
```

---
# 177. Blob signing

Supply chain não termina em OCI images.

Podemos assinar:

```text
release binary
script
configuration
README
policy bundle
installer
```

---
# 178. Release binary verification

A documentação demonstra verificar releases do próprio apko com:

```text
release file
+
signature
+
certificate
+
expected OIDC issuer
+
expected workflow identity
```

Esse é um padrão importante para bootstrap trust.

---
# 179. Bootstrap trust

Existe um problema clássico:

```text
Who verifies the verifier?
```

Uma estratégia:

```text
download apko
    │
    ▼
verify apko signature
    │
    ▼
use apko to build
```

O mesmo raciocínio vale para outras ferramentas críticas da toolchain.

---
# 180. Air-gapped verification

Keyless verification também pode ser realizada em ambientes desconectados quando o material necessário é levado para dentro do ambiente.

Precisamos preservar:

```text
artifact
signatures/attestations
Sigstore trusted root
```

---
# 181. O que precisa atravessar o air gap

```text
Connected side
    │
    ├── image
    ├── signatures
    ├── attestations
    └── trusted_root.json
            │
            ▼
       controlled transfer
            │
            ▼
Air-gapped side
```

---
# 182. Não copie só a imagem

Uma falha operacional importante:

```text
copy image
```

pode não copiar automaticamente:

```text
signature
attestation
```

Resultado:

```text
image present
+
metadata absent
```

---
# 183. cosign tree como inspeção

Antes de mover um artefato, é útil visualizar:

```text
image
├── signatures
└── attestations
```

Isso ajuda a confirmar o conjunto que precisa ser preservado.

---
# 184. Offline transparency verification

A documentação atual mostra que não é necessário simplesmente desabilitar transparency-log verification em air-gap.

Com material suficiente, como trusted root e evidência assinada, parte importante da verificação pode continuar offline.

---
# 185. Trust root também tem lifecycle

Não basta copiar:

```text
trusted_root.json
```

uma vez e esquecer.

Autoridades e chaves podem ser rotacionadas.

Portanto:

```text
trust root freshness
```

também precisa ser administrada.

---
# 186. Air-gap cria um novo supply chain boundary

```text
External Trust Domain
       │
       ▼
Verify
       │
       ▼
Controlled Transfer
       │
       ▼
Internal Trust Domain
       │
       ▼
Verify Again
```

---
# 187. Re-signing é decisão de trust domain

Algumas organizações verificam a assinatura externa e reassinam internamente.

Isso não é uma obrigação técnica.

É uma escolha entre:

```text
Trust vendor identity directly
```

e:

```text
Trust internal import process
```

---
# 188. Wolfi-base vs distroless runtime

`wolfi-base` não é necessariamente distroless.

Pode conter:

```text
apk
shell
```

Ele funciona bem como builder, ambiente interativo ou custom base.

Já uma imagem runtime distroless busca remover ferramentas não necessárias à execução.

---
# 189. Wolfi pode ser usado com Dockerfile

```text
Wolfi
    ≠
apko mandatory
```

É possível usar:

```dockerfile
FROM cgr.dev/chainguard/wolfi-base
```

em um Dockerfile tradicional.

Isso permite adoção incremental.

---
# 190. Caminho de maturidade incremental

```text
Traditional Dockerfile
        │
        ▼
Wolfi builder/base
        │
        ▼
Multi-stage
        │
        ▼
Distroless runtime
        │
        ▼
Melange package
        │
        ▼
apko composition
        │
        ▼
SBOM + signing + provenance
        │
        ▼
OIDC + no long-lived credentials
        │
        ▼
Policy enforcement
```

---
# 191. Supply chain maturity não é uma ferramenta

Nenhuma ferramenta isolada resolve tudo.

```text
Wolfi
→ package foundation

Melange
→ package build

apko
→ image composition

Renovate
→ freshness automation

Octo STS
→ short-lived GitHub credentials

Cosign
→ signing/verification

Fulcio
→ identity-backed certificates

Rekor
→ transparency

SBOM
→ inventory

VEX
→ exploitability context

Policy / Admission
→ enforcement
```

---
# 192. OIDC como eixo central da V5

OIDC aparece em vários pontos:

```text
GitHub Actions
    │
    ├── Octo STS
    │      └── short-lived GitHub token
    │
    ├── Sigstore/Fulcio
    │      └── signing certificate
    │
    └── Cloud federation
           └── cloud credentials
```

Princípio arquitetural:

> Workload identity should replace long-lived machine secrets wherever practical.

---
# 193. Secrets minimization

Nova métrica para o pipeline:

```text
How many long-lived secrets does this pipeline require?
```

Avalie:

```text
PATs
registry passwords
cloud access keys
signing keys
SSH keys
API tokens
```

Para cada um:

```text
Can this become OIDC federation?
```

---
# 194. Pipeline V5 sem credenciais estáticas

```text
GitHub Actions
      │
      ├── OIDC → Octo STS → GitHub API
      │
      ├── OIDC → Cloud STS → Cloud API
      │
      ├── OIDC → Registry identity
      │
      └── OIDC → Fulcio/Cosign → Signing
                │
                ▼
             Build
                │
                ▼
            Artifact
```

---
# 195. Pipeline V5 consolidado

```text
                       SOURCE
                         │
                         ▼
                  GITHUB WORKFLOW
                         │
               ┌─────────┼─────────┐
               │         │         │
               ▼         ▼         ▼
             OIDC      OIDC      OIDC
               │         │         │
               ▼         ▼         ▼
          Octo STS   Cloud STS   Fulcio
               │         │         │
               ▼         ▼         ▼
        GitHub Token  Cloud Cred  Signing ID
               │         │         │
               └─────────┼─────────┘
                         ▼
                   TRUSTED BUILD
                         │
                         ▼
                      MELANGE
                         │
                         ▼
                   SIGNED APK
                         │
                         ▼
               TRUSTED APK REPOSITORY
                         │
                         ▼
                       APKO
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
          OCI IMAGE     SBOM    RESOLVED CONFIG
              │          │          │
              └──────────┼──────────┘
                         ▼
                       SCAN
                         │
                         ▼
                        VEX
                         │
                         ▼
                    PROVENANCE
                         │
                         ▼
                       COSIGN
                         │
                         ▼
                       REKOR
                         │
                         ▼
                     REGISTRY
                         │
                         ▼
                  POLICY / ADMISSION
                         │
                         ▼
                      RUNTIME
                         │
                         ▼
                RENOVATE / REBUILD
                         │
                         └───────────────┐
                                         ▼
                                   NEXT VERSION
```

---
# 196. Checklist V5 — Identity

```text
[ ] CI usa OIDC quando disponível
[ ] PATs foram eliminados quando possível
[ ] Tokens são short-lived
[ ] Trust policies estão versionadas
[ ] Subject é exato quando possível
[ ] IDs imutáveis são usados quando disponíveis
[ ] Permissões seguem least privilege
[ ] Cada automação possui identidade própria
```

---
# 197. Checklist V5 — Freshness

```text
[ ] Base images são monitoradas
[ ] Digests são pinados
[ ] Renovate/Dependabot abre updates automaticamente
[ ] GitHub Actions também são atualizadas
[ ] Rebuilds não dependem apenas de mudança no app
[ ] Maximum image age é considerado
[ ] Security updates geram rebuild
```

---
# 198. Checklist V5 — Wolfi/Melange

```text
[ ] Pacotes são construídos from source
[ ] Source hash é verificado
[ ] Build dependencies estão separadas
[ ] Runtime dependencies estão explícitas
[ ] Epoch é usado quando build muda sem upstream version
[ ] Subpackages removem conteúdo não-runtime
[ ] Pacotes possuem SBOM
[ ] Pacotes são assinados
[ ] Update automation está configurada quando aplicável
```

---
# 199. Checklist V5 — OCI

```text
[ ] Artefato é identificado por digest
[ ] Multi-arch index está correto quando necessário
[ ] Registry suporta o modelo de metadata utilizado
[ ] SBOM/signature/attestation são preservadas em cópias
[ ] Mirroring não perde supply-chain artifacts
```

---
# 200. Checklist V5 — Cosign/Sigstore

```text
[ ] Keyless signing é preferido quando possível
[ ] OIDC issuer esperado é verificado
[ ] Signer identity esperada é verificada
[ ] Signing usa digest
[ ] SBOM é atestada quando apropriado
[ ] Provenance é verificável
[ ] Transparency evidence é preservada
[ ] Build tools também têm assinatura verificada
```

---
# 201. Checklist V5 — Air-gap

```text
[ ] Imagem é transferida
[ ] Assinaturas são transferidas
[ ] Attestations são transferidas
[ ] Trusted root é transferido
[ ] Trusted root possui processo de atualização
[ ] Verificação ocorre após import
[ ] Re-signing interno é uma decisão explícita de trust domain
```

---
# 202. Modelo mental final da V5

```text
SECURE SUPPLY CHAIN
        =
Known Source
        +
Verified Inputs
        +
Minimal Packages
        +
Declarative Composition
        +
Reproducible Resolution
        +
Build-time SBOM
        +
High-quality Metadata
        +
VEX
        +
Provenance
        +
Artifact Signing
        +
Workload Identity
        +
Short-lived Credentials
        +
Transparency
        +
Policy Enforcement
        +
Automated Freshness
        +
Continuous Re-evaluation
```

---
# 203. Nova conclusão: trust sem segredo permanente

A principal evolução da V5 é que confiança deixa de depender apenas de:

```text
"qual chave/segredo este sistema possui?"
```

e passa a depender cada vez mais de:

```text
"qual identidade verificável este workload possui?"
```

Isso conecta:

```text
Octo STS
Sigstore
Fulcio
Cloud STS
OIDC
```

em uma filosofia comum.

O pipeline moderno ideal tenta evitar:

```text
PAT
static cloud key
long-lived signing key
shared registry password
```

quando existe uma alternativa federada.

O resultado é uma supply chain que busca ser:

```text
minimal
declarative
reproducible
traceable
signed
policy-driven
fresh
identity-based
secret-minimized
```

---
