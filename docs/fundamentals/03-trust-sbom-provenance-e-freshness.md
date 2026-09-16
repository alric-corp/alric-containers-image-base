# Marco 03 — Trust, SBOM, Provenance, assinatura e Freshness

> **Origem:** V6, seções **55–80**.
>
> O conteúdo abaixo foi preservado da V6; a divisão em marcos não altera o conteúdo técnico original.

---
# 55. Assinatura não significa que o software é bom

Um dos insights mais importantes do terceiro vídeo é separar duas perguntas:

```text
1. Este artefato é autêntico?
2. Este artefato é seguro/confiável?
```

Uma assinatura responde principalmente à primeira.

Se assinarmos uma imagem vulnerável:

```text
Vulnerable Image
       │
       ▼
    Signature
       │
       ▼
Authentic Vulnerable Image
```

a assinatura não remove vulnerabilidades.

Ela nos permite verificar que:

```text
o artefato verificado
=
o artefato que foi assinado
```

Portanto:

```text
Signature
   ≠
Security approval
```

A assinatura é um mecanismo de:

```text
integridade
+
identidade
+
autenticidade
```

Ela precisa ser combinada com:

```text
SBOM
scan
provenance
policy
trusted build pipeline
```

---
# 56. "Não assine qualquer coisa que chegou na sua mesa"

Essa frase resume muito bem outro insight do vídeo.

Não basta:

```text
Build
  │
  ▼
Artifact
  │
  ▼
Security Team
  │
  ▼
Sign
```

se ninguém consegue provar como o artefato foi produzido.

O modelo desejável é:

```text
Trusted Source
      │
      ▼
Trusted CI
      │
      ▼
Controlled Build
      │
      ├── inputs conhecidos
      ├── dependencies conhecidas
      ├── tests
      ├── scan
      └── SBOM
             │
             ▼
        Artifact
             │
             ▼
         Signature
```

A confiança deve começar **antes da assinatura**.

---
# 57. A assinatura da SBOM também depende da origem da SBOM

Assinar uma SBOM é útil porque permite detectar alteração posterior.

Porém:

```text
Bad / incomplete SBOM
        │
        ▼
     Signature
```

continua sendo uma SBOM ruim — apenas autenticada.

A cadeia correta é:

```text
Build process
     │
     ▼
Known inputs
     │
     ▼
SBOM generated during build
     │
     ▼
SBOM verification
     │
     ▼
Signature / attestation
```

Por isso build-time SBOM continua sendo um conceito central.

---
# 58. SBOM como inventário de segurança ao longo do tempo

O terceiro vídeo explica muito bem por que uma SBOM continua útil **depois do deploy**.

Considere:

```text
January
Image A
└── libX 1.2
    └── nenhuma CVE conhecida
```

Meses depois:

```text
June
libX 1.2
└── CVE-XXXX publicada
```

A aplicação pode nem ter sido reconstruída.

Mas, se temos uma SBOM confiável:

```text
Image digest
     │
     ▼
SBOM
     │
     ▼
libX 1.2
```

podemos consultar novamente o inventário e descobrir:

```text
"Quais imagens ainda possuem libX 1.2?"
```

Portanto a SBOM não serve apenas para o pipeline.

Ela também serve para:

```text
incident response
vulnerability response
asset inventory
compliance
runtime policy
```

---
# 59. Dependências transitivas são parte da superfície de ataque

Uma aplicação raramente possui apenas dependências diretas.

Exemplo:

```text
Application
   │
   └── Library A
         │
         └── Library B
               │
               └── Library C
```

Mesmo que o time tenha escolhido conscientemente:

```text
Library A
```

ele pode acabar executando:

```text
A + B + C + ...
```

É por isso que inventariar apenas dependências diretas é insuficiente.

O objetivo deve ser enxergar:

```text
direct dependencies
+
transitive dependencies
+
OS packages
+
language packages
+
embedded libraries
```

---
# 60. Typosquatting e dependency confusion

O terceiro vídeo adiciona dois exemplos úteis de ataques à cadeia de dependências.

## Typosquatting

Um atacante publica um pacote com nome parecido com um pacote popular.

Exemplo conceitual:

```text
lodash
  ↓
lodahs
```

Se alguém errar o nome:

```bash
npm install lodahs
```

pode instalar um pacote malicioso.

## Dependency confusion

Imagine uma empresa utilizando internamente:

```text
acme-utils
```

