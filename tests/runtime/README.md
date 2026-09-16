# Contratos funcionais M08/M10

O executor testa as duas plataformas de um artifact OCI existente, sem
rebuild da imagem base, publicação ou autenticação AWS. Dois tipos de
contrato, com o **mesmo contrato de ambiente e a mesma saída**:

| Tipo | Frameworks | Como executa |
| --- | --- | --- |
| interpretado | Node 22/24 (e `-dev`), Python 3.13/3.14 | o probe roda com o interpretador da própria imagem candidata, montado somente para leitura |
| compilado | `go1-26`, `java21`, `dotnet10` | o projeto mínimo de [`projects/`](projects) é construído por um Dockerfile multi-stage real: variante `-dev` no estágio de build, variante de runtime no estágio final |

```sh
# interpretado
python3 -B -m scripts.pipeline.runtime.runtime_images /caminho/candidate.oci nodejs24 --reports /tmp/reports

# compilado: precisa do par -dev do MESMO run
python3 -B -m scripts.pipeline.runtime.runtime_images /caminho/go1-26.oci go1-26 \
  --dev-layout /caminho/go1-26-dev.oci --reports /tmp/reports

python3 -B -m scripts.pipeline.runtime.runtime_images --plan '["go1-26","go1-26-dev"]'  # o que roda no lote
python3 -B -m scripts.pipeline.runtime.runtime_images --gate go1-26 --requested '["go1-26","go1-26-dev"]' \
  --reports /tmp/reports                                                        # o gate de publicação
```

Cada diretório deve conter o layout completo e `validated-index.json`, como
nos artifacts `validated-oci-<framework>`. Requer Python 3.9+, OpenSSL com
`req -addext`, Docker acessível e emulação da arquitetura diferente da do
daemon. Docker Desktop já forneceu essa emulação no exercício local; o
workflow usa QEMU no runner Linux. O host precisa aceitar conexões do
container em duas portas efêmeras via `host.docker.internal`/`host-gateway`.

## Os projetos mínimos são versionados, não improvisados

[`projects/go`](projects/go), [`projects/java`](projects/java) e
[`projects/dotnet`](projects/dotnet) são os projetos e Dockerfiles que o M07
usou à mão, agora versionados e executados no CI. Cada Dockerfile recebe as
duas imagens candidatas por `--build-arg` — o par testado é o par do run, não
uma imagem de registry — e reproduz a forma que o README documenta para os
consumidores:

- `RUN` em **shell-form** (`RUN go build ...`, `RUN dotnet publish ...`), que
  é como um Dockerfile normal se escreve e só funciona porque a variante
  `-dev` tem shell. Foi exatamente essa lacuna que a revisão do M07 achou.
- Java compila por [`build.sh`](projects/java/build.sh), um wrapper
  `#!/bin/sh` no formato de `mvnw`/`gradlew`: sem shell não roda de jeito
  nenhum, nem em exec-form.
- Nenhum estágio de build usa rede (`docker build --network none`): os
  projetos só usam biblioteca padrão, e `dotnet publish` roda com um
  `NuGet.config` sem nenhuma fonte. Download aqui seria conteúdo não validado
  entrando na imagem.
- O estágio final não declara `USER` nem `ENTRYPOINT` de conveniência: a
  identidade non-root e o `PATH` vêm da imagem candidata — é isso que está
  sendo testado.

## O que cada execução verifica

O executor verifica todos os blobs do OCI e sua correspondência com a
evidência de validação, nos dois layouts (runtime e `-dev`). Skopeo (mesmo
digest fixado no publicador) importa cada plataforma para uma tag local
exclusiva. Uma reexportação pelo Docker confirma o hash da configuração, que
inclui os hashes das camadas descomprimidas. Não se presume que
`docker inspect .Id` seja o digest da configuração: no image store containerd
ele pode ser um digest de manifest. Os relatórios preservam essas identidades
separadamente, para runtime e `-dev`.

O contrato executado dentro da imagem confere:

- Versão do runtime correspondente ao framework (major de Node/Java/.NET,
  major.minor de Python/Go), derivada do nome do catálogo.
