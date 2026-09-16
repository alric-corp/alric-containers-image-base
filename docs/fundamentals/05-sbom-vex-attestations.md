# Marco 05 — SBOM avançada, Attestations, VEX e supply chain verificável

> **Origem:** V6, seções **101–123**.
>
> O conteúdo abaixo foi preservado da V6; a divisão em marcos não altera o conteúdo técnico original.

---
# 101. SBOM automática não significa SBOM perfeita

A documentação oficial reforça um ponto importante:

```text
have SBOM
    ≠
have good SBOM
```

A utilidade da SBOM depende da qualidade dos dados.

Uma SBOM útil deve possuir, quando aplicável:

```text
component name
version
package ecosystem
purl
transitive dependencies
license
supplier
checksums
relationships
timestamp
```

---
# 102. Package URL (purl)

O `purl` ajuda a identificar um pacote sem depender apenas de:

```text
name + version
```

Exemplo conceitual:

```text
pkg:apk/wolfi/git@2.39.0-r1?arch=x86_64
```

Ele fornece contexto sobre:

```text
package type
ecosystem
name
version
architecture / qualifiers
```

Isso reduz ambiguidade durante:

```text
vulnerability matching
license analysis
VEX matching
inventory
```

---
# 103. SBOM deve conter dependências transitivas

Uma boa SBOM não deve parar em:

```text
Application
├── direct dependency A
└── direct dependency B
```

Precisamos também de:

```text
Application
├── A
│   └── A1
│       └── A2
└── B
    └── B1
```

Porque vulnerabilidades frequentemente aparecem em dependências que o time nunca adicionou diretamente.

---
# 104. SBOM também serve para licença e supplier

O uso de SBOM não se limita a CVEs.

Ela também pode responder:

```text
Qual licença esse componente possui?
Quem é o supplier?
Quais componentes GPL/MIT/Apache existem?
Existem dependências abandonadas?
```

Portanto:

```text
SBOM
=
security inventory
+
legal inventory
+
supplier inventory
```

---
# 105. Checksums dentro da SBOM

Checksums permitem comparar conteúdo de forma verificável.

Exemplo:

```text
Component
├── name
├── version
└── checksum
```

Se o conteúdo mudar:

```text
checksum changes
```

Isso ajuda casos de:

```text
tampering detection
integrity verification
artifact correlation
```

---
# 106. SPDX e CycloneDX

Dois formatos amplamente utilizados para SBOM são:

```text
SPDX
CycloneDX
```

A escolha não deve ser baseada apenas em preferência.

É preciso verificar se:

```text
scanner
SCA
registry
policy engine
compliance tooling
```

consegue consumir corretamente o formato escolhido.

---
# 107. Medir qualidade da SBOM

A documentação cita ferramentas específicas para avaliar SBOMs.

## SBOM Scorecard

Pode avaliar campos e qualidade de documentos:

```text
SPDX
CycloneDX
```

## NTIA Conformance Checker

Avalia se uma SBOM SPDX contém os elementos mínimos esperados.

O princípio mais importante é:

> **SBOM também precisa de quality gates.**

Assim como testamos código, podemos testar metadata de supply chain.

---
# 108. Pós-build SBOM vs build-time SBOM

A documentação reforça a distinção:

## Post-build scanner

```text
Image
  │
  ▼
filesystem inspection
  │
  ▼
infer components
```

Pode perder componentes não registrados em package managers.

## Build-time SBOM

```text
Build inputs
   │
   ▼
known inventory
   │
   ▼
SBOM
```

Tem acesso à informação no momento em que ela ainda é conhecida de forma explícita.

Isso explica por que apko/Melange tratam SBOM como parte do build.

---
# 109. SBOM ≠ Attestation

Essa distinção merece ficar explícita na V4.

## SBOM

Responde:

```text
WHAT is inside?
```

## Attestation

Fornece uma afirmação verificável sobre um artefato.

Conceitualmente:

```text
Predicate
   +
Artifact identity
   +
Signer
   +
Signature
```

Então podemos ter:

```text
SBOM
      │
      ▼
attested SBOM
```

Uma SBOM sozinha não prova automaticamente:

```text
quem a produziu
quando
como
se foi alterada
```

---
# 110. Attach vs Attest

A documentação diferencia dois modelos conceituais.

## Attach

