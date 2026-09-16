# Marco 10 — Policy engineering, runtime security, Fulcio e Rekor

> **Origem:** V6, seções **230–263**.
>
> O conteúdo abaixo foi preservado da V6; a divisão em marcos não altera o conteúdo técnico original.

---
# 230. CUE vs Rego

Policy Controller suporta políticas declarativas usando:

```text
CUE
Rego
```

## CUE

Bom para:

```text
schema constraints
shape validation
allowed values
structural policies
```

## Rego

Bom para:

```text
complex conditions
aggregation
counting
time calculations
cross-field logic
custom messages
```

---
# 231. Exemplo de CUE: non-root

Conceitualmente:

```yaml
policy:
  includeSpec: true
  type: cue
  data: |
    spec: {
      containers: [...{
        securityContext: {
          runAsUser: != 0
        }
      }]
    }
```

Isso avalia a configuração do workload.

---
# 232. Exemplo de CUE: privileged

```text
privileged: true
```

pode ser rejeitado.

A intenção é garantir:

```text
privileged != true
```

para:

```text
containers
initContainers
ephemeralContainers
```

---
# 233. Exemplo de capabilities

Podemos restringir:

```text
NET_ADMIN
SYS_ADMIN
SYS_MODULE
...
```

e permitir apenas um conjunto controlado.

Boa prática geral:

```yaml
capabilities:
  drop:
    - ALL
```

e adicionar explicitamente apenas o necessário.

---
# 234. Exemplo de sysctls

Também é possível inspecionar:

```text
spec.securityContext.sysctls
```

e restringir a parâmetros conhecidos.

Mas esse controle pertence mais à categoria:

```text
Kubernetes workload hardening
```

do que:

```text
software supply chain provenance
```

Essa distinção deve ficar clara.

---
# 235. Supply chain policy vs workload policy

## Supply chain policy

Pergunta:

```text
Can I trust how this artifact was produced?
```

Exemplos:

```text
signature
signer identity
SBOM attestation
provenance
vulnerability attestation
image age
```

## Workload policy

Pergunta:

```text
Is this Pod allowed to run with this configuration?
```

Exemplos:

```text
runAsUser
privileged
capabilities
sysctls
hostNetwork
hostPID
hostIPC
```

São camadas diferentes.

---
# 236. Onde o Policy Controller é mais único

Para regras como:

```text
non-root
privileged
capabilities
sysctls
```

Kubernetes possui mecanismos próprios e ecossistemas consolidados, como:

```text
Pod Security Admission
Kyverno
OPA Gatekeeper
```

O diferencial mais forte do Sigstore Policy Controller está em:

```text
signature verification
signer identity
attestations
supply-chain metadata
digest-aware admission
```

Por isso, na V6, runtime policies são apresentadas como complemento.

---
# 237. Evite duplicar policy engines sem motivo

Um ambiente pode acabar com:

```text
Pod Security Admission
+
Kyverno
+
Gatekeeper
+
Policy Controller
+
custom webhooks
```

Isso pode gerar:

```text
overlapping rules
confusing errors
operational complexity
ordering ambiguity
ownership problems
```

Escolha claramente a responsabilidade de cada mecanismo.

---
# 238. Uma divisão prática

Exemplo de arquitetura:

```text
Sigstore Policy Controller
  ├── image signature
  ├── signer identity
  ├── SBOM
  ├── provenance
  └── vulnerability attestations

Pod Security Admission / Kyverno
  ├── non-root
  ├── privileged
  ├── capabilities
  ├── seccomp
  ├── host namespaces
  └── volume/security constraints
```

Isso reduz sobreposição.

---
# 239. `warn` vs `enforce`

Nem toda policy precisa bloquear imediatamente.

## warn

```text
violation
   │
   ▼
allow + warning
```

Útil para:

```text
inventory
migration
policy tuning
false-positive analysis
```

## enforce

```text
violation
   │
   ▼
deny
```

Útil quando a policy está madura.

---
# 240. Fail-open vs fail-closed

Toda architecture de admission precisa decidir:

> O que acontece se a verificação não puder ser executada?

Exemplos:

```text
registry unavailable
transparency service unavailable
policy controller unavailable
signature cannot be fetched
attestation cannot be retrieved
```

Em workloads sensíveis, o princípio tende a ser:

```text
cannot establish trust
       │
       ▼
do not admit
```

Mas isso possui impacto de disponibilidade e precisa ser deliberadamente projetado.

---
# 241. No matching policy também é uma decisão

Não encontrar uma policy pode significar:

```text
allow
warn
deny
```

Isso precisa ser tratado como configuração explícita da plataforma.

Caso contrário, gaps de matching podem virar bypass.

---
# 242. `glob: "**"` merece cuidado

Uma regra global parece simples:

```yaml
images:
  - glob: "**"
```

Mas pode atingir:

```text
system workloads
third-party operators
debug images
ephemeral workloads
internal registries
bootstrap components
```

Adote scoping deliberado.

---
# 243. `static: pass` não verifica provenance

Uma authority:

```yaml
static:
  action: pass
```

significa, conceitualmente:

```text
do not require a cryptographic authority here
```

Ela pode ser apropriada para policies que avaliam apenas:

```text
Pod spec
OCI config
metadata
```

Mas não deve ser confundida com:

```text
verified signer
```

---
# 244. Anti-pattern: "policy exists, therefore secure"

Exemplo ruim:

```text
glob: "**"
+
static pass
+
no meaningful policy
```

Ter um admission webhook não cria segurança sozinho.

Precisamos de:

```text
meaningful evidence
+
trusted authorities
+
correct matching
+
policy semantics
+
operational ownership
```

---
# 245. Custom error messages

Policies devem ser operáveis.

Erro ruim:

```text
admission denied
```

Erro melhor:

```text
Image rejected:
missing SPDX SBOM attestation from trusted release workflow.
```

Isso ajuda:

```text
developer experience
incident response
policy adoption
troubleshooting
```

---
# 246. Policy é produto de plataforma

Uma policy madura precisa ter:

```text
owner
version
tests
documentation
rollout strategy
exception process
observability
change review
```

Policy-as-code deve ser tratada como software.

---
# 247. Teste positivo e negativo

Cada policy deve possuir pelo menos:

```text
known-good case
known-bad case
```

Exemplo:

```text
signed image
→ expected ADMIT

unsigned image
→ expected DENY
```

Ou:

```text
SBOM attested
→ expected ADMIT

missing SBOM
→ expected DENY
```

---
# 248. Policy test matrix

Uma matriz útil:

| Caso | Assinatura | SBOM | Provenance | CVE policy | Esperado |
|---|---|---|---|---|---|
| A | ✓ | ✓ | ✓ | ✓ | Admit |
| B | ✗ | ✓ | ✓ | ✓ | Deny |
| C | ✓ | ✗ | ✓ | ✓ | Deny |
| D | ✓ | ✓ | ✗ | ✓ | Deny |
| E | ✓ | ✓ | ✓ | ✗ | Deny |

Isso transforma arquitetura em comportamento testável.

---
# 249. Policy Controller como consumer de metadata

Até agora, produzimos:

```text
SBOM
provenance
signature
vulnerability report
```

Agora existe um consumidor concreto:

```text
Policy Controller
```

Isso responde uma pergunta importante:

> Para quem estamos produzindo toda essa metadata?

Resposta:

```text
humans
security tools
scanners
auditors
admission controllers
automation
```

---
# 250. Attestation precisa ter finalidade

Produzir attestations que ninguém verifica gera:

```text
security metadata theater
```

O ciclo correto é:

```text
Generate
   │
   ▼
Sign
   │
   ▼
Store
   │
   ▼
Verify
   │
   ▼
Enforce
```

---
# 251. From build policy to runtime policy

A V6 fecha o circuito:

```text
BUILD TIME
    │
    ├── source validation
    ├── package build
    ├── SBOM
    ├── scan
    ├── provenance
    └── signing
           │
           ▼
REGISTRY
           │
           ▼
ADMISSION TIME
    │
    ├── verify signature
    ├── verify signer
    ├── verify attestations
    ├── evaluate vulnerabilities
    └── inspect workload policy
           │
           ▼
RUNTIME
```