- UID e GID reais iguais a 10000, herdados da imagem, sem `--user` no
  executor. Java e .NET leem `/proc/self/status`, porque nenhuma das duas
  plataformas expõe `getuid()`.
- Escrita em `/app` rejeitada com `EROFS` — `/app` pertence ao mesmo uid/gid
  do processo, então a rejeição só pode vir do mount somente leitura, não de
  permissão.
- **Duas áreas graváveis explícitas**, `/tmp` e `/app/work`, ambas tmpfs de
  16 MiB: escrita, leitura de volta e remoção. A segunda mostra que um
  diretório de trabalho sob `/app` pode ser concedido sem abrir a raiz.
- Parsing do bundle que a imagem já traz (`/etc/ssl/certs/ca-certificates.crt`).
- HTTPS com CA efêmera confiável aceito e HTTPS com **outra** CA rejeitado
  por erro de verificação de certificado. Erro de conexão ou timeout não
  aprova o negativo — em nenhuma das quatro linguagens.
- Shell `/bin/sh` funcional como UID/GID 10000 nas variantes `-dev`, mais o
  toolchain (`go version`, `javac -version`, `dotnet --version`) nas
  compiladas.

### Como a CA de teste chega em cada runtime

Não há um mecanismo único, e o contrato não finge que há:

| Runtime | Mecanismo | Por quê |
| --- | --- | --- |
| Node | `NODE_EXTRA_CA_CERTS` | mecanismo de ambiente do próprio runtime |
| Python, Go | `SSL_CERT_FILE` | idem; é o caminho que uma CA corporativa usaria |
| Java | `KeyStore` em memória a partir do PEM | a JVM não lê `SSL_CERT_FILE` nem bundle PEM do sistema; construir o `KeyStore` evita depender de `keytool` no runtime e de arquivo gravável |
| .NET | `X509Chain` com `CustomRootTrust` | validação de cadeia de verdade, só com a CA de teste como raiz — não é callback que aceita tudo, e o nome do host continua sendo conferido |

Onde o mecanismo de ambiente existe, é ele que é testado (é o que um
consumidor usaria). Onde não existe, o contrato configura a confiança
explicitamente. Em nenhum caso a verificação é desligada.

O processo roda sem capabilities, com `no-new-privileges` e raiz somente
leitura. Não há `--privileged` nem montagem do socket Docker dentro do
candidato. As chaves TLS ficam no host e são descartadas ao final; só o
certificado público confiável é montado no candidato. Tags, imagens e
containers criados têm nomes únicos; o cleanup não executa prune nem remove
recursos de outras sessões.

Cada relatório `runtime-<framework>-<arch>.json` registra os digests de
índice, manifest e configuração (do runtime e do `-dev`), o tempo do build
multi-stage, o resultado e **execução nativa ou emulada em relação à
arquitetura do daemon Docker**, separadamente por arquitetura. Qualquer falha
retorna código diferente de zero. A segunda arquitetura continua sendo
testada quando a primeira falha; erro de integridade/setup sobrescreve os
dois relatórios com falha, sem reutilizar sucesso antigo.

## Gate de publicação (integração com M13)

`test-runtime-images.yml` roda dentro de `build-base-images.yml`, entre a
validação e a publicação, e **a publicação de cada framework exige o contrato
do próprio framework aprovado nas duas plataformas**. Aprovação de build/scan
não substitui execução funcional.

A cobertura é decidida em código versionado
([`runtime_images.plan`](../../scripts/pipeline/runtime/runtime_images.py)), não pela
ausência de um artifact:

- framework com contrato: evidência ausente é **falha**, não aprovação;
- framework sem contrato (`dotnet8`, sem variante `-dev`;
  `*-dev` compiladas, cobertas como estágio de build do par): publica com o
  motivo registrado no log e na tabela do run;
- contrato compilado cujo par `-dev` não está no mesmo lote (um
  `workflow_dispatch` só com `go1-26`, por exemplo): não roda, e o motivo
  aparece — o estágio de build precisa ser o artifact candidato.

PRs continuam rodando só validação e scan: contrato funcional roda no caminho
que publica (push/schedule/dispatch na `main`). O dispatch manual do workflow
serve para diagnóstico sobre o artifact de outro run; ele não autoriza
publicação nenhuma.

