# Marco 04 — apko, Melange, reprodutibilidade, lockfiles e multi-arch

> **Origem:** V6, seções **81–100**.
>
> O conteúdo abaixo foi preservado da V6; a divisão em marcos não altera o conteúdo técnico original.

---
# 81. apko é composição, não build da aplicação

A documentação oficial deixa uma separação de responsabilidades ainda mais clara:

```text
Docker
=
build da aplicação
+
mutação do filesystem
+
composição da imagem
```

Enquanto o modelo apko/Melange procura separar:

```text
Melange
=
BUILD / PACKAGE

apko
=
COMPOSE IMAGE
```

O `apko` é descrito explicitamente como uma ferramenta de **composição**.

Ele recebe componentes já empacotados e monta a imagem final.

Isso significa que tarefas como:

```text
compilar
executar npm install
executar pip install
executar make
baixar código
gerar artefatos
```

não pertencem ao `apko.yaml`.

Elas pertencem ao processo que produz o pacote APK — por exemplo, ao pipeline do Melange.

---
# 82. apko não possui RUN arbitrário

A documentação oficial confirma um dos princípios que já havíamos destacado:

```text
apko.yaml
    ≠
Dockerfile com RUN
```

Não existe equivalente direto a:

```dockerfile
RUN curl ...
RUN apt install ...
RUN make ...
RUN chmod ...
```

O apko oferece diretivas para definir coisas como:

```text
packages
users
groups
directories
permissions
entrypoint
architectures
repositories
keyrings
```

O objetivo é reduzir lógica imperativa na etapa de composição.

Isso favorece:

```text
reproducibility
+
predictability
+
SBOM accuracy
```

---
# 83. Imagens single-layer / "flat"

A documentação define apko como uma ferramenta que cria imagens de container de **camada única**.

Dockerfiles normalmente produzem uma sequência conceitual de camadas:

```text
Layer 1
Layer 2
Layer 3
Layer 4
...
```

Com apko, o foco é compor o filesystem final:

```text
Desired Packages
       │
       ▼
Final Filesystem
       │
       ▼
Single OCI Layer
```

Isso reforça a ideia de pensar:

```text
"qual deve ser o estado final?"
```

em vez de:

```text
"quais passos devo executar para chegar lá?"
```

---
# 84. Reprodutibilidade como propriedade explícita

A documentação do apko afirma que a configuração YAML foi projetada para permitir builds reproduzíveis.

A intenção é:

```text
same config
+
same resolved inputs
=
same output
```

Esse princípio fica ainda mais forte quando adicionamos um lock file:

```text
apko.yaml
    │
    ▼
dependency resolution
    │
    ▼
apko.lock.json
    │
    ├── exact versions
    └── checksums
```

Assim distinguimos:

```text
Declarative Configuration
```

de:

```text
Pinned Resolution
```

---
# 85. O papel do apko.lock.json

A documentação atual de `rules_apko` introduz um conceito muito relevante para builds reprodutíveis:

```text
apko.lock.json
```

O lock file fixa:

```text
package versions
+
checksums
+
architecture-specific resolution
```

Fluxo:

```text
apko.yaml
     │
     ▼
apko_lock
     │
     ▼
apko.lock.json
     │
     ▼
apko_image
```

O arquivo deve ser versionado junto com o código.

Isso permite revisar mudanças como:

```diff
- packageA 1.2.0
+ packageA 1.2.1
```

em vez de deixar a resolução acontecer implicitamente a cada build.

---
# 86. Reprodutibilidade possui diferentes níveis

Podemos pensar em quatro níveis:

```text
1. Declarative
   apko.yaml

2. Resolved
   apko.lock.json

3. Hermetic Toolchain
   versão conhecida do apko/build system

4. Verified Inputs
   checksums + signing keys
```

Quanto mais níveis aplicamos, menor o espaço para:

```text
dependency drift
toolchain drift
unexpected package updates
non-deterministic resolution
```

---
# 87. Bazel + rules_apko: modo avançado

A documentação atual também apresenta integração oficial com Bazel por meio de:

```text
rules_apko
```

Objetivos principais:

```text
hermetic build
reproducibility
Bazel caching
locked dependencies
multi-architecture builds
```

Arquitetura:

```text
MODULE.bazel
      │
      ├── rules_apko
      └── apko toolchain
              │
              ▼
         apko.lock.json
              │
              ▼
          apko_image
              │
              ▼
           OCI Image
```

Esse caminho é especialmente interessante para organizações que já utilizam Bazel.

---
# 88. Cache também faz parte da eficiência da factory

Com `rules_apko`, builds subsequentes podem aproveitar o cache do Bazel.

Conceitualmente:

```text
Build 1
├── resolve
├── fetch
├── compose
└── produce

Build 2
├── cached
├── cached
├── cached
└── changed actions only
```

Isso mostra que segurança e reprodutibilidade não precisam significar necessariamente builds lentos.

---
# 89. Não misture Wolfi e Alpine

Essa é uma regra operacional importante da documentação oficial:

> **Não misture repositórios/pacotes Wolfi e Alpine no mesmo ambiente apko/Melange.**

Embora ambos utilizem APK:

```text
Wolfi APK
    ≠
Alpine APK ecosystem
```

Podemos usar:

```text
apko + Wolfi
```

ou:

```text
apko + Alpine
```

Mas não devemos criar:

```text
Wolfi repository
      +
Alpine repository
```

no mesmo build.

O mesmo princípio vale para o ambiente de build do Melange.

---
# 90. Keyring e repository são parte da trust policy

Um `apko.yaml` não define apenas pacotes.

