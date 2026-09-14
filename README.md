# image-base

Imagens base **distroless multi-arquitetura** (`amd64`/`arm64`) para **Java, Python, Go, Node.js e .NET** — **17 definições** de runtime/build no catálogo, **16 no lote automático**; a disponibilidade depende dos gates de cada release. Construídas com [apko](https://github.com/chainguard-dev/apko) + [melange](https://github.com/chainguard-dev/melange) (pacotes [Wolfi](https://github.com/wolfi-dev), sem Dockerfile), escaneadas com [Trivy](https://github.com/aquasecurity/trivy) e publicadas no **Amazon ECR** via workflows reusáveis do GitHub Actions, com autenticação por OIDC (sem chave de acesso estática).

## Índice

- [image-base](#image-base)
  - [Índice](#índice)
  - [O que é uma imagem Distroless?](#o-que-é-uma-imagem-distroless)
  - [Imagens disponíveis](#imagens-disponíveis)
  - [Pré-requisitos](#pré-requisitos)
  - [Como usar](#como-usar)
  - [Estrutura do repositório](#estrutura-do-repositório)
  - [Como as imagens são compostas](#como-as-imagens-são-compostas)
  - [O pacote `image-base-ca-certificates` (melange)](#o-pacote-image-base-ca-certificates-melange)
  - [Pipeline de CI/CD (GitHub Actions)](#pipeline-de-cicd-github-actions)
  - [Checks obrigatórios, revisão e endurecimento (M12/M16)](#checks-obrigatórios-revisão-e-endurecimento-m12m16)
  - [Gate de promoção para stable (canário de soak)](#gate-de-promoção-para-stable-canário-de-soak)
  - [Recuperação de stable (runbook, M15)](#recuperação-de-stable-runbook-m15)
  - [Verificação: assinatura e build provenance](#verificação-assinatura-e-build-provenance)
  - [Configuração dos workflows reusáveis](#configuração-dos-workflows-reusáveis)
  - [Build local](#build-local)
  - [Conclusão](#conclusão)

As fronteiras de responsabilidade e as regras de organização estão em
[`docs/repository-architecture.md`](docs/repository-architecture.md). O índice
de automação fica em [`scripts/README.md`](scripts/README.md). Para contribuir,
veja [`CONTRIBUTING.md`](CONTRIBUTING.md); o índice de documentação está em
[`docs/README.md`](docs/README.md).

## O que é uma imagem Distroless?

<p align="center">
  <img src="./img/distroless-logo.svg" alt="Distroless logo" width="220" />
</p>

Imagens "Distroless" contêm apenas o aplicativo e suas dependências de tempo de execução — sem gerenciador de pacotes, shell ou qualquer outra ferramenta que normalmente vem junto de uma distribuição Linux padrão. Restringir o container de produção precisamente ao que a aplicação precisa reduz a superfície de ataque e é uma prática recomendada, principalmente em ambientes produtivos.

> Como não há shell nem ferramentas de troubleshooting na imagem, depurar um pod rodando distroless exige um mecanismo de debug fora da imagem da aplicação (ex.: um [Container Efêmero](https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/#ephemeral-container) anexado ao pod). O toolkit de referência está isolado em [`troubleshooting/`](troubleshooting/README.md), com ciclo de vida próprio; ele não integra as imagens base nem o pipeline de publicação delas.

A composição e os controles atuais são:

- **Composição declarativa em camadas por origem:** Apko resolve packages usando um lock e compõe OCI sem Dockerfile de base. `layering.strategy: origin`, com orçamento 10, permite até 11 camadas finais no Apko fixado; medidas e limites em [composição](docs/image-composition.md).
- **Superfície de ataque mínima:** `distroless/image-base.yaml` (herdado por todo `frameworks/<nome>.yaml`) só traz `ca-certificates-bundle`, `tzdata` e `image-base-ca-certificates` — **sem `wolfi-base`**, que traria `apk-tools` e `busybox` (shell) de brinde via dependência transitiva. Cada `frameworks/<nome>.yaml` declara os pacotes de sua variante (ex.: `openjdk-21-jre` para Java runtime). Todas as imagens rodam como usuário non-root por padrão (`spring` ou `appuser`, uid/gid 10000). As variantes `-dev` trazem o toolchain e shell para o estágio de build; as variantes de runtime usam somente os pacotes necessários à execução. O consumidor deve escolher a variante runtime final; `dotnet8` continua com SDK, sem contrato e fora do lote automático.
- **Cadeia de suprimentos (supply chain) rastreável:** os pacotes vêm do repositório rolling-release do [Wolfi](https://github.com/wolfi-dev) (assinado e mantido pela Chainguard); o único pacote que não vem de lá (`image-base-ca-certificates`) é compilado neste próprio repositório via melange, com índice assinado por uma chave efêmera gerada a cada build. Não existe imagem base de terceiros nem `FROM` de uma tag de procedência desconhecida.
- **Signing key Wolfi — defense-in-depth:** o keyring explícito usa [chave pública e pin locais](melange/keys/), preflight offline, monitor de drift e [rotação por revisão humana](docs/wolfi-signing-key.md). O Apko ainda pode adicionar chaves via discovery da origem: o keyring não é um conjunto de confiança exclusivo. Veja a [limitação de tooling P1-03](specs/2026-09-13-wolfi-signing-key/evidence.md).
- **SBOM e scan em todo build:** o `apko` gera um SBOM (SPDX) a cada build, e o [Trivy](#pipeline-de-cicd-github-actions) escaneia a imagem localmente antes de qualquer push — uma CVE `CRITICAL`/`HIGH`/`MEDIUM`/`LOW` **com correção disponível** bloqueia o artifact aprovado e a publicação daquele framework (veja [`ignore-unfixed`](#pipeline-de-cicd-github-actions)).

## Imagens disponíveis

| Linguagem | Versão | Pacote(s) Wolfi | Imagem (repositório ECR) | Usuário | Uso |
|---|---|---|---|---|---|
| Java | 21 (LTS) | `openjdk-21-jre` | `image-base-java21` | `spring` | runtime final (sem `javac`/jmods/shell) |
| Java | 21 (LTS) | `openjdk-21`, `busybox` | `image-base-java21-dev` | `spring` | build stage (JDK completo + shell p/ mvnw/gradlew) |
| Java | 25 (LTS) | `openjdk-25-jre` | `image-base-java25` | `spring` | runtime final (sem `javac`/jmods/shell) |
| Java | 25 (LTS) | `openjdk-25`, `busybox` | `image-base-java25-dev` | `spring` | build stage (JDK completo + shell p/ mvnw/gradlew) |
| Python | 3.13 | `python-3.13` | `image-base-python3-13` | `appuser` | runtime final |
| Python | 3.14 | `python-3.14` | `image-base-python3-14` | `appuser` | runtime final |
| Go | 1.25 | *(nenhum — só a base distroless)* | `image-base-go1-25` | `appuser` | runtime final (binário estático, sem toolchain/shell) |
| Go | 1.25 | `go-1.25`, `busybox` | `image-base-go1-25-dev` | `appuser` | build stage (toolchain completo + shell) |
| Go | 1.26 | *(nenhum — só a base distroless)* | `image-base-go1-26` | `appuser` | runtime final (binário estático, sem toolchain/shell) |
| Go | 1.26 | `go-1.26`, `busybox` | `image-base-go1-26-dev` | `appuser` | build stage (toolchain completo + shell) |
| Node.js | 22 (LTS) | `nodejs-22` | `image-base-nodejs22` | `appuser` | runtime final (sem npm/shell) |
| Node.js | 22 (LTS) | `nodejs-22`, `npm`, `busybox` | `image-base-nodejs22-dev` | `appuser` | build stage (tem npm e shell) |
| Node.js | 24 (LTS) | `nodejs-24` | `image-base-nodejs24` | `appuser` | runtime final (sem npm/shell) |
| Node.js | 24 (LTS) | `nodejs-24`, `npm`, `busybox` | `image-base-nodejs24-dev` | `appuser` | build stage (tem npm e shell) |
| .NET | 8 (LTS) | `dotnet-8-sdk` | `image-base-dotnet8` | `appuser` | runtime final (SDK completo — ainda não separado, ver M07). **Fora do lote padrão** ([ADR-0001](docs/adr/0001-dotnet8-fora-do-lote-padrao.md)): o Wolfi não publica a correção que o scan exige; só builda por `workflow_dispatch` e nunca teve `stable` |
| .NET | 10 (LTS) | `aspnet-10-runtime` | `image-base-dotnet10` | `appuser` | runtime final (ASP.NET Core + .NET runtime, sem SDK/shell) |
| .NET | 10 (LTS) | `dotnet-10-sdk`, `busybox` | `image-base-dotnet10-dev` | `appuser` | build stage (SDK completo + shell, para `dotnet publish`) |

**⚠️ Migração (09/09/2026):** `image-base-go1-26`, `image-base-dotnet10` e `image-base-java21` deixaram de conter o toolchain de build (Go, SDK do .NET, JDK) e passaram a ser runtime-only, seguindo o mesmo padrão que `image-base-nodejs22`/`nodejs24` já usavam. Quem consumia essas três tags para **compilar** (não só rodar) precisa migrar para as novas tags `-dev` (`image-base-go1-26-dev`, `image-base-dotnet10-dev`, `image-base-java21-dev`), que mantêm o toolchain completo — veja os exemplos de Dockerfile multi-stage abaixo. Naquela data, `go1-25`, `dotnet8` e `java25` ainda não tinham a separação; o estado atual está na tabela e na atualização de 10/09 abaixo.

**⚠️ Migração (10/09/2026):** o mesmo movimento para `image-base-go1-25` e `image-base-java25` — passaram a ser runtime-only (`go1-25` só a base; `java25` com `openjdk-25-jre`). Quem compilava com essas tags deve usar `image-base-go1-25-dev`/`image-base-java25-dev` no estágio de build. Dos frameworks do catálogo, só `dotnet8` continua sem a separação.

Referência completa de uma imagem: `<registro-ecr>/image-base-<framework>:<tag>`, onde `<registro-ecr>` é `<conta-aws>.dkr.ecr.<região>.amazonaws.com`.

Cada publicação recebe uma **build tag imutável** `<ddmmaa>-<hhmm>-r<run_id>-a<tentativa>`. **`stable` é um ponteiro mutável**, atribuído somente após promoção com soak, verificações, re-scan e read-back; nem todo build recebe essa tag. O **OCI index digest** identifica o artifact multiarch exato. As tags históricas `ddmmaa-hhmm` continuam reconhecidas pelo seletor. O [Consumer Verification Contract](docs/consumer-verification-contract.md) define os três níveis de consumo e os comandos de verificação.

## Pré-requisitos

- **Consumir as imagens:** um cliente OCI (`docker`, `podman`, `nerdctl`...) autenticado no ECR (`aws ecr get-login-password`).
- **Build/CI local:** Docker Engine com suporte a `--privileged` (usado pelo melange) — nada de `apko`/`melange` instalado à parte, o [`Makefile`](Makefile) roda os dois via `docker run`. Não precisa de credencial AWS para build local (o OCI é construído e carregado no Docker local).
- **CI (push real):** uma role assumível via OIDC com permissões explícitas de execução e provisionamento nos ECRs autorizados — veja o [contrato IAM P1-04 e templates propostos](docs/iam-permission-contract.md). A proposta ainda exige validação/aplicação por Cloud/IAM.

## Como usar

Os exemplos com `stable` abaixo são de conveniência. Para deployment reproduzível
e consumo auditado, fixe e verifique o **OCI index digest** de cada estágio
conforme o [contrato canônico](docs/consumer-verification-contract.md).

```bash
aws ecr get-login-password --region <região> | docker login --username AWS --password-stdin <registro-ecr>
docker pull <registro-ecr>/image-base-nodejs24:stable
```

Todas as imagens já vêm com `work-dir: /app` e rodando como usuário non-root (`spring` para Java, `appuser` para as demais). Runtimes cujo artefato final já vem pronto de outro lugar (ex.: um binário Go compilado localmente) podem copiar direto:

```Dockerfile
FROM <registro-ecr>/image-base-go1-26:stable
COPY --chown=appuser:appuser ./app /app/app
CMD ["/app/app"]
```

Para Go, .NET e Java, o normal é compilar dentro do próprio pipeline — use a variante `-dev` só no estágio de build (tem o toolchain e `busybox`, para os wrappers tipo `mvnw`/`gradlew` funcionarem) e a variante final (sem toolchain/shell) no estágio de runtime:

```Dockerfile
# Go: binário estático, sem toolchain no runtime
FROM <registro-ecr>/image-base-go1-26-dev:stable AS build
WORKDIR /app
COPY --chown=appuser:appuser . .
RUN go build -o server .

FROM <registro-ecr>/image-base-go1-26:stable
COPY --chown=appuser:appuser --from=build /app/server /app/server
CMD ["/app/server"]
```

```Dockerfile
# .NET: publica no estágio SDK, roda no runtime ASP.NET (sem SDK)
FROM <registro-ecr>/image-base-dotnet10-dev:stable AS build
WORKDIR /app
COPY --chown=appuser:appuser . .
RUN dotnet publish -c Release -o /app/out --self-contained false

FROM <registro-ecr>/image-base-dotnet10:stable
COPY --chown=appuser:appuser --from=build /app/out /app
CMD ["/usr/bin/dotnet", "/app/app.dll"]
```

```Dockerfile
# Java: compila com javac/Maven/Gradle no JDK, roda no JRE (sem javac)
FROM <registro-ecr>/image-base-java21-dev:stable AS build
WORKDIR /app
COPY --chown=spring:spring . .
RUN javac -d out Main.java

FROM <registro-ecr>/image-base-java21:stable
COPY --chown=spring:spring --from=build /app/out /app
CMD ["java", "-cp", "/app", "Main"]
```

Para Node.js, use a variante `-dev` só no estágio de build (onde `npm install` precisa rodar) e a variante final (sem `npm`/shell) no estágio de runtime — a imagem que vai pra produção nunca tem `npm` nem shell:

```Dockerfile
FROM <registro-ecr>/image-base-nodejs24-dev:stable AS build
COPY package*.json ./
RUN npm ci --omit=dev
COPY . .

FROM <registro-ecr>/image-base-nodejs24:stable
COPY --chown=appuser:appuser --from=build /app .
CMD ["node", "server.js"]
```

Para fixar a identidade exata da base, use o índice aprovado (substitua o digest ilustrativo pelo valor verificado da release):

```Dockerfile
FROM <registro-ecr>/image-base-python3-14@sha256:<index-digest>
```

A build tag permite rastrear a release; não substitui a verificação do digest,
da assinatura/provenance ou, quando exigida, da SBOM attestation. O pin da base
não torna automaticamente o build da aplicação inteira reproduzível.

## Estrutura do repositório

A composição das imagens, as regras Python, as políticas e a orquestração
ficam em áreas distintas. O [mapa de arquitetura](docs/repository-architecture.md)
detalha responsabilidades, dependências e compatibilidade.

```text
.
├── distroless/                    # base comum das imagens
├── frameworks/                    # catálogo de runtimes e variantes -dev
├── melange/                       # receita do pacote adicional de certificados
├── scripts/
│   ├── certificates/              # bundle corporativo, checksum e metadados
│   └── pipeline/
│       ├── catalog/               # validação das entradas
│       ├── artifacts/             # OCI, digests e scans
│       ├── runtime/               # contratos funcionais e readiness
│       ├── release/               # candidatos, publicação e promoção
│       ├── operations/            # saúde, tempos, resumos e versões
│       └── governance/            # hardening, pins e contratos compartilhados
├── policies/
│   ├── operations/health.json     # alertas, donos, cron e retenção
│   └── release/promotion-quarantine.json
├── .github/
│   ├── workflows/                 # gatilhos, permissões e composição de jobs
│   └── scripts/                   # seis adaptadores para o executor publicado
├── tests/
│   ├── unit/pipeline/             # testes por domínio, sem infraestrutura
│   ├── integration/               # certificados, TLS, adaptadores e executor
│   └── runtime/                   # probes e projetos Go, Java e .NET nas imagens
├── docs/                          # arquitetura, runbooks e evidências
├── troubleshooting/               # toolkit de diagnóstico separado do produto
├── CONTRIBUTING.md                # ambiente e fluxo de contribuição
├── requirements-dev.txt           # dependência Python da automação
├── Makefile                       # build local e comandos de verificação
└── README.md
```

Validação rápida: `make test-unit lint-local`. Validação completa da automação:
`make check`, com o checkout compartilhado preparado conforme o guia de contribuição.
Os required checks do CI mantêm os nomes `test` e `lint-workflows`.

## Como as imagens são compostas

Todo `frameworks/<nome>.yaml` usa `include: distroless/image-base.yaml`, herdando os pacotes comuns (o `apko` faz *merge* das listas de pacotes, não substitui) e adicionando só o runtime específico e um usuário non-root próprio:

```mermaid
flowchart TD
    subgraph Base["distroless/image-base.yaml<br/>(sem wolfi-base: nada de apk/shell)"]
        B2["ca-certificates-bundle<br/>(trust store oficial do Wolfi)"]
        B3["image-base-ca-certificates<br/>(apk compilado pelo melange)"]
    end

    Base -- "include:" --> J["java21.yaml + java25.yaml (JRE)<br/>openjdk-21-jre / openjdk-25-jre · user spring"]
    Base -- "include:" --> JD["java21-dev.yaml<br/>openjdk-21 (JDK), só build stage · user spring"]
    Base -- "include:" --> N["nodejs22.yaml + nodejs24.yaml<br/>runtime final, sem npm/busybox · user appuser"]
    Base -- "include:" --> ND["nodejs22-dev.yaml + nodejs24-dev.yaml<br/>+ npm + busybox, só build stage · user appuser"]
    Base -- "include:" --> G["go1-26.yaml<br/>sem toolchain, binário estático · user appuser"]
    Base -- "include:" --> GD["go1-26-dev.yaml<br/>go-1.26, só build stage · user appuser"]
    Base -- "include:" --> DN["dotnet10.yaml<br/>aspnet-10-runtime, sem SDK · user appuser"]
    Base -- "include:" --> DND["dotnet10-dev.yaml<br/>dotnet-10-sdk, só build stage · user appuser"]
    Base -- "include:" --> OUT["... Python (runtime) e dotnet8<br/>(SDK, ainda sem separação run/dev)"]
```

(a tabela [Imagens disponíveis](#imagens-disponíveis) acima tem a lista completa e exata dos 12 arquivos)

Critério de escolha das versões (no momento em que este README foi escrito):

| Linguagem | Versão A | Versão B | Por quê |
|---|---|---|---|
| Java | `openjdk-21` | `openjdk-25` | as duas últimas LTS (Java só recebe LTS a cada ~2 anos: 17, 21, 25) |
| Node.js | `nodejs-22` | `nodejs-24` | as duas últimas LTS (22 em Maintenance, 24 em Active LTS; 26 ainda é "Current", não é LTS) |
| .NET | `dotnet-8-sdk` | `dotnet-10-sdk` | as duas últimas LTS (.NET tem LTS a cada 2 anos: 6, 8, 10; a 9 é STS, não LTS) |
| Python | `python-3.13` | `python-3.14` | as duas últimas minors estáveis (Python não tem trilha LTS separada) |
| Go | `go-1.25` | `go-1.26` | as duas últimas minors estáveis (Go também não tem trilha LTS separada) |

O Wolfi é um repositório rolling-release. Cada build novo resolve um lock com os patches disponíveis; o build e seus replays usam as versões e checksums registrados nesse lock.

> **Nota:** o pacote `nodejs-*` do Wolfi não traz `npm` funcional sozinho — o `npm` usa `#!/usr/bin/env node` no shebang e o `/usr/bin/env` só existe se o pacote `busybox` também for instalado. Por isso as variantes `-dev` incluem `busybox` explicitamente — e por isso o `npm`/`busybox` ficam isolados nessa variante em vez de irem para a imagem de runtime final.

## O pacote `image-base-ca-certificates` (melange)

O `certificados.sh` busca e verifica os certificados. `make certificates` separa
as CAs do bundle interno em âncoras individuais; o Melange as empacota e o Apko
as incorpora ao bundle do sistema e ao truststore Java. Node usa o mesmo bundle
por `NODE_EXTRA_CA_CERTS`. O perfil padrão contém as raízes públicas do Wolfi;
o manifesto corporativo atual é MOCK e não entra em releases.

A [documentação de composição](docs/image-composition.md) explica essa divisão,
os testes de TLS com a CA instalada na imagem, timezone, camadas, lockfiles,
annotations e a publicação dos SBOMs originais por digest.

## Pipeline de CI/CD (GitHub Actions)

O `workflow.yml` separa validação e publicação:

- **PRs:** chamam `validate-base-images.yml`, com `contents: read`, sem OIDC, autenticação AWS ou push.
- **Push na `main`, execução manual na `main` e schedule diário às 03:00 UTC:** chamam `build-base-images.yml`, que executa a mesma validação antes do job de publicação.
- **Promoção:** roda a cada hora, no minuto 17, e seleciona somente candidatos que completaram o soak mínimo de seis horas desde o push.

```mermaid
flowchart TD
    PR["Pull request"] --> V["validate-base-images.yml<br/>sem AWS / somente leitura"]
    MAIN["main: push / dispatch / build diário"] --> B["build-base-images.yml"]
    B --> V
    V --> M["Melange: bundle amd64 + arm64"]
    M --> A["Apko: layout OCI por framework"]
    A --> S["Trivy: amd64 + arm64<br/>relatórios JSON e digests OCI"]
    S --> G["Artifact aprovado de cada framework"]
    G -->|"caminho de publicação na main"| F["Contrato conforme plano + gate comum de trust<br/>amd64 + arm64 sobre o candidato"]
    F -->|"somente execução autorizada na main"| PUB["Job de publicação<br/>OIDC + cópia OCI + assinatura/provenance + SBOM attestations"]
    PUB --> ECR[("ECR: tag de build")]
    PUB --> T["Tabela por framework<br/>no resumo do run"]
    H["Schedule horário"] --> P["promote-stable.yml"]
    ECR --> P
    P --> SOAK["Candidato elegível + re-scan<br/>amd64 + arm64 por digest"]
    SOAK --> WRITE["stable escrita por referência"]
    WRITE --> STABLE["ECR read-back confirma índice<br/>promoted=true"]
```

O build do CI usa `apko build` uma única vez por framework para produzir um layout OCI multi-arquitetura. [oci_artifact.py](scripts/pipeline/artifacts/oci_artifact.py) verifica hashes/tamanhos dos blobs, presença de amd64/arm64 e coerência dos configs, preservando o índice original em um layout transportável. [scan_images.py](scripts/pipeline/artifacts/scan_images.py) fornece ao Trivy uma visão com apenas o manifest da arquitetura solicitada e confere a arquitetura no relatório: o teste real mostrou que somente `--platform` não bastava para layouts OCI multi-arquitetura no Trivy 0.72.0.

Relatórios JSON e digests dos manifests ficam nos artifacts `build-scans-<framework>-<tentativa>` por 30 dias. O layout aprovado, sua evidência e os SBOMs são transferidos em `validated-oci-<framework>` por três dias. Uma falha em qualquer arquitetura impede a disponibilização desse artifact para publicação.

O **lote padrão** que `workflow.yml` passa aos três chamadores (`validate-pr`, build diário/push e promoção horária) é o catálogo `frameworks/*.yaml` menos os frameworks excluídos em `policies/operations/health.json` → `exceptions` — hoje só `dotnet8` ([ADR-0001](docs/adr/0001-dotnet8-fora-do-lote-padrao.md)). Um lint offline no check obrigatório ([default_batch.py](scripts/pipeline/catalog/default_batch.py)) reprova qualquer divergência entre as três listas e `catálogo − exclusões`; um framework excluído continua no catálogo e pode ser buildado por `workflow_dispatch`, com o mesmo gate.

A validação usa matrix com `fail-fast: false`. **A publicação é independente por framework (M13):** cada leg do publicador exige o seu próprio artifact `validated-oci-<framework>` e falha, visível e sem publicar, se a validação daquele framework tiver reprovado — sem derrubar os demais do lote. Uma falha numa dependência comum, como o bundle melange, continua bloqueando todos. O job de publicação tem matrix própria e autenticação AWS restrita à `main`. Para publicar um subconjunto, uma execução manual pode selecionar os frameworks desejados.

**Identidade do artefato (M02):** o publicador baixa o layout aprovado do mesmo run, verifica novamente sua integridade e usa Skopeo com `copy --all --preserve-digests`. O digest devolvido pela cópia precisa ser igual ao índice validado; não há novo build nem resolução de pacotes nesse job. Após copiar, o publicador lê a tag de volta e confere os bytes do índice e os manifests de ambas as arquiteturas contra a evidência validada. O artifact `publication-<framework>-<tentativa>` preserva essa comparação por 30 dias. A cópia foi comprovada em ECR exclusivo de teste e a leitura de volta em registry local; a integração completa na `main` ainda depende da validação do workflow autenticado.

O gate mantém `--ignore-unfixed` e severidades `CRITICAL,HIGH,MEDIUM,LOW`, além do scan de segredos. O scan aprovado representa apenas a política configurada e os dados disponíveis ao Trivy naquele momento. A triagem automática de CVEs permanece pausada; sua futura reativação deverá consumir os relatórios JSON, pois as tabelas em logs deixaram de ser a saída principal.

**Execução funcional antes de publicar (M08/M10):** entre a validação e a publicação, `test-runtime-images.yml` executa os contratos previstos no plano do lote nas duas plataformas, sobre o próprio artifact candidato — sem rebuild da imagem base. Node e Python rodam um probe com o interpretador da imagem; Go, Java e .NET têm projeto mínimo e Dockerfile multi-stage versionados em [tests/runtime/projects](tests/runtime/projects), construídos com a variante `-dev` do candidato no estágio de build e a variante de runtime no estágio final. O contrato confere versão do runtime, UID/GID 10000 herdados da imagem, raiz somente leitura com duas áreas graváveis explícitas, parsing do bundle de CAs da imagem e TLS positivo **e** negativo com CA de teste. **O contrato é obrigatório quando previsto no plano do lote:** evidence ausente não aprova um contrato exigido. Há 11 contratos diretos: seis interpretados e cinco compilados. As cinco variantes `-dev` compiladas são exercitadas no contrato do runtime, mas sua publicação não exige gate funcional próprio. Runtime compilado solicitado sem seu par e `dotnet8` recebem skip explícito `not_required`, com `passed:null`; isso não é PASS. A cobertura vem do código versionado ([runtime_images.py](scripts/pipeline/runtime/runtime_images.py)). Detalhes, mecanismos de confiança TLS por linguagem e limites em [tests/runtime/README.md](tests/runtime/README.md).

QEMU serve ao job melange (comandos no sandbox do pacote) e ao contrato funcional, que executa a arquitetura não nativa emulada e **registra emulação e execução nativa separadamente**. Apko continua compondo pacotes sem executar os runtimes.

**Resultado e saúde visíveis (M11/M04/P1-08):** build e promoção produzem resumo por framework e artifacts de evidência. O [health diário](.github/workflows/pipeline-health.yml) calcula proxies de idade de publicação/escrita de `stable` a partir de jobs, lacunas de cron e intervalo criação/início de run, além de checar pins. Não consulta o estado atual do ECR nem comprova entrega de notificação. O [contrato operacional](docs/m11-m04-operational-health.md) distingue controle executado, release utilizável, detecção, entrega e atendimento; documenta fontes/limites, runbook, responsabilidades e proposta de SLO. Canal externo e SLA corporativo permanecem pendentes; o detector compartilha o scheduler monitorado.


## Checks obrigatórios, revisão e endurecimento (M12/M16)

A configuração de revisão da `main` no sandbox, conferida em 13/09/2026, exige:

- **`test`** — testes unitários de pipeline, contratos entre repositórios e
  integração de certificados, sem AWS.
- **`lint-workflows`** — `actionlint` nos workflows mantidos à mão e checks offline de hardening,
  pins, contratos compartilhados e políticas:
  [lint_workflow_hardening.py](scripts/pipeline/governance/lint_workflow_hardening.py)
  (checkout sem `persist-credentials: false`, expressão `${{ }}` dentro de um
  `run`, job executor sem `timeout-minutes`, workflow sem `permissions` no
  topo, Action externa sem SHA completo);
  [pin_inventory.py](scripts/pipeline/governance/pin_inventory.py) `lint` (pin externo
  sem gerenciador de atualização, ou o mesmo insumo com digests diferentes em
  arquivos diferentes); e
  [operational_health.py](scripts/pipeline/operations/operational_health.py) `lint`
  (retenção declarada na política divergente do `retention-days` real, cron
  agendado sem declaração na política); e
  [default_batch.py](scripts/pipeline/catalog/default_batch.py) `lint` (lote
  padrão dos três chamadores diferente de `catálogo − exclusões` ou escrito
  como expressão dinâmica em vez do literal canônico, ou exclusão sem motivo,
  dono, `review_by` e ADR válido em `docs/adr/`).
- **Uma aprovação**, com revisão de code owner nos caminhos do
  [CODEOWNERS](.github/CODEOWNERS) (manifests, workflows, actions,
  automação, testes, políticas de dependência, `melange` e `Makefile`).
  Aprovações são descartadas a cada novo push.

`enforce_admins` está **desligado por decisão explícita do sandbox**; não há
garantia de bloqueio para administradores. Habilitação e aceite no corporativo
pertencem ao P0-03, conforme a [Capability Matrix](docs/ai/CAPABILITY-MATRIX.md).

Os dois checks rodam **sem filtro de path**: um required check com filtro
nunca dispara para um PR fora do escopo e fica pendente para sempre em vez de
aprovar. São rápidos (segundos), então um PR só de documentação recebe
resultado definido.

Entradas de execução manual passam por
[validate_inputs.py](scripts/pipeline/catalog/validate_inputs.py) **antes** de
qualquer credencial AWS: nome único pertencente ao catálogo
`frameworks/*.yaml`, soak finito e não negativo, digest `sha256:<64 hex>`. O
input rejeitado não é ecoado de volta no log. Nenhum input é interpolado
dentro de um `run`; todos chegam por `env:` e são usados com aspas.

No lado da plataforma estão ativos secret scanning, push protection e
`sha_pinning_required` para Actions diretas. Os reusable workflows também
usam SHA completo, conferido no checkout de integração do CI. O token
padrão do Actions é `read` e não pode aprovar PRs.
Detalhes, estado anterior e pendências em
[docs/m09-m16-review.md](docs/m09-m16-review.md).

## Gate de promoção para stable (canário de soak)

A tag `stable` **não** é publicada no mesmo run que builda a imagem. `promote-stable.yml` roda separadamente a cada hora (minuto 17) e só promove um build para `stable` se, decorrida a janela de soak, um **re-scan** do mesmo digest continuar limpo:

1. Lista as imagens do repositório ECR e seleciona o índice OCI/Docker com tag de build válida (`ddmmaa-hhmm`, com sufixo opcional `-r<run_id>-a<tentativa>`) mais recente entre os que já completaram o soak. Descarta o digest já marcado como `stable` e candidatos com data de push anterior ou igual à dele ([find_promotion_candidate.py](scripts/pipeline/release/find_promotion_candidate.py)). Um build recente ainda em soak não impede a seleção de outro elegível.
2. Inspeciona o índice e exige exatamente `linux/amd64` e `linux/arm64`. Verifica assinatura cosign com identidade exata do workflow `build-base-images.yml@refs/heads/main` e provenance GitHub vinculada ao signer workflow e à source ref `refs/heads/main`. Falhas e evidências ausentes bloqueiam a promoção.
3. Re-escaneia esse digest com Trivy em `linux/amd64` e `linux/arm64` (`--ignore-unfixed`). Uma falha em qualquer arquitetura bloqueia a promoção. Em seguida, um scan **separado e não-bloqueante** (`report_unfixed_cves.py`, M11) roda sem `--ignore-unfixed`: CVEs sem correção disponível continuam invisíveis pro gate de propósito (bloquear por algo que ninguém pode corrigir ainda não ajuda), mas passam a aparecer em `unfixed-cves-summary.json`, nunca falhando o job. Os relatórios e a referência por digest ficam nos artifacts `promotion-scans-<framework>-<tentativa>` por 30 dias.
4. Se o re-scan continuar limpo, move a tag com `docker buildx imagetools create --tag <imagem>:stable <imagem>@<digest>` — retagueia o índice multi-arch por referência, sem baixar/re-subir camadas.
5. Consulta o ECR novamente com `--image-ids imageTag=stable` e exige um único índice com digest exatamente igual ao candidato verificado. Só então registra `promoted=true`. Tag ausente, erro/timeout de consulta, resposta inválida/ambígua ou digest diferente falham fechado ([verify_stable.py](scripts/pipeline/release/verify_stable.py)).

O artifact final `promotion-<framework>-<tentativa>` registra `candidate_digest`,
`stable_digest_observed`, `read_back_status` (`confirmed`, `mismatch`, `failed`
ou `not_run`) e `promoted` em `promotion-evidence.json`. O campo `digest`
continua identificando o candidato; `stable_digest` preserva a observação
anterior à escrita. Falha de read-back não desfaz automaticamente uma tag já
movida: consulte o estado e siga o runbook de recuperação se necessário.
O read-back confirma o estado naquele instante; escritores externos podem
alterá-lo depois. Aceite hospedado P1-01: **PASS**, observado em `go1-26` e
`go1-26-dev` no run `34768459323`, commit `e3ed682`, com read-back confirmado
e igualdade dos digests. Ver [evidence atualizada](specs/2026-09-13-consumer-contract-rfc-refresh/evidence.md).

Isso é um canário de **tempo/CVE**, não um canário de tráfego real contra aplicações consumidoras — não há apps de referência nesta POC pra validar contra. Validar contra consumidores reais (deploy canário, smoke test de aplicação) é responsabilidade de cada pipeline de deploy downstream. O gate reavalia vulnerabilidades conhecidas no momento do scan, nas severidades configuradas e com correção disponível; ele não garante ausência de vulnerabilidades durante toda a janela de soak.

A seleção inicial usa metadados ECR; o gate posterior valida plataformas, assinatura e provenance por digest. O verificador espera que o workflow assinante esteja no mesmo repositório GitHub informado ao script; chamadas externas precisam alinhar explicitamente essa política à localização do workflow assinante. A seleção e a atualização de `stable` são serializadas por role/região/framework dentro do mesmo repositório GitHub, tanto no dispatch direto quanto no workflow reusável; atualizações externas não participam desse controle. Os testes dos scripts rodam em PRs/pushes que alterem os scripts e antes da autenticação AWS na promoção. Para executá-los localmente, sem Docker ou AWS:

```bash
python3 -B -m unittest discover -s tests/unit -t . -p 'test_*.py' -v
```

**Medições de patch (M11 — observações históricas, SLA corporativo pendente):**

| Etapa | O que é medido | Valor real observado | Fonte |
| --- | --- | --- | --- |
| Execução do job de promoção | Tempo do job `Promote <framework>` do dispatch até concluir (seleção + verificação + re-scan + retag) | 11-40s | Runs reais desta sessão, ver histórico de entregas M04/M14 |
| Atraso do cron horário | Diferença entre o slot nominal (`17 * * * *`) e a criação do run | ≥24m43s (limite inferior — a API não expõe o instante nominal de enfileiramento) | [run 34390576742](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34390576742), Décima sexta entrega |
| Correção disponível no Wolfi → build que a incorpora → `stable` atualizado | Ainda **não medido de ponta a ponta** — exige correlacionar o timestamp de publicação do pacote corrigido no Wolfi com o build seguinte, e esse rastreamento ainda não existe no pipeline | — | Item aberto (ver M11 — restante) |

A espera nominal após o soak (6h) até a próxima janela de promoção horária é inferior a uma hora, mas uma amostra única de atraso do scheduler não prova regularidade contínua — só observação repetida ao longo do tempo formaliza isso como garantia. O build publicado pode ser consumido antes da promoção, assumindo explicitamente que ainda não passou pelo gate de `stable`.

**Política de exceção (M11/M15):** hoje não existe nenhuma exceção ao gate de CVE, em nenhum workflow, inclusive na recuperação de emergência (`recover-stable.yml`, M15) — um digest que falhe o re-scan não é promovido nem restaurado, ponto. Essa é a política vigente, declarada explicitamente em vez de implícita. Uma exceção formal (permitir conscientemente uma CVE específica, por prazo e responsável definidos) não está implementada; se vier a existir, precisa de escopo, aprovador e validade explícitos — nunca um bypass geral do gate.

## Recuperação de `stable` (runbook, M15)

Se um build promovido apresentar problema depois da promoção (ex.: CVE divulgada após o soak, comportamento inesperado reportado por um consumidor), `recover-stable.yml` restaura `stable` para um digest anterior já aprovado — sem rebuild, sem bypass do gate de segurança:

1. **Escolher o digest de destino.** Precisa ser um build já publicado no repositório (`aws ecr describe-images --repository-name image-base-<framework>`) — nunca um digest arbitrário. Idealmente um build que já foi `stable` antes.
2. **Disparar o workflow** (Actions → "Recover stable to a previous digest" → Run workflow) com `framework`, `digest` (`sha256:...`) e `reason`. O job:
   - confirma que o digest existe no repositório;
   - reverifica plataformas (amd64+arm64), assinatura cosign e provenance GitHub com a **mesma política** de `promote-stable.yml` — um digest antigo que não passe nessa verificação não é restaurado;
   - reescaneia as duas arquiteturas com o banco de CVE atual — uma CVE nova no digest antigo bloqueia a recuperação; correção do gate por exceção exige política explícita, não esse workflow;
   - move `stable` com `docker buildx imagetools create` (mesmo mecanismo da promoção normal, sem rebuild) e confirma por leitura de volta independente;
   - grava um `recovery-evidence.json` (operador = `github.actor`, motivo, digest anterior/novo, run) como artifact.
3. **Abrir um PR** adicionando o digest retirado a `policies/release/promotion-quarantine.json` (o job imprime o trecho JSON pronto pra colar). Sem isso, o build retirado continua sendo o mais recente por timestamp em `find_promotion_candidate.py`, e o próximo ciclo de promoção o selecionaria de novo — desfazendo a recuperação. A entrada de quarentena some quando um build mais novo e aprovado for promovido de verdade (a partir daí o timestamp de `stable` já avança e a exclusão explícita deixa de ser necessária).

A recuperação e uma promoção concorrente do mesmo framework compartilham o grupo de concorrência de `promote-stable.yml` — nunca correm ao mesmo tempo. Restaurar a imagem base **não** reconstrói nem reverte automaticamente aplicações consumidoras; isso é responsabilidade do runbook de deploy de cada time.

## Verificação: assinatura e build provenance

O pipeline assina o **OCI index digest** com Cosign keyless, anexa provenance
GitHub e atesta os SPDX originais do índice e de cada arquitetura. Uma tag de
build pode existir antes dessas etapas concluírem; a promoção exige assinatura
e provenance válidas. A promoção não possui gate específico de SBOM attestation.

O [Consumer Verification Contract](docs/consumer-verification-contract.md) é a
fonte canônica para resolução única do digest, `cosign verify`,
`gh attestation verify`, `cosign verify-attestation --type spdxjson`, identidade
exata atual e vínculo com os IDs de repository/owner. Ele diferencia evidence
disponível de enforcement e indica quais valores precisam ser aprovados no
ambiente corporativo. Não se atribui SLSA level formal.

O [ADR-0002 — Modelo de confiança Sigstore](docs/adr/0002-sigstore-trust-model.md)
detalha raízes, metadados públicos e diferenças de attestations entre
repositories públicos/privados. A decisão corporativa permanece PROPOSED,
dependente de Segurança/AppSec; o ADR não altera o signing atual.

Para aplicar a política completa da promoção, em checkout revisado e com
`IMAGE_REF` já fixada por digest conforme o contrato:

```bash
python3 -B -m scripts.pipeline.release.verify_promotion \
  "$IMAGE_REF" alric-corp/alric-containers-image-base
```

Esse verificador é somente leitura no registry e não executa promoção,
soak, re-scan ou verificação de SBOM. A evidência histórica de assinatura e
provenance está no [histórico](docs/rfc-013-historico-de-entregas.md); a
[reconciliação atual](specs/2026-09-13-consumer-contract-rfc-refresh/evidence.md)
registra as observações hospedadas recentes e os aceites ainda pendentes.

## Configuração dos workflows reusáveis

O [ADR-0003 — Controles da fábrica em workflows federados](docs/adr/0003-controles-seguranca-workflows-federados.md)
é a fonte canônica para autoria/sustentação, controles existentes e requisitos
corporativos a confirmar. O contrato de reuso abaixo permanece técnico;
não estabelece homologação de scanner ou dispensa de requisitos externos.

Os workflows podem ser chamados diretamente. `validate-base-images.yml` exige apenas `frameworks` e `contents: read`, sem credenciais AWS. Build/publicação e promoção exigem OIDC e restringem os jobs que acessam AWS a eventos de push/schedule/dispatch na `main` do chamador. No uso externo, `actions/checkout` utiliza o repositório chamador, que precisa conter os manifestos e scripts esperados. Exemplo de permissões para build/publicação e promoção:

```yaml
permissions:
  id-token: write
  contents: read
  attestations: write
  artifact-metadata: write
  actions: read

jobs:
  build-images:
    uses: alric-corp/alric-containers-image-base/.github/workflows/build-base-images.yml@e3ed68259f66af41e8054a4c0ac29a54082ddd60
    with:
      aws-region: us-east-1
      aws-role-arn: arn:aws:iam::<conta>:role/github-actions-image-base
      frameworks: '["java25", "java25-dev", "nodejs24", "nodejs24-dev"]'

  promote-images:
    uses: alric-corp/alric-containers-image-base/.github/workflows/promote-stable.yml@e3ed68259f66af41e8054a4c0ac29a54082ddd60
    with:
      aws-region: us-east-1
      aws-role-arn: arn:aws:iam::<conta>:role/github-actions-image-base
      soak-hours: 6
      frameworks: '["java25", "java25-dev", "nodejs24", "nodejs24-dev"]'
```

| Nome | Workflow | Tipo | Obrigatório | Descrição |
|---|---|---|---|---|
| `aws-region` | ambos | input | sim | região AWS onde o ECR está |
| `aws-role-arn` | ambos | input | sim | role assumida via OIDC, com permissão de push/leitura no ECR |
| `frameworks` | ambos | input | sim | array JSON com os nomes dos arquivos em `frameworks/*.yaml` a processar |
| `soak-hours` | promote-stable | input | não (default `6`) | horas mínimas que um build imutável espera antes de poder virar `stable` |

Pré-requisito de infraestrutura: provider OIDC e role aprovados por Cloud/IAM, com trust restrita e permissões conforme o [contrato P1-04](docs/iam-permission-contract.md). Seus exemplos locais não alteram a policy ativa. O publicador atual também cria/configura ECRs; PutImage no mesmo repositório não reserva stable exclusivamente ao promotor.

## Build local

O [`Makefile`](Makefile) automatiza o build local — melange e apko sempre rodam via `docker run` (não como binário nativo), então funciona em qualquer SO/arquitetura de dev sem precisar instalar nada além do Docker:

```bash
make list                                                # lista os frameworks disponiveis
make build FRAMEWORK=go1-26                               # compõe o OCI e carrega no Docker local
make run FRAMEWORK=go1-26-dev ENTRYPOINT=/usr/bin/go ARGS=version  # builda e roda um comando na imagem (toolchain só existe na variante -dev)
make clean                                                # remove chave e pacotes locais
```

`make build` compila o pacote de âncoras com o Melange, resolve um lockfile e compõe um OCI com data fixa. Depois carrega a arquitetura selecionada no Docker, sem reconstrução. `make oci` conserva somente o layout; `LOCKFILE=<arquivo>` permite replay com as mesmas versões. O `ARCH` é detectado do host e pode ser sobrescrito. As ferramentas continuam executando via Docker, sem credenciais AWS para build local.

## Conclusão

Manter uma imagem base atualizada e escaneada pra 5 linguagens diferentes costuma acabar em um de dois lugares: um Dockerfile artesanal por time/projeto que ninguém revisita depois que funciona uma vez, ou a decisão de aceitar uma imagem genérica de distro completa (com o pacote de ferramentas — e CVEs — que vem junto) só porque é o caminho de menor resistência.

O `image-base` centraliza as 17 combinações linguagem+versão+variante em `frameworks/*.yaml`, com validação das duas arquiteturas antes do job de publicação e nova avaliação por digest antes de promover para `stable`. A identidade do artefato é preservada na cópia OCI; a [RFC-013](RFC-013-Image-Base-Completa-com-Mermaid.md) registra o estado de cada controle e o que falta para produção.

Isso não substitui a imagem final da sua aplicação — é o ponto de partida (`FROM <registro-ecr>/image-base-<framework>:stable`) pra não ter que decidir, de novo, quais pacotes tirar de uma imagem Ubuntu/Alpine pra chegar a um resultado parecido.

## Dependências do pipeline e tags

As Actions diretas dos workflows estão fixadas por SHA completo; apko, melange, Skopeo e actionlint usam digests; a versão do Trivy é fixada por tag de release. Os reusable workflows corporativos também usam SHA completo, conferido no CI. **Todo pin tem um gerenciador de atualização configurado** — Dependabot para Actions, Renovate para os digests de imagem (workflows, Makefile e o executor de contratos) e para `TRIVY_VERSION` — e um lint offline no check obrigatório reprova pin sem gerenciador ou o mesmo insumo com valores divergentes entre arquivos ([pin_inventory.py](scripts/pipeline/governance/pin_inventory.py)).

Renovate ainda precisa ser instalado pelo administrador nos dois repositórios; a configuração não comprova automação ativa. Skopeo usa versão `-immutable` mais digest para evitar depender da retenção dos rebuilds diários. O runtime gerado de `gh-aw` é atualizado pelo compilador, não por alteração isolada do Dependabot. Ver [ajustes e aceites restantes](docs/release-readiness-2026-09-10.md).

As versões **efetivas** do que rodou ficam na evidência de cada etapa ([tool_versions.py](scripts/pipeline/operations/tool_versions.py)): apko/Trivy na validação, cosign/AWS/Docker/Skopeo na publicação, cosign/Trivy/AWS/gh/buildx na promoção, mais `python3`/`git` e a identificação da imagem do runner hospedado — que muda sem passar por nenhum pin deste repositório. Só comandos de versão em allowlist, sem dump de ambiente.

O workflow diário de saúde confere que **cada pin ainda existe na origem** (commit da Action, manifest do digest, release do Trivy) e reporta a idade das PRs de atualização abertas. Um pin recolhido do registry quebra o próximo build; melhor descobrir num job de saúde do que numa publicação.

O workflow de publicação configura tags imutáveis no ECR, com exceção exata para `stable`, incluindo repositórios existentes. As tags novas incluem run ID e tentativa. Reexecuções parciais do publicador reutilizam `validated-oci-<framework>` aprovado no mesmo run, independentemente de `run_attempt`. Se a validação for reexecutada, o artifact é substituído somente após o novo scan passar (`overwrite: true`). M13 mantém os gates por framework: artifact validado próprio, contrato aplicável e integração de trust continuam obrigatórios. O repositório melange também permite substituição em reexecuções completas. Artifacts expirados exigem nova validação. Os relatórios de scan continuam separados por tentativa.

**P1-02 — retry parcial sem rebuild:** o gate procura `runtime-<framework>-<attempt>` somente no run corrente e seleciona numericamente a tentativa mais recente compatível com os índices/manifests atuais. Os dois reports precisam pertencer ao mesmo artifact/run/framework/revisão; contratos compilados também conferem o par `-dev` validado atual. Falha do producer mais recente, ausência, corrupção, conflitos ou digest divergente bloqueiam. Success herdado pelo GitHub não exige report novo: o publicador pode reutilizar o contrato anterior sem executar Apko/Melange. A decisão e o attempt escolhido ficam em `runtime-gate-result.json`, junto à evidência de publicação. [Spec, política de seleção e limites](specs/2026-09-13-partial-retry-without-rebuild/spec.md). O aceite hospedado com rerun real permanece **NOT RUN**.

Para executar as suítes de regressão do pipeline e dos certificados, consulte [tests/README.md](tests/README.md).

## Workflows compartilhados

A validação Apko/Melange e a execução dos contratos de runtime são consumidas
via o commit publicado `7a9b055a462eeb8552d3404c26538b44e8ccd83f` de
`alric-corp/alric-containers-reusable-workflows`. A instalação do Trivy é uma
composite action comum à validação, promoção e recuperação. Gatilhos, catálogo,
scripts/testes de domínio e decisões de release permanecem neste repositório.

Veja a [divisão de responsabilidades, contrato e adoção](docs/m09-m12-reusable-workflows.md).
Para os checks locais, defina `REUSABLE_WORKFLOWS_PATH` apontando para um checkout
da biblioteca no SHA fixado pelos chamadores; no CI esse commit é conferido
automaticamente. A [migração dos nomes e da confiança AWS](docs/repository-rename.md)
descreve a compatibilidade das assinaturas históricas.