Se o resolver consultar um repositório público antes do repositório corporativo, um atacante pode publicar:

```text
public registry
└── acme-utils
```

e tentar fazer com que a dependência pública seja selecionada.

Isso mostra que supply chain security também envolve:

```text
repository priority
package provenance
dependency pinning
private registry policy
checksums
signatures
```

---
# 61. Dockerfile: pensar em passos vs pensar no estado final

O terceiro vídeo fornece uma maneira muito boa de visualizar Dockerfiles.

Um Dockerfile normalmente descreve:

```text
faça A
depois B
depois C
depois D
```

Por exemplo:

```dockerfile
RUN apk add ...
RUN curl ...
COPY ...
RUN chmod ...
```

Isso é um modelo **imperativo**.

Podemos visualizar verticalmente:

```text
Base
 │
 ▼
Layer 1
 │
 ▼
Layer 2
 │
 ▼
Layer 3
 │
 ▼
Final Image
```

A abordagem declarativa pergunta outra coisa:

> Quais componentes devem existir na imagem final?

```text
Desired Image

├── application
├── libc
├── certificates
└── runtime
```

Essa mudança é importante porque aproxima o build de:

```text
desired state
```

em vez de:

```text
sequence of arbitrary mutations
```

---
# 62. Custom Distroless

Distroless é um conceito muito útil, mas imagens distroless genéricas ainda precisam atender vários tipos de aplicações.

Por isso podem existir variantes como:

```text
static
base
cc
java
python
node
```

A consequência é que uma imagem genérica pode possuir mais componentes do que **aquela aplicação específica** realmente precisa.

A ideia apresentada com apko pode ser vista como:

```text
Generic Distroless
        ↓
Custom Distroless
```

Em vez de escolher:

```text
"qual flavor chega mais perto?"
```

escolhemos:

```text
"quais pacotes exatamente meu workload precisa?"
```

---
# 63. Granularidade importa

Quanto mais granular for o ecossistema de pacotes:

```text
package A
package B
package C
package D
```

mais fácil é construir:

```text
Image
├── A
└── C
```

em vez de instalar um pacote maior que implicitamente traz:

```text
A + B + C + D + E + F
```

Essa granularidade ajuda a reduzir:

```text
package count
dependency count
attack surface
patching surface
```

---
# 64. Imagens ficam antigas mesmo quando o código não muda

Esse é outro insight muito relevante.

Um serviço pode estar perfeitamente estável:

```text
Application version
v1.0
```

e ficar meses sem commits.

Mas sua imagem pode conter:

```text
CA certificates
timezone database
libc
OpenSSL
runtime
OS packages
```

que continuam evoluindo.

Portanto:

```text
no application changes
       ≠
no image changes required
```

Uma política madura deve considerar rebuild por:

```text
source change
OR
base/package update
OR
security update
OR
certificate/trust change
```

---
# 65. Freshness deve virar uma propriedade da imagem

Podemos adicionar uma métrica importante à avaliação:

```text
Build Age
```

Exemplo:

```text
Image A
built 2 days ago

Image B
built 280 days ago
```

Mesmo usando o mesmo código da aplicação, o risco operacional pode ser muito diferente.

Isso sugere controles como:

```text
maximum image age
automatic rebuild
dependency update policy
EOL policy
```

---
# 66. CA certificates também são dependências

Normalmente pensamos em dependências como:

```text
OpenSSL
glibc
Python
Node
libraries
```

Mas o terceiro vídeo destaca outro componente:

```text
CA trust bundle
```

O trust store determina **quem a aplicação considera confiável para TLS**.

Portanto ele também faz parte da postura de segurança.

Problemas possíveis:

```text
stale CA
revoked CA
unwanted CA
corporate CA missing
corporate CA obsolete
```

---
# 67. Trust store em runtime

Uma alternativa interessante apresentada é não congelar necessariamente o conjunto de CAs dentro de cada imagem.

Em Kubernetes podemos pensar em:

```text
Cluster Trust Policy
        │
        ▼
Trust Bundle
        │
        ▼
Workload A
Workload B
Workload C
```

em vez de:

```text
Image A ── CA bundle
Image B ── CA bundle
Image C ── CA bundle
```

Isso permite atualizar confiança sem reconstruir todas as imagens apenas para trocar o trust bundle.

Ferramentas como `trust-manager` existem justamente para distribuir bundles de certificados confiáveis dentro de clusters Kubernetes.

---
# 68. Build-time dependency ≠ Runtime dependency