```text
Image
  │
  └── SBOM file
```

Cria uma associação.

## Attest

```text
Image
  │
  └── signed statement
       └── SBOM predicate
```

Além da associação, existe uma declaração verificável.

Portanto:

```text
association
    ≠
attestation
```

---
# 111. OpenVEX: o próximo nível após a SBOM

SBOM responde:

```text
"Tenho um componente relacionado a CVE-X?"
```

Mas isso não responde:

```text
"A CVE-X é realmente explorável no meu produto?"
```

VEX existe para comunicar esse segundo contexto.

Fluxo:

```text
SBOM
  │
  ▼
component has CVE
  │
  ▼
VEX
  │
  ├── affected
  ├── not_affected
  ├── fixed
  └── under_investigation
```

---
# 112. Os quatro estados VEX

## `affected`

O produto é afetado.

```text
ACTION REQUIRED
```

## `not_affected`

A vulnerabilidade existe no contexto do componente, mas não afeta aquele produto.

Precisa de justificativa/contexto.

## `fixed`

A versão contém correção.

## `under_investigation`

O impacto ainda está sendo avaliado.

Isso transforma um scanner de:

```text
CVE list
```

em algo mais próximo de:

```text
CVE + exploitability context
```

---
# 113. VEX reduz vulnerability noise

Sem VEX:

```text
Scanner
   │
   ▼
500 alerts
```

Com contexto:

```text
500 alerts
   │
   ├── fixed
   ├── not affected
   ├── accepted/investigating
   └── actionable
```

O objetivo não é “esconder CVEs”.

É distinguir:

```text
present vulnerability
```

de:

```text
exploitable vulnerability
```

---
# 114. VEX deve ser machine-readable e auditável

Um VEX pode ser associado a:

```text
product
vulnerability
status
justification
timestamp
author
```

Isso permite automatizar:

```text
scanner filtering
risk prioritization
policy decisions
security dashboards
```

Além disso, documentos VEX podem ser assinados/atestados e associados ao artefato.

---
# 115. VEX evolui no tempo

A avaliação de uma CVE pode mudar.

Exemplo:

```text
T0
under_investigation

T1
not_affected
```

ou:

```text
T0
affected

T1
fixed
```

Portanto VEX funciona como uma comunicação cronológica de estado.

Esse detalhe é importante porque vulnerabilidade não é apenas um booleano estático.

---
# 116. Modelo completo: SBOM + VEX

Podemos resumir:

```text
SBOM
=
"What components do I have?"

Scanner
=
"What known CVEs map to these components?"

VEX
=
"Which of those CVEs actually affect this product?"
```

Isso produz:

```text
Inventory
    │
    ▼
Potential Risk
    │
    ▼
Exploitability Context
    │
    ▼
Prioritized Action
```

---
# 117. Private APK repositories

A documentação também mostra que esse modelo pode ser usado com repositórios privados.

Arquitetura corporativa:

```text
Source
  │
  ▼
Melange
  │
  ▼
Internal APK
  │
  ▼
Private APK Repository
  │
  ▼
apko
```

Isso permite centralizar:

```text
approved packages
internal packages
version policy
signing
access control
```

e evita depender de pacotes locais em pipelines de produção.

---
# 118. CI/CD: três formas de operar apko

A documentação sugere pelo menos três caminhos práticos:

## Container oficial

```text
docker run cgr.dev/chainguard/apko ...
```

Bom para:

```text
local development
generic CI
experiments
```

## GitHub Actions

Existe ação dedicada para build com apko.

Bom quando GitHub Actions já é a plataforma de CI.

## Bazel / rules_apko

Bom para ambientes que precisam de:

```text
hermetic builds
lockfiles
strong caching
large monorepos
reproducible toolchains
```

---
# 119. Um apko.yaml mais próximo de produção

Um exemplo conceitual mais completo fica assim:

```yaml
contents:
  keyring:
    - https://packages.wolfi.dev/os/wolfi-signing.rsa.pub
    - ./internal-signing.rsa.pub

  repositories:
    - https://packages.wolfi.dev/os
    - '@local /work/packages'

  packages:
    - ca-certificates-bundle
    - my-application@local

accounts:
  groups:
    - groupname: nonroot
      gid: 65532

  users:
    - username: nonroot
      uid: 65532

  run-as: 65532

entrypoint:
  command: /usr/bin/my-application

archs:
  - x86_64
  - aarch64
```

