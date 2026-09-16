# Marco 01 — Fundamentos: Dockerfile, apko, Melange, SBOM e Software Supply Chain

> **Origem:** V6, seções **1–37**.
>
> O conteúdo abaixo foi preservado da V6; a divisão em marcos não altera o conteúdo técnico original.

---
# 1. O problema do Dockerfile tradicional

Um Dockerfile oferece bastante flexibilidade:

```dockerfile
FROM alpine:3.22

RUN apk add --no-cache curl

COPY ./app /usr/local/bin/app

ENTRYPOINT ["/usr/local/bin/app"]
```

O problema é que instruções como:

```dockerfile
RUN ...
COPY ...
ADD ...
```

permitem introduzir praticamente qualquer conteúdo na imagem.

Por exemplo:

```dockerfile
COPY ./binary /app
```

O container sabe que existe um arquivo chamado `/app`.

Porém, nem sempre existe metadata suficiente para responder:

- De onde esse binário veio?
- Qual é sua versão?
- Quais bibliotecas estão embutidas nele?
- Qual versão dessas bibliotecas foi utilizada?
- Há alguma CVE associada?
- Quem produziu esse artefato?
- Esse binário foi alterado depois do build?

Esse é um dos problemas de **software supply chain** abordados no vídeo.

---
# 2. A ideia do apko

O `apko` é uma ferramenta de composição de imagens.

Em vez de oferecer um modelo como:

```dockerfile
RUN
COPY
ADD
```

o apko trabalha principalmente com **pacotes APK conhecidos**.

Exemplo conceitual:

```yaml
contents:
  repositories:
    - https://dl-cdn.alpinelinux.org/alpine/edge/main

  packages:
    - alpine-base
    - nginx
```

A imagem passa a ser composta a partir de componentes registrados pelo package manager.

Isso permite manter informações sobre:

```text
pacote
 ├── nome
 ├── versão
 ├── dependências
 ├── origem
 └── metadata
```

A consequência é uma imagem muito mais previsível.

---
# 3. Por que isso ajuda os scanners?

Ferramentas de análise como:

- Trivy;
- Snyk;
- scanners SCA;
- scanners de imagens de container;

dependem de metadata para identificar componentes.

Em uma imagem construída com arquivos arbitrariamente copiados:

```text
Container
├── /app
├── /lib/custom.so
└── /usr/local/bin/tool
```

o scanner pode não saber exatamente de onde esses componentes vieram.

Quando os componentes são tratados como pacotes:

```text
Container
├── package A 1.2.3
├── package B 4.5.6
└── package C 7.8.9
```

existe muito mais contexto disponível para análise.

O ponto central do vídeo é:

> Quanto mais metadata houver sobre os componentes da imagem, maior será a visibilidade da ferramenta de segurança.

---
# 4. O papel do Melange

O `Melange` resolve outra parte do problema.

Se o apko monta imagens usando pacotes APK, alguém precisa transformar nossa aplicação em um pacote.

Esse é o papel do Melange.

Fluxo simplificado:

```text
Código-fonte
     │
     ▼
  Melange
     │
     ▼
Pacote APK
     │
     ▼
   apko
     │
     ▼
Imagem OCI
```

O Melange funciona como um builder orientado a pipelines.

A configuração pode conter:

```text
metadata
environment
pipeline
subpackages
```

Exemplo conceitual:

```yaml
package:
  name: my-app
  version: 1.0.0

pipeline:
  - uses: fetch
  - uses: configure
  - uses: make
  - uses: make/install
```

---
# 5. Build como pipeline

Um ponto interessante do Melange é tratar o build de maneira semelhante a sistemas como GitHub Actions.

As etapas podem executar ações como:

```text
download
   │
   ▼
checksum SHA-256
   │
   ▼
extract
   │
   ▼
compile
   │
   ▼
install
   │
   ▼
package
```

Se uma etapa falhar:

```text
Pipeline
   │
   ├── fetch       ✅
   ├── checksum    ✅
   ├── compile     ❌
   │
   └── build falha
```

Isso aumenta a previsibilidade do processo.

---
# 6. Verificação de integridade

No exemplo apresentado no vídeo, o processo de download inclui verificação de SHA-256.

Conceitualmente:

```text
Download
   │
   ▼
SHA-256 esperado
   │
   ▼
Comparação
   │
   ├── igual     → continua
   │
   └── diferente → falha
```

Isso ajuda a proteger contra alterações inesperadas no artefato utilizado durante o build.

---
# 7. Assinatura dos pacotes

O Melange também permite assinar pacotes APK.

O fluxo demonstrado envolve:

```text
Melange
   │
   ▼
gera chave
   │
   ▼
build do APK
   │
   ▼
assinatura
```

Posteriormente, o repositório APK também pode possuir um índice assinado.

Arquitetura:

```text
Application
    │
    ▼
Melange
    │
    ▼
Signed APK
    │
    ▼
APK Repository
    │
    ▼
Signed Index
    │
    ▼
apko
```

Isso adiciona uma camada de confiança ao processo.

---
# 8. Assinatura de pacote ≠ assinatura de imagem

O vídeo faz uma distinção importante.

O Melange utiliza assinatura no contexto dos pacotes APK.

Já para a imagem OCI completa, o vídeo menciona:

```text
Cosign
  +
Sigstore
```

Portanto podemos pensar em dois níveis:

```text
Pacote
  └── assinatura APK

Imagem OCI
  └── assinatura Cosign/Sigstore
```

Essa distinção é importante em uma software supply chain madura.

---
# 9. SBOM

## Software Bill of Materials

Uma **SBOM** funciona como uma lista de materiais do software.

Exemplo:

```text
my-container:1.0

├── musl 1.x
├── openssl 3.x
├── ca-certificates
├── my-app 1.0
└── libxyz 2.x
```

O vídeo destaca uma ideia especialmente importante:

> A SBOM é mais confiável quando é produzida durante o processo de construção, em vez de ser reconstruída apenas depois que a imagem já existe.

---
# 10. Build-time SBOM vs scan posterior

Modelo tradicional:

```text
Build
  │
  ▼
Imagem
  │
  ▼
Scanner
  │
  ▼
"Tentar descobrir o que existe"
```

Modelo orientado à supply chain:

```text
Build
  │
  ├── componentes conhecidos
  ├── versões conhecidas
  ├── dependências conhecidas
  └── origem conhecida
       │
       ▼
      SBOM
       │
       ▼
     Imagem
```

A diferença é importante.

No segundo modelo, o inventário é conhecido **antes de a imagem chegar ao runtime**.

---
# 11. Imagem pequena não significa automaticamente imagem segura

Esse é um dos principais insights do vídeo.

Considere:

```dockerfile
FROM scratch

COPY app /app

ENTRYPOINT ["/app"]
```

Essa imagem pode ser extremamente pequena.

Porém:

```text
small image ≠ complete visibility
```

O scanner pode enxergar apenas:

```text
/app
```

sem necessariamente saber:

```text
OpenSSL version?
libc version?
embedded libraries?
dependencies?
origin?
```

Portanto:

```text
imagem mínima
      +
metadata
      +
SBOM
      +
assinatura
      +
scan
```

é muito mais interessante do que simplesmente:

```text
imagem mínima
```

---
# 12. Scratch vs Distroless vs apko

## Scratch

```dockerfile
FROM scratch
```

### Vantagens

- extremamente pequeno;
- praticamente nenhuma ferramenta extra;
- superfície de ataque reduzida.

### Limitação

A rastreabilidade depende da forma como o binário foi produzido.

---

## Distroless

Mantém apenas componentes necessários ao runtime.

Exemplo conceitual:

```text
application
runtime libraries
certificates
```

Sem:

```text
shell
package manager
curl
wget
compiler
debug tools
```

---

## apko

O apko segue uma filosofia semelhante a distroless, mas com composição declarativa baseada em pacotes APK.

O vídeo descreve apko + Melange como uma evolução conceitual da abordagem distroless.

---
# 13. Um insight importante sobre scanners

Imagine um binário estaticamente compilado:

```text
app
 ├── OpenSSL
 ├── libc
 └── outras libs
```

Depois:

```dockerfile
FROM scratch

COPY app /app
```

O filesystem da imagem pode conter apenas:

```text
/app
```

Para um scanner baseado apenas no filesystem, entender quais bibliotecas estão embutidas nesse binário pode ser mais difícil.