A retenção de evidências é 30 dias. Reexecução depende também do OCI
original, cuja retenção é 3 dias; guardar o relatório não estende esse prazo
(ver [política de evidências](../../docs/m11-m04-operational-health.md)). O
pin do Skopeo neste executor está sob o mesmo manager do Renovate que o do
publicador, e o lint de M09 reprova se os dois divergirem.

## Evidência

**09/09/2026** ([evidence-2026-09-09.json](evidence-2026-09-09.json)): as
seis variantes interpretadas (Node 22/24 e `-dev`, Python 3.13/3.14) passaram
em amd64 emulado e arm64 nativo — 12 execuções reais. Rotular deliberadamente
um OCI local Node 24 como Node 22 falhou nas duas arquiteturas.

**10/09/2026** ([evidence-2026-09-10.json](evidence-2026-09-10.json)):
primeira execução dos contratos compilados, sobre os artifacts reais do
[run 34421525305](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34421525305)
(push na `main`), no daemon Docker arm64 de um Mac com amd64 emulado:

| Framework | Contrato | amd64 (emulado) | arm64 (nativo) | Versão observada | Build multi-stage |
| --- | --- | --- | --- | --- | --- |
| `go1-26` | compilado | passou | passou | 1.26.8 | 19,3s / 3,0s |
| `java21` | compilado | passou | passou | 21.0.12.1+-wolfi-r1 | 2,0s / 0,8s |
| `dotnet10` | compilado | passou | passou | 10.0.12 | 5,3s / 2,0s |
| `python3-13` | interpretado | passou | passou | 3.13.15 | — |
| `nodejs22-dev` | interpretado | passou | passou | 22.23.2 | — |

**10/09/2026, pares restantes do M07** ([evidence-2026-09-10-m07.json](evidence-2026-09-10-m07.json)):
`go1-25`/`go1-25-dev` e `java25`/`java25-dev` construídos localmente com o
apko fixado (x86_64+aarch64), preparados como no CI e executados pelo contrato
compilado — Go 1.25.12 e Java 25.0.4.1 aprovados em amd64 emulado e arm64
nativo, com shell e toolchain nas `-dev`. Camadas comprimidas por
arquitetura: `go1-25` 231K vs `go1-25-dev` 239–255M; `java25` 85–87M vs
`java25-dev` 115–118M. Depois, no runner hospedado, sobre os artifacts do
`validate-pr` do PR #49 (run 34497811172): `go1-25` (run 34498586167) e
`java25` (run 34498589927) aprovados em amd64 nativo e arm64 emulado por QEMU.

**Teste negativo, não decorativo:** apontando as duas URLs de TLS para o
**mesmo** servidor confiável, o contrato do `go1-26` falhou nas duas
plataformas com `HTTPS com CA não confiável foi aceito` (saída 1). Antes
disso, uma variante do mesmo teste em que a CA montada deixou de corresponder
ao servidor confiável falhou com erro de verificação de certificado — os dois
lados da checagem reagem.

## Limites desta entrega

- Falta **executar isto num runner hospedado com o gate ligado**: os
  contratos compilados rodaram localmente sobre artifacts reais de CI, e o
  `test-runtime-images.yml` já rodou no runner em 09/09 na versão anterior
  (só interpretados, sem gate). A primeira execução da nova cadeia
  `validate → contrato → publicação` no GitHub ainda não aconteceu.
- Os tempos de build acima vêm de Rosetta no Mac; **QEMU no runner hospedado
  é mais lento** — o `timeout-minutes: 30` do job foi dimensionado com essa
  margem, mas o número real ainda precisa ser observado.
- `dotnet8` continua **sem contrato compilado**, porque não tem variante
  `-dev` — e não terá enquanto o scan o bloquear (decisão de catálogo).
- O TLS usa uma CA sintética: testa os mecanismos de confiança dos runtimes,
  **não** comprova distribuição, pin, legitimidade ou confiança end-to-end do
  bundle corporativo. O parsing do bundle da imagem é um check separado.
- M08/M10 seguem **parciais**.