Esse arquivo descreve declarativamente:

```text
trust
repositories
dependencies
identity
entrypoint
architectures
```

---
# 120. Uma visão mais madura de "secure image"

Depois da documentação oficial, podemos expandir a definição:

```text
Secure Container Image
=
Minimal Components
+
Declarative Composition
+
Pinned Inputs
+
Verified Repositories
+
Signed Packages
+
Non-root Runtime
+
Build-time SBOM
+
High-quality SBOM
+
Provenance / Attestation
+
Image Signature
+
VEX Context
+
Continuous Rebuild
+
Admission Policy
```

---
# 121. Pipeline de referência V4

```text
                  SOURCE CODE
                       │
                       ▼
               TRUSTED CI IDENTITY
                       │
                       ▼
                    MELANGE
                       │
            ┌──────────┴───────────┐
            ▼                      ▼
      APPLICATION APK          PACKAGE SBOM
            │
            ▼
       PACKAGE SIGNING
            │
            ▼
     PRIVATE / TRUSTED APK REPO
            │
            ▼
               APKO RESOLUTION
                       │
                       ▼
                 apko.lock.json
                       │
                       ▼
                    APKO
                       │
              ┌────────┴────────┐
              ▼                 ▼
          OCI IMAGE          IMAGE SBOM
              │
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
       TRANSPARENCY LOG
              │
              ▼
            REGISTRY
              │
              ▼
       ADMISSION POLICY
              │
              ▼
           KUBERNETES
              │
              ▼
   CONTINUOUS VULNERABILITY
        RE-EVALUATION
```

---
# 122. Checklist V4

## apko

```text
[ ] YAML é declarativo
[ ] Não existem passos de build arbitrários na composição
[ ] Repositórios são explicitamente definidos
[ ] Keyrings são explicitamente definidos
[ ] Wolfi e Alpine não são misturados
[ ] Pacotes internos são assinados
[ ] Imagem executa como non-root
[ ] Arquiteturas necessárias são declaradas
[ ] Lockfile é utilizado quando o fluxo suporta
```

## Melange

```text
[ ] Build dependencies estão em environment
[ ] Runtime dependencies estão no package
[ ] Pipeline produz apenas os artefatos necessários
[ ] APK é assinado
[ ] Builds multi-arch são testados
[ ] Índices APK são gerados
```

## SBOM

```text
[ ] É gerada durante o build quando possível
[ ] Possui nome e versão
[ ] Possui purl/ecossistema
[ ] Inclui dependências transitivas
[ ] Inclui licenças
[ ] Inclui supplier quando relevante
[ ] Inclui checksums quando relevante
[ ] Formato é suportado pelos consumidores
[ ] Qualidade da SBOM é validada
```

## Vulnerabilities

```text
[ ] Scanner roda continuamente
[ ] Resultados são correlacionados ao digest
[ ] VEX é usado quando há contexto de exploitability
[ ] Estado under_investigation é acompanhado
[ ] not_affected possui justificativa
[ ] fixed está associado às versões corretas
```

## Artifact trust

```text
[ ] SBOM é associada ao artefato
[ ] Attestations são verificáveis
[ ] Imagem é assinada
[ ] Signer identity é validada
[ ] Provenance é validada
[ ] Registry é confiável
[ ] Admission aplica as políticas
```

---
# 123. Conclusão V4: de imagem mínima para artefato verificável

A documentação oficial reforça que o objetivo final não é apenas produzir:

```text
small container
```

Nem apenas:

```text
0 CVEs today
```

O objetivo é produzir um artefato sobre o qual conseguimos responder:

```text
O que existe dentro?
De onde cada pacote veio?
Qual chave assinou esse pacote?
Quais versões foram resolvidas?
Quais checksums foram utilizados?
Quem construiu?
Com qual toolchain?
Qual é o digest final?
Qual SBOM pertence a esse digest?
A SBOM é completa?
Quais CVEs estão associadas?
Quais realmente afetam o produto?
Qual é a provenance?
A imagem foi assinada?
A identidade do signer é confiável?
A política permite executar esse artefato?
```

Nesse ponto deixamos de falar somente sobre:

```text
Container Image Building
```

e passamos a falar sobre:

```text
Verifiable Software Supply Chain
```

---