Com um pipeline baseado em pacotes e SBOM:

```text
app
├── openssl 3.x
├── libc
└── xyz
```

essa informação pode ser explicitamente registrada.

---
# 14. Redução da superfície de ataque

Outro benefício apresentado é a construção de imagens extremamente pequenas.

O vídeo demonstra exemplos muito menores que imagens tradicionais.

Mas o benefício mais relevante não é apenas:

```text
140 MB → 30 MB → 8 MB → 1 MB
```

O benefício é reduzir:

```text
pacotes
comandos
bibliotecas
binários
shells
ferramentas
```

disponíveis para um eventual atacante.

---
# 15. Imagens sem shell

Uma das ideias discutidas é eliminar o shell das imagens de aplicação.

Imagem tradicional:

```text
/bin/sh
/bin/bash
curl
wget
apk
ps
grep
sed
...
```

Imagem minimalista:

```text
/app
/lib
/certs
```

Com isso, mesmo que um atacante consiga executar código dentro do container, ele encontra menos ferramentas disponíveis.

---
# 16. Mas como fazer troubleshooting?

Esse é um ponto importante.

Remover ferramentas da imagem não significa abandonar troubleshooting.

Em Kubernetes podemos separar:

```text
Application Container
        │
        ├── minimal
        ├── sem shell
        └── sem tooling

Debug Container
        │
        ├── shell
        ├── curl
        ├── tcpdump
        ├── dig
        └── ferramentas de diagnóstico
```

Um exemplo de abordagem moderna é usar:

```bash
kubectl debug
```

para adicionar um container de troubleshooting quando necessário.

---
# 17. Runtime image vs Debug image

Essa separação é muito importante.

## Runtime

Deve ter apenas o necessário para executar:

```text
application
runtime
libraries
certificates
```

## Debug

Pode possuir:

```text
bash
curl
dig
nslookup
tcpdump
netstat
ip
ps
strace
kubectl
aws-cli
```

Isso evita transformar toda aplicação em uma caixa de ferramentas.

---
# 18. O princípio do mínimo necessário

A ideia pode ser resumida como:

```text
Runtime Image
    =
Aplicação
    +
Somente dependências necessárias
```

Não:

```text
Runtime Image
    =
Aplicação
+ Shell
+ Debug tools
+ Build tools
+ Package manager
+ Utilitários
+ Ferramentas que talvez sejam usadas algum dia
```

---
# 19. Comparação com Dockerfile tradicional

## Dockerfile

```text
Source
   │
   ▼
Dockerfile
   │
   ├── RUN
   ├── COPY
   ├── ADD
   └── scripts
   │
   ▼
Image
```

Alta flexibilidade.

Porém, também existe mais espaço para introdução de componentes arbitrários.

---

## Melange + apko

```text
Source
   │
   ▼
Melange
   │
   ▼
APK
   │
   ├── metadata
   ├── version
   ├── dependencies
   └── signature
   │
   ▼
apko
   │
   ▼
OCI Image
```

Menos liberdade arbitrária.

Mais previsibilidade.

---
# 20. Restrição como feature de segurança

Normalmente pensamos:

> quanto mais flexível uma ferramenta, melhor.

Em segurança, isso nem sempre é verdade.

Dockerfile:

```dockerfile
RUN qualquer-coisa
```

oferece uma superfície enorme de possibilidades.

apko restringe deliberadamente o processo.

Essa limitação ajuda a tornar o resultado mais previsível.

Podemos pensar em:

```text
Flexibilidade
      ↓

Previsibilidade
      ↑

Reprodutibilidade
      ↑

Auditabilidade
      ↑
```

---
# 21. Software Factory Segura

O vídeo menciona o uso desse modelo dentro de uma **secure software factory**.

Uma arquitetura corporativa poderia ser:

```text
Git Repository
      │
      ▼
CI Pipeline
      │
      ▼
Melange
      │
      ▼
Signed APK
      │
      ▼
Artifact Repository
      │
      ▼
apko
      │
      ▼
OCI Image
      │
      ├── SBOM
      ├── Scan
      └── Signature
      │
      ▼
Container Registry
      │
      ▼
Admission Policy
      │
      ▼
Kubernetes
```