---
# 252. Fulcio: identity-bound certificate

Fulcio liga:

```text
OIDC identity
+
ephemeral public key
```

por meio de um certificado X.509 de curta duração.

Modelo:

```text
OIDC Provider
     │
     ▼
Identity proof
     │
     ▼
Fulcio
     │
     ▼
Short-lived certificate
     │
     ▼
Artifact signing
```

---
# 253. Fulcio não prova que o software é seguro

Fulcio responde essencialmente:

```text
This public key was associated with this identity.
```

Ele não afirma:

```text
the code is vulnerability-free
the build is trustworthy
the artifact is approved
```

Essas garantias vêm de outras evidências e policies.

---
# 254. Certificate identity

Na verificação, interessam campos como:

```text
OIDC issuer
subject / SAN
certificate validity
signing identity
```

Por isso o verifier precisa conhecer:

```text
expected issuer
expected subject
```

e não aceitar qualquer certificado válido.

---
# 255. Short-lived certificate reduz key custody

Modelo tradicional:

```text
private signing key
       │
       ├── storage
       ├── backup
       ├── rotation
       ├── revocation
       └── compromise risk
```

Modelo keyless:

```text
OIDC identity
       │
       ▼
ephemeral signing material
       │
       ▼
short-lived certificate
       │
       ▼
sign
```

Isso reduz a necessidade de custodiar uma chave de assinatura permanente.

---
# 256. Rekor: transparency, não approval

Rekor é um transparency log append-only/tamper-evident.

Ele pode registrar evidências de que:

```text
signature existed
at a certain point
with specific metadata
```

Mas:

```text
entry in Rekor
    ≠
artifact approved
```

O consumer ainda precisa aplicar trust policy.

---
# 257. Transparency permite detecção

Uma propriedade importante:

```text
logs can be monitored
```

Isso permite procurar:

```text
unexpected signer
unexpected artifact
unexpected release
unexpected certificate
```

Logo transparency não serve apenas para verificação pontual.

Ela também suporta detecção contínua.

---
# 258. Inclusion proofs

Merkle trees permitem provar que uma entrada pertence ao log sem precisar transportar o log inteiro.

Conceitualmente:

```text
entry hash
   │
   ├── sibling hash
   ├── sibling hash
   └── ...
        │
        ▼
     root hash
```

Se o root esperado for alcançado:

```text
entry inclusion verified
```

---
# 259. Rekor CLI como ferramenta de investigação

Ferramentas como `rekor-cli` permitem consultar:

```text
log index
UUID
artifact metadata
signature metadata
```

Isso é útil para:

```text
incident analysis
verification
education
transparency investigation
```

No fluxo cotidiano, Cosign normalmente abstrai boa parte desse trabalho.

---
# 260. Public vs private transparency infrastructure

Uma organização pode:

```text
use public Sigstore
```

ou operar componentes próprios.

Isso muda:

```text
trust root
operational burden
availability responsibility
governance
audit model
```

Self-hosting não é automaticamente mais seguro.

É uma mudança de trust ownership.

---
# 261. Custom Sigstore trust roots

Policy Controller também pode ser configurado para verificar contra trust roots privados.

Arquitetura:

```text
Internal OIDC
    │
    ▼
Internal Fulcio
    │
    ▼
Internal Rekor
    │
    ▼
Internal Policy Controller
```

Esse modelo pode fazer sentido em ambientes regulados ou isolados.

---
# 262. Bundle format e OCI 1.1

Versões recentes do ecossistema Sigstore evoluíram a serialização de signatures/attestations em direção a bundles e mecanismos alinhados ao OCI 1.1.

O princípio que importa para a arquitetura é:

```text
metadata format evolves
```

Portanto:

```text
pin tool versions
test verification
validate registry compatibility
upgrade policy-controller with care
```

---
# 263. Admission policy também precisa de version compatibility

Uma combinação real envolve:

```text
Cosign
Policy Controller
Sigstore bundle format
OCI registry
Kubernetes
policy CRDs
```

Atualizar um componente isoladamente pode afetar compatibilidade.

A plataforma deve testar o conjunto.

---