Ele também define:

```yaml
contents:
  keyring:
    - ...
  repositories:
    - ...
  packages:
    - ...
```

Isso significa que a própria configuração declara:

```text
WHERE packages may come from
+
WHICH signing keys are trusted
+
WHICH packages are allowed into the image
```

Podemos pensar nisso como uma pequena policy de supply chain:

```text
Trusted Repositories
        │
        ▼
Trusted Keys
        │
        ▼
Allowed Packages
        │
        ▼
Image
```

---
# 91. Pacote unsigned: Melange vs apko

Uma nuance importante da documentação:

```text
Melange
```

não obriga tecnicamente que todo pacote seja assinado.

Porém, assinatura é recomendada.

Já:

```text
apko
```

por padrão pode falhar ao utilizar pacotes sem assinatura confiável.

Portanto, o modelo recomendado permanece:

```text
Melange
    │
    ▼
Signed APK
    │
    ▼
Trusted keyring
    │
    ▼
apko
```

Assinar o pacote permite validar:

```text
producer identity
+
package integrity
```

---
# 92. Multi-architecture como parte do design

Melange e apko possuem suporte nativo a múltiplas arquiteturas.

Exemplo conceitual:

```text
Source
   │
   ▼
Melange
   ├── amd64 APK
   └── arm64 APK
         │
         ▼
        apko
   ├── amd64 OCI image
   └── arm64 OCI image
```

Isso é especialmente relevante em ambientes cloud-native com:

```text
x86_64
+
ARM64
```

como clusters Kubernetes mistos ou workloads executados em instâncias Graviton.

---
# 93. Build-time e runtime dependencies no Melange

A documentação do Melange separa explicitamente três áreas:

```text
package
environment
pipeline
```

## package

Define metadata e dependências de runtime.

```yaml
package:
  dependencies:
    runtime:
      - php
      - php-curl
```

## environment

Define o que é necessário **somente para construir**:

```text
compiler
git
composer
curl
headers
build tooling
```

## pipeline

Define como produzir o conteúdo do pacote.

Essa separação materializa:

```text
Build dependencies
      ≠
Runtime dependencies
```

e ajuda a evitar build tools dentro da imagem final.

---
# 94. O pacote da aplicação deve carregar suas runtime dependencies

Um detalhe muito útil da demo oficial:

Se o APK da aplicação declara corretamente:

```yaml
dependencies:
  runtime:
    - php
    - php-curl
```

o `apko.yaml` não precisa repetir essas dependências manualmente.

Podemos pensar assim:

```text
Application APK
      │
      ├── app files
      └── runtime dependency metadata
               │
               ▼
              apk
               │
               ▼
         dependency closure
```

Isso melhora encapsulamento e reduz duplicação de configuração.

---
# 95. Package repositories locais também são primeira classe

O apko pode consumir pacotes gerados internamente pelo Melange.

Exemplo conceitual:

```yaml
repositories:
  - https://packages.wolfi.dev/os
  - '@local /work/packages'
```

Então podemos compor:

```text
Wolfi packages
      +
Internal application APK
      │
      ▼
    apko
```

Isso é exatamente o modelo necessário para uma software factory interna.

---
# 96. Estrutura de um repositório APK interno

A documentação de troubleshooting deixa clara a importância do índice por arquitetura.

Exemplo:

```text
packages/
├── aarch64/
│   ├── APKINDEX.tar.gz
│   └── app.apk
└── x86_64/
    ├── APKINDEX.tar.gz
    └── app.apk
```

Sem:

```text
APKINDEX.tar.gz
```

o apko pode não conseguir resolver os pacotes do repositório local.

Isso é importante quando usamos:

```text
Melange
→ Artifactory/Nexus/custom APK repo
→ apko
```

---
# 97. Troubleshooting apko

A documentação apresenta três causas muito comuns para falha na resolução de pacotes.

## Pacote não existe

```text
ERROR: unable to select packages:
app (no such package)
```

Verifique:

```text
package name
repository configured
repository reachable
```

## Diretório local não está montado

Quando usamos Melange + apko em containers:

```text
host packages
     │
     X
apko container
```

o build não encontrará os artefatos.

## APKINDEX ausente

Mesmo que o APK exista, o repository index também precisa existir.

### Debug

```shell
apko build --debug ...
```

é a primeira ferramenta de diagnóstico.

---
# 98. Troubleshooting Melange

Para pipelines Melange, a documentação recomenda ativar tracing no trecho relevante:

```sh
set -x
```

Exemplo:

```yaml
pipeline:
  - runs: |
      set -x
      ...
```

Erros comuns incluem:

```text
missing build dependencies
missing commands
multi-architecture emulation unavailable
```

---
# 99. QEMU e builds multi-arch

Em hosts Linux, builds para outra arquitetura podem depender de emulação user-space.

Exemplo:

```text
x86_64 host
      │
      ▼
QEMU/binfmt
      │
      ▼
ARM64 build
```

Docker Desktop normalmente já configura suporte de arquiteturas adicionais.

Em Linux puro, isso pode exigir registro de handlers `binfmt`.

Esse detalhe é importante para pipelines que prometem:

```text
amd64
+
arm64
```

mas executam sobre runners de uma única arquitetura.

---
# 100. OCI compliance

As imagens produzidas pelo apko são OCI compliant.

Isso significa que o resultado não depende de um runtime específico.

Pode ser consumido por ecossistemas compatíveis com OCI, como:

```text
Docker
containerd
CRI-O
Kubernetes
ECS
registries OCI
```

O apko muda **como construímos** a imagem.

Não muda o padrão usado para executá-la.

---