---
# 22. Artifact Repository

No vídeo é criado um repositório APK local para demonstração.

Em ambiente empresarial isso provavelmente seria substituído por algo como:

```text
JFrog Artifactory
Nexus
Artifact Registry
ou outro repositório corporativo
```

O próprio vídeo menciona Artifactory como uma opção para gerenciamento de repositórios APK.

---
# 23. CI/CD

O vídeo também comenta automação por GitHub Actions.

Um pipeline moderno poderia executar:

```text
Commit
   │
   ▼
Build
   │
   ▼
Package
   │
   ▼
SBOM
   │
   ▼
Vulnerability Scan
   │
   ▼
Image Build
   │
   ▼
Image Sign
   │
   ▼
Registry
```

---
# 24. Assinatura e provenance

Uma evolução natural desse modelo é incluir provenance.

Exemplo:

```text
Artifact
├── digest
├── builder
├── source repository
├── commit SHA
├── timestamp
├── SBOM
├── signature
└── build metadata
```

Assim é possível responder:

```text
Quem construiu?

De qual código?

Qual commit?

Quando?

Com quais dependências?

Qual era o digest?

Foi alterado?
```

---
# 25. Modelo completo de Supply Chain

Podemos representar a filosofia apresentada no vídeo assim:

```text
Source Code
    │
    ▼
Controlled Build
    │
    ▼
Versioned Artifact
    │
    ├── metadata
    ├── checksum
    ├── dependencies
    └── signature
    │
    ▼
Minimal Container Image
    │
    ├── only required dependencies
    ├── no shell when possible
    ├── no build tools
    └── minimal attack surface
    │
    ▼
SBOM
    │
    ▼
Vulnerability Scan
    │
    ▼
Image Signature
    │
    ▼
Registry
    │
    ▼
Admission Control
    │
    ▼
Runtime
```

---
# 26. O que realmente queremos saber sobre uma imagem?

Uma boa imagem de container deveria permitir responder:

```text
O que existe dentro dela?

Por que esse componente existe?

De onde ele veio?

Qual versão está instalada?

Quais dependências existem?

Existe alguma vulnerabilidade conhecida?

Quem construiu a imagem?

Qual código originou o artefato?

O conteúdo foi alterado?

A imagem está assinada?
```

Esse é um objetivo muito maior do que simplesmente:

```text
"minha imagem tem poucos MB"
```

---
# 27. Dockerfile ainda é ruim?

Não necessariamente.

Um Dockerfile moderno pode incorporar várias dessas práticas:

```dockerfile
FROM golang:1.25 AS builder

WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 go build -o /out/app ./cmd/app


FROM scratch

COPY --from=builder /out/app /app

USER 65532

ENTRYPOINT ["/app"]
```

Isso já oferece:

- multi-stage build;
- redução de ferramentas no runtime;
- imagem pequena;
- non-root;
- separação entre build e execução.

Porém, supply-chain security exige outras camadas:

```text
Dockerfile
   +
SBOM
   +
scan
   +
signature
   +
provenance
   +
policy
```

---
# 28. Multi-stage build continua importante

Mesmo sem utilizar apko/Melange, um dos princípios permanece:

```text
Build Environment
       │
       ▼
     Artifact
       │
       ▼
Runtime Environment
```

Ferramentas como:

```text
gcc
go
npm
maven
gradle
git
curl
```

idealmente ficam apenas no estágio de build.

---
# 29. Non-root continua importante

Minimalismo não substitui:

```dockerfile
USER 65532
```

ou configuração equivalente.

Uma imagem minimalista executada como root continua tendo riscos.

Portanto:

```text
Minimal Image
     +
Non-root
     +
Read-only filesystem
     +
Dropped capabilities
     +
Seccomp
     +
AppArmor/SELinux
```

forma uma defesa muito mais completa.

---
# 30. Boas práticas complementares

Além do modelo apresentado no vídeo, uma estratégia moderna de container security normalmente combina:

```text
Minimal image
Non-root
Multi-stage build
SBOM
Vulnerability scan
Image signing
Provenance
Digest pinning
Admission policies
Read-only filesystem
Drop Linux capabilities
Secrets fora da imagem
Network policies
Runtime monitoring
```