A demo também reforça algo extremamente importante.

Durante o build podemos precisar de:

```text
Go compiler
GCC
binutils
shell
headers
git
```

Mas isso não significa que esses componentes devam existir no runtime.

```text
BUILD ENVIRONMENT
├── compiler
├── linker
├── headers
├── shell
└── tooling

        │
        ▼

ARTIFACT

        │
        ▼

RUNTIME IMAGE
├── application
├── required libraries
└── required data
```

Esse é o princípio de multi-stage build levado para uma supply chain declarativa.

---
# 69. O próprio software da empresa também deve entrar na cadeia

Não adianta termos:

```text
Wolfi package A ✅
Wolfi package B ✅
Wolfi package C ✅
```

e depois terminar com:

```dockerfile
COPY ./my-random-binary /app
```

sem metadata.

A aplicação da empresa também precisa participar da cadeia.

Fluxo:

```text
Application source
       │
       ▼
Melange
       │
       ▼
Application APK
       │
       ├── version
       ├── dependencies
       ├── SBOM
       └── signature
              │
              ▼
             apko
```

Assim o software interno deixa de ser uma exceção opaca dentro da imagem.

---
# 70. "SBOM all the way down"

Esse talvez seja o melhor conceito técnico do terceiro vídeo.

A imagem pode ter:

```text
OCI Image
│
├── OS Package A
│    └── SBOM
│
├── OS Package B
│    └── SBOM
│
└── Application Package
     └── SBOM
          │
          ├── Go module A
          ├── Go module B
          └── Go module C
```

Mesmo que a aplicação final seja:

```text
ELF binary
```

e visualmente pareça apenas um blob de machine code, a metadata produzida durante o build permite continuar identificando as dependências utilizadas para produzi-la.

Isso é muito mais poderoso do que tentar reconstruir tudo somente a partir do binário final.

---
# 71. Provenance: não basta saber "o quê"

SBOM responde principalmente:

```text
O que existe no artefato?
```

Provenance responde:

```text
Como esse artefato foi produzido?
```

Uma provenance útil pode registrar:

```text
source repository
commit
builder
build environment
inputs
build configuration
output digest
```

Portanto:

```text
SBOM
=
WHAT

Provenance
=
HOW / WHERE / FROM WHAT

Signature
=
WHO / INTEGRITY
```

Os três são complementares.

---
# 72. Artifact identity deve usar digest

Tags são convenientes:

```text
my-app:1.0
my-app:latest
```

mas a identidade criptográfica do conteúdo é melhor representada por:

```text
sha256:...
```

Isso permite associar:

```text
Image Digest
     │
     ├── SBOM
     ├── provenance
     ├── signature
     └── scan result
```

àquele conteúdo específico.

Se o conteúdo mudar:

```text
digest changes
```

---
# 73. Transparency log e Rekor

Depois de produzir e assinar um artefato, existe outra pergunta:

> Como provar posteriormente que determinada assinatura existia?

No ecossistema Sigstore existe o **Rekor**, um transparency log.

Conceitualmente:

```text
Artifact Digest
      │
      ▼
Signature
      │
      ▼
Transparency Log
      │
      ▼
Auditable Record
```

Isso cria evidência verificável sobre eventos de assinatura.

O modelo de keyless signing do Sigstore também associa uma identidade OIDC a certificados de curta duração, reduzindo a dependência de uma chave privada de longa duração armazenada manualmente.

---
# 74. A cadeia de confiança completa

Com o terceiro vídeo, podemos deixar o modelo mais completo:

```text
Source Repository
       │
       ▼
Authenticated CI Identity
       │
       ▼
Hermetic / Controlled Build
       │
       ├── verified build dependencies
       ├── package signatures
       ├── checksums
       └── tests
              │
              ▼
        Application Package
              │
              ├── SBOM
              └── signature
                     │
                     ▼
                    apko
                     │
                     ▼
                 OCI Image
                     │
           ┌─────────┼─────────┐
           ▼         ▼         ▼
         SBOM    Provenance   Scan
           │         │         │
           └─────────┼─────────┘
                     │
                     ▼
                  Cosign
                     │
                     ▼
             Transparency Log
                     │
                     ▼
                  Registry
                     │
                     ▼
             Admission Policy
                     │
                     ▼
                  Runtime
```

---
# 75. Admission Control fecha o ciclo

No Kubernetes, assinatura e metadata só geram valor operacional real quando conseguimos aplicar política.

