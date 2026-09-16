# Marco 07 — Wolfi package engineering, APK, versionamento e OCI

> **Origem:** V6, seções **142–167**.
>
> O conteúdo abaixo foi preservado da V6; a divisão em marcos não altera o conteúdo técnico original.

---
# 142. Wolfi: glibc como decisão de compatibilidade

A documentação oficial reforça uma diferença relevante:

```text
Alpine
→ musl

Wolfi
→ glibc support
```

Wolfi foi desenhado com objetivos próprios:

```text
cloud-native
supply chain metadata
package granularity
glibc compatibility
container-focused lifecycle
```

---
# 143. Wolfi sem kernel

Wolfi não pretende ser uma distribuição completa para bare metal.

```text
Host Kernel
    │
    ▼
Container Runtime
    │
    ▼
Wolfi userspace
```

Por isso não precisa carregar componentes típicos de um sistema bootável completo, como kernel e bootloader.

---
# 144. Build from source reduz intermediários de confiança

Os pacotes Wolfi são construídos diretamente a partir do source.

```text
Upstream
   │
   ▼
Wolfi Build
   │
   ▼
Package
```

Isso reduz intermediários na cadeia de confiança e facilita preservar provenance e metadata desde o build.

---
# 145. Provenance começa no package build

Construir direto do source permite registrar:

```text
source URL
source hash
patches
compiler/toolchain
build flags
runtime dependencies
package version
epoch
```

Portanto:

```text
provenance is not an image-only concern
```

---
# 146. Epoch: versão upstream não é a única versão relevante

No Melange/Wolfi existe o conceito de `epoch`.

```text
8.2.8-r0
8.2.8-r1
```

A versão upstream pode permanecer igual enquanto a revisão do pacote muda por motivos como:

```text
compiler flags
security patch
package metadata
subpackages
build configuration
```

---
# 147. Subpackages reduzem o runtime

Melange permite separar conteúdos em subpackages.

```text
package
├── runtime
├── -dev
├── -dbg
├── -static
├── -docs
└── -locales
```

Isso evita carregar no runtime:

```text
headers
debug symbols
man pages
static libraries
development files
```

---
# 148. Fine-grained packages são uma estratégia de segurança

Quanto mais monolítico o pacote:

```text
install A
→ brings A+B+C+D+E
```

mais difícil controlar a superfície de ataque.

Quanto mais granular:

```text
install A-runtime
```

mais precisamente conseguimos controlar o closure do runtime.

---
# 149. Reusable Melange pipelines

A documentação mostra pipelines reutilizáveis como:

```text
fetch
git-checkout
autoconf/*
cmake/*
go/*
meson/*
ruby/*
split/*
strip
patch
```

Benefícios:

```text
less repeated shell
more consistent builds
reviewable primitives
reusable behavior
```

---
# 150. SHA esperado no fetch

Exemplo:

```yaml
uses: fetch
with:
  uri: ...
  expected-sha256: ...
```

Fluxo:

```text
downloaded artifact
       │
       ▼
SHA-256
       │
       ▼
expected digest?
```

Se não corresponder:

```text
FAIL
```

---
# 151. Custom patches também fazem parte da provenance

Se uma distribuição aplica patches próprios, apenas a versão upstream não descreve completamente o componente.

Precisamos conhecer:

```text
upstream version
+
distribution revision
+
patch set
```

---
# 152. Update automation no próprio pacote

A seção `update` pode ser utilizada para detectar novas releases.

```text
Upstream release
      │
      ▼
release monitor / GitHub tag
      │
      ▼
Wolfi automation
      │
      ▼
package update
```

Freshness passa a fazer parte do package lifecycle.

---
# 153. Desired state no apk

A documentação "Why apk" traz um modelo mental importante.

O apk mantém desired state em:

```text
/etc/apk/world
```

Conceitualmente:

```text
Desired Constraints
       │
       ▼
Dependency Solver
       │
       ▼
Installed State
```

---
# 154. Package manager como state reconciler

Esse design lembra ideias conhecidas em Kubernetes e Terraform:

```text
desired state
      │
      ▼
reconcile
      │
      ▼
actual state
```

Isso ajuda a explicar por que apk se encaixa bem em pipelines declarativos.

---
# 155. Constrained solver

O solver do apk é deliberadamente restrito.

```text
if no valid solution exists
      │
      ▼
fail
```

Para build pipelines:

```text
fail cleanly
>
partially mutate environment
```

---
# 156. Atomicidade na instalação

Pacotes podem ser tratados em um fluxo como:

```text
fetch
verify
unpack to temporary state
atomic commit
```

Isso reduz estados intermediários quebrados.

---
# 157. Version selection também é security policy

Wolfi/apk permite estratégias como:

```text
latest stable
exact version
fuzzy version
minimum version
maximum version
```

Exemplos:

```text
go
go=1.21.1-r0
go=~1.21
go>=1.21
```

A escolha equilibra:

```text
freshness
compatibility
reproducibility
```

---
# 158. Exact version não deve ser automático em todos os casos

Fixar exatamente:

```text
go=1.21.1-r0
```

maximiza reprodutibilidade, mas pode impedir a adoção automática de correções.

Uma separação útil é:

```text
Development constraint
→ compatible range

Resolved artifact metadata
→ exact version
```

---
# 159. Constraints e freshness

```text
Loose:
package

Balanced:
package=~major.minor

Strict:
package=exact-rN
```

O importante é combinar:

```text
constraint strategy
+
automated updates
+
tests
+
resolved metadata
```

---
# 160. OCI: três especificações

OCI mantém três especificações principais:

```text
Image Specification
Runtime Specification
Distribution Specification
```

## Image

Define como a imagem é representada.

## Runtime

Define como containers são executados.

## Distribution

Define como registries distribuem conteúdo.

---
# 161. Content-addressable images

```text
content
   │
   ▼
SHA-256
   │
   ▼
digest
```

Se um único byte muda:

```text
digest changes
```

Isso sustenta:

```text
integrity
immutable references
signature binding
attestation binding
```

---
# 162. OCI manifest, index, layers e config

Uma imagem OCI pode ser vista como:

```text
Image
├── Manifest
├── Config
├── Layers
└── optional Image Index
```

O image index permite representar várias plataformas sob uma única referência lógica.

---
# 163. Multi-arch não é apenas build

Precisamos distinguir:

```text
build artifacts per architecture
```

de:

```text
publish a multi-arch image index
```

```text
amd64 manifest ─┐
                ├── Image Index
arm64 manifest ─┘
```

---
# 164. OCI registry não significa OCI image obrigatoriamente

Um registry OCI-compliant pode armazenar outros formatos.

```text
OCI-compliant registry
    ≠
every stored image is OCI mediaType
```

---
# 165. OCI artifacts: registry como repositório de supply chain metadata

Container registries podem armazenar mais do que imagens:

```text
SBOMs
signatures
attestations
Helm charts
policy bundles
other artifacts
```

Isso permite manter artefato e metadata no mesmo distribution system.

---
# 166. Artifact identity por digest

```text
sha256:image
   │
   ├── signature
   ├── SBOM
   ├── provenance
   └── VEX
```

A associação ao digest evita depender apenas de tags.

---
# 167. OCI artifacts e portabilidade

Nem todo registry suporta da mesma forma todos os mecanismos de referência e artifact metadata.

O conceito durável é:

> Metadata de supply chain precisa estar associada ao digest do artefato e ser recuperável de forma confiável.

---