---
# 31. Um ponto crítico: "100% scannable"

No vídeo existe a afirmação de que o modelo baseado em pacotes torna a imagem completamente visível aos scanners.

Essa ideia deve ser interpretada com cuidado.

Na prática:

```text
mais metadata
     ↓
melhor identificação
     ↓
melhores scans
```

Mas isso não significa necessariamente:

```text
100% das vulnerabilidades detectadas
```

Um scanner continua dependendo de:

- qualidade da SBOM;
- qualidade da base de CVEs;
- identificação correta de componentes;
- dependências da linguagem;
- bibliotecas incorporadas;
- vulnerabilidades ainda desconhecidas;
- qualidade das regras do scanner.

Portanto o insight correto é:

> Maximizar a transparência da imagem para ferramentas de segurança.

---
# 32. Quando uma imagem precisa de ferramentas?

Nem toda imagem deve ser distroless.

Uma imagem criada especificamente para troubleshooting pode precisar de:

```text
kubectl
helm
aws-cli
curl
wget
dig
nslookup
tcpdump
netstat
ip
jq
bash
```

Nesse caso:

```text
remover shell
```

seria contraproducente.

O princípio correto não é:

> Toda imagem deve ser mínima ao extremo.

O princípio é:

> Toda imagem deve conter apenas o necessário para cumprir sua função.

---
# 33. Application Image vs Tooling Image

## Application Image

Objetivo:

```text
executar aplicação
```

Características desejáveis:

```text
minimal
non-root
sem shell
sem package manager
sem compiler
sem ferramentas desnecessárias
```

---

## Tooling / Troubleshooting Image

Objetivo:

```text
diagnosticar ambientes
```

Características necessárias:

```text
shell
network tools
cloud CLI
Kubernetes CLI
debug utilities
```

Nesse caso, segurança deve vir principalmente de:

```text
controle de acesso
RBAC
IAM
network policies
capabilities
runtime restrictions
image signing
scanning
```

e não simplesmente da remoção das ferramentas.

---
# 34. Principal aprendizado

O maior insight do vídeo pode ser resumido assim:

```text
Container Security
      ≠
apenas imagem pequena
```

É muito mais próximo de:

```text
Container Security
      =
Minimal Runtime
      +
Traceable Components
      +
Known Dependencies
      +
SBOM
      +
Scanning
      +
Signing
      +
Provenance
      +
Runtime Controls
```

---
# 35. Evolução mental

Podemos visualizar a evolução:

```text
Dockerfile simples
       │
       ▼
Multi-stage Dockerfile
       │
       ▼
Minimal image
       │
       ▼
Distroless / Scratch
       │
       ▼
Wolfi / pacotes rastreáveis
       │
       ▼
SBOM
       │
       ▼
Artifact signing
       │
       ▼
Image signing
       │
       ▼
Provenance
       │
       ▼
Admission policies
       │
       ▼
Secure Software Supply Chain
```

---
# 36. Resumo das ferramentas

| Ferramenta | Papel |
|---|---|
| Dockerfile | Construção tradicional da imagem |
| Wolfi | Conjunto/distribuição de pacotes voltado a containers e supply chain |
| Melange | Criação de pacotes APK |
| apko | Composição declarativa da imagem |
| APK | Formato de pacote utilizado |
| SBOM | Inventário de componentes |
| Trivy / Snyk | Análise de vulnerabilidades |
| Cosign | Assinatura de imagens |
| Sigstore | Infraestrutura de assinatura |
| Artifactory | Armazenamento de artefatos |
| kubectl debug | Troubleshooting sem colocar ferramentas na aplicação |

---
# 37. Fluxo final recomendado

```text
Developer
    │
    ▼
Git
    │
    ▼
CI
    │
    ├── Build
    ├── Tests
    ├── Dependency verification
    └── Package
         │
         ▼
       Artifact
         │
         ├── Version
         ├── SHA
         ├── Metadata
         └── Signature
              │
              ▼
          Image Build
              │
              ▼
             SBOM
              │
              ▼
         Vulnerability Scan
              │
              ▼
          Image Signature
              │
              ▼
           Registry
              │
              ▼
        Admission Policy
              │
              ▼
          Kubernetes
```

---