Exemplos conceituais:

```text
ALLOW image IF

signature valid
AND
trusted identity
AND
approved registry
AND
SBOM available
AND
provenance available
AND
no blocked package
AND
policy satisfied
```

Caso contrário:

```text
DENY
```

Assim:

```text
Supply Chain Metadata
        │
        ▼
Policy Decision
        │
        ▼
Runtime
```

---
# 76. O que assinatura garante — e o que não garante

| Pergunta | Assinatura responde? |
|---|---|
| O artefato foi alterado? | ✅ Ajuda a verificar |
| Quem/qual identidade assinou? | ✅ |
| O digest é o esperado? | ✅ |
| O software possui CVE? | ❌ |
| O código é seguro? | ❌ |
| O build foi confiável? | ❌ Sozinha não |
| As dependências são permitidas? | ❌ Sozinha não |
| A SBOM está completa? | ❌ |
| A configuração é segura? | ❌ |

Esse quadro evita tratar signing como uma solução mágica.

---
# 77. O que SBOM garante — e o que não garante

| Pergunta | SBOM responde? |
|---|---|
| Quais componentes foram inventariados? | ✅ |
| Qual versão dos componentes? | ✅ Quando registrada |
| Existem dependências transitivas conhecidas? | ✅ Pode registrar |
| O artefato não foi alterado? | ❌ |
| O software é livre de vulnerabilidades? | ❌ |
| A SBOM é autêntica? | ❌ Sem assinatura/attestation |
| O build foi legítimo? | ❌ Sozinha não |

Por isso:

```text
SBOM
+
Provenance
+
Signature
+
Policy
```

é mais forte do que qualquer uma dessas peças isoladamente.

---
# 78. Checklist adicional de Supply Chain

## Dependências

```text
[ ] Dependências diretas são conhecidas
[ ] Dependências transitivas são inventariadas
[ ] Repositórios públicos/privados têm precedência controlada
[ ] Versões são pinadas quando apropriado
[ ] Checksums são verificados
[ ] Typosquatting é considerado
[ ] Dependency confusion é mitigada
```

## Build

```text
[ ] Build acontece em ambiente controlado
[ ] Build dependencies também são verificadas
[ ] CI possui identidade autenticável
[ ] Artefato é reproduzível quando possível
[ ] Build gera SBOM
[ ] Build gera provenance
```

## Artifact

```text
[ ] Imagem possui digest conhecido
[ ] Imagem é assinada
[ ] SBOM está associada ao digest
[ ] Provenance está associada ao digest
[ ] Artefato é armazenado em registry confiável
```

## Runtime

```text
[ ] Admission verifica assinatura
[ ] Identidade do signer é permitida
[ ] Registry é permitido
[ ] Imagem não está além da idade máxima
[ ] Packages proibidos podem ser bloqueados
[ ] Trust bundle é mantido atualizado
```

---
# 79. Novo princípio: freshness é parte da supply chain

Depois dos três vídeos, podemos acrescentar:

```text
Secure once
    ≠
Secure forever
```

Uma imagem precisa continuar sendo avaliada conforme:

```text
new CVEs
new package releases
new CA revocations
new policy
new threat intelligence
dependency EOL
runtime changes
```

Portanto:

```text
Secure Software Supply Chain
=
Build Security
+
Artifact Integrity
+
Continuous Evaluation
```

---
# 80. Modelo mental consolidado

```text
             SOURCE
                │
                ▼
        TRUSTED BUILD SYSTEM
                │
                ▼
        VERIFIED DEPENDENCIES
                │
                ▼
             MELANGE
                │
                ▼
          SIGNED PACKAGE
                │
                ▼
              apko
                │
                ▼
           MINIMAL IMAGE
                │
       ┌────────┼─────────┐
       ▼        ▼         ▼
     SBOM   Provenance   Scan
       │        │         │
       └────────┼─────────┘
                ▼
             SIGNING
                │
                ▼
        TRANSPARENCY LOG
                │
                ▼
            REGISTRY
                │
                ▼
        ADMISSION CONTROL
                │
                ▼
             RUNTIME
                │
                ▼
      CONTINUOUS RE-EVALUATION
```

A diferença para um simples Dockerfile é enorme.

Não estamos mais pensando apenas em:

```text
"como empacotar minha aplicação?"
```

Estamos pensando em:

```text
"como provar a origem, composição, integridade e política
de tudo que será executado em produção?"
```

---
