# EVIDENCE — 2026-09-17 full-catalog-revalidation

Estado: **DONE** para R1–R4 (16 definições); **DONE via inspeção de registro
ao vivo** (não build de CI) para R5 (`dotnet8`, por desenho — ver seção 5);
**DONE** para R6.

## Identidade

- Data: 2026-09-17, execução entre 03:40Z e 03:52Z.
- Branch/commit base: `d2eac6e894a4f2f87e99a4f304775d034fcb7363` (`HEAD` ==
  `origin/main` no início da sessão; a branch local `main` divergia 4
  ahead/4 behind de `origin/main` — resíduo de sessão anterior, não tocado
  nesta rodada).
- Mecanismo de trigger: PR descartável
  [`#81`](https://github.com/alric-corp/alric-containers-image-base/pull/81)
  (`ops/full-catalog-revalidation-20260917`, commit `e308c7d`), com uma
  única mudança **comment-only** no `Makefile` (mesmo padrão já usado neste
  repositório em `test/m12-doc-only`/`test/m16-codeowners-enforcement`:
  "comment-only change to a protected path") para que
  `pr_execution_scope` resolvesse o profile como `FULL` e disparasse
  `validate-pr-full` ("Validate full catalog for shared-impact PR"). Sem essa
  rota, o único gatilho de PR disponível (`validate-pr`, profile `P0_04`)
  valida só `go1-26`/`go1-26-dev`. Nenhuma outra alteração de produto entrou
  nesse PR; ele **não foi mergeado** (ver seção 6).
- Ferramenta/sessão: Claude Code, `gh` autenticado (`repo`+`workflow`),
  Docker local ativo.

## 1. Mecanismo real usado

`validate-pr-full` → `validate-base-images.yml` → `wolfi-trust` +
`image-trust` + `validate` (reusable
`alric-corp/alric-containers-reusable-workflows/.github/workflows/validate-apko-images.yml@7a9b055a…`),
com `melange-config: image-base-ca-certificates.yaml`, `locked-build: true`.
Cada leg da matriz `validate` builda a imagem real via **apko**
(`cgr.dev/chainguard/apko@sha256:37e3aa16…`) contra o repositório Wolfi
configurado em `distroless/image-base.yaml`, compila o pacote de
certificados via **melange**
(`cgr.dev/chainguard/melange@sha256:43d6581e…`), e escaneia as duas
arquiteturas (`amd64`+`arm64`) com **Trivy**. Run real:

```
Run ID:  35179012804  (workflow "Build & publish base images", evento pull_request)
Job "Validate full catalog for shared-impact PR / wolfi-trust": success
Jobs "… / image-trust / trust (<framework>)" (16): todos success
Jobs "… / validate / Validate <framework>" (16): todos success
Job "… / image-trust / image-trust-gate": success
Jobs "build-base-images", "promote-stable", "validate-pr": skipping (correto —
  não é push/schedule/dispatch em main, não é profile P0_04)
```

URL: https://github.com/alric-corp/alric-containers-image-base/actions/runs/35179012804

Nenhum framework fora da lista abaixo foi tocado; a lista corresponde
exatamente aos 16 hardcoded em `validate-pr-full` (todo o catálogo exceto
`dotnet8`).

## 2. Toolchain / advisory evidence (R4)

Capturado do job log real (`tool-versions.json` por framework + log do
step "Scan both architectures"):

| Campo | Valor |
| --- | --- |
| Trivy version (pinada pela fábrica) | `0.72.0` |
| Fonte do DB | `mirror.gcr.io/aquasec/trivy-db:2` |
| Download do DB | fresco a cada job, `2026-09-17T03:41:06Z`–`03:41:12Z` (amostra: job `java21`, ID `105067065112`; outros jobs do mesmo run em janela equivalente) |
| apko | `v1.2.43+dirty` |
| melange | `v0.59.5+dirty` |
| `run_id` / `run_attempt` | `35179012804` / `1` |

`trivy --version` roda **antes** do download do DB (só imprime a versão do
binário); o download real do DB acontece dentro de `scan_images.py`, cujo
timestamp de log é a evidência de estado do advisory DB usada nesta rodada
— não presumido, lido diretamente do log de cada job.

**Lacuna encontrada (não implementada nesta rodada, ver spec.md → Fora do
escopo):** nenhum artifact de evidência hoje persiste `UpdatedAt`/`NextUpdate`
do Trivy DB lado a lado do resultado do scan — só a versão do binário
(`tool-versions.json`) e o timestamp do job (metadado do GitHub Actions).
Reconstruí o estado do DB a partir do log bruto porque a informação não
está em nenhum artifact estruturado. Recomendação para o Tech Lead: pedir ao
dono do reusable workflow (`alric-containers-reusable-workflows`) para
persistir a saída de `trivy --version` **depois** do download do DB (ou o
conteúdo de `~/.cache/trivy/db/metadata.json`) em `reports/trivy-db.json`.

## 3. Matriz real (16 definições, ambas arquiteturas)

Fonte: artifacts `build-scans-<framework>-1` do run `35179012804`, parseados
estruturalmente (`trivy-amd64.json`/`trivy-arm64.json` — blocos
`Results[].Vulnerabilities`/`Results[].Packages`, não `grep` isolado) +
`evidence-<arch>.json` (digests) + `unfixed-cves-summary.json` (relatório
informacional de CVEs sem correção, não bloqueante).

| Framework | Build amd64 | Build arm64 | Trivy amd64 | Trivy arm64 | Unfixed (info.) | Contrato funcional | zlib resolvido | CVE bloqueante | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `dotnet10` | PASS | PASS | PASS | PASS | 0 | NOT_RUN¹ | `1.3.2.1_rc20260601-r0` | nenhuma | READY |
| `dotnet10-dev` | PASS | PASS | PASS | PASS | 0 | NOT_RUN¹ | `1.3.2.1_rc20260601-r0` | nenhuma | READY |
| `go1-25` | PASS | PASS | PASS | PASS | 0 | NOT_RUN¹ | ausente (binário estático) | nenhuma | READY |
| `go1-25-dev` | PASS | PASS | PASS | PASS | 0 | NOT_RUN¹ | `1.3.2.1_rc20260601-r0` | nenhuma | READY |
| `go1-26` | PASS | PASS | PASS | PASS | 0 | NOT_RUN¹ | ausente (binário estático) | nenhuma | READY |
| `go1-26-dev` | PASS | PASS | PASS | PASS | 0 | NOT_RUN¹ | ausente | nenhuma | READY |
| `java21` | PASS | PASS | PASS | PASS | 0 | NOT_RUN¹ | `1.3.2.1_rc20260601-r0` | nenhuma | READY |
| `java21-dev` | PASS | PASS | PASS | PASS | 0 | NOT_RUN¹ | `1.3.2.1_rc20260601-r0` | nenhuma | READY |
| `java25` | PASS | PASS | PASS | PASS | 0 | NOT_RUN¹ | `1.3.2.1_rc20260601-r0` | nenhuma | READY |
| `java25-dev` | PASS | PASS | PASS | PASS | 0 | NOT_RUN¹ | `1.3.2.1_rc20260601-r0` | nenhuma | READY |
| `nodejs22` | PASS | PASS | PASS | PASS | 0 | NOT_RUN¹ | `1.3.2.1_rc20260601-r0` | nenhuma | READY |
| `nodejs22-dev` | PASS | PASS | PASS | PASS | 0 | NOT_RUN¹ | `1.3.2.1_rc20260601-r0` | nenhuma | READY |
| `nodejs24` | PASS | PASS | PASS | PASS | 0 | NOT_RUN¹ | `1.3.2.1_rc20260601-r0` | nenhuma | READY |
| `nodejs24-dev` | PASS | PASS | PASS | PASS | 0 | NOT_RUN¹ | `1.3.2.1_rc20260601-r0` | nenhuma | READY |
| `python3-13` | PASS | PASS | PASS | PASS | 0 | NOT_RUN¹ | `1.3.2.1_rc20260601-r0` | nenhuma | READY |
| `python3-14` | PASS | PASS | PASS | PASS | 0 | NOT_RUN¹ | `1.3.2.1_rc20260601-r0` | nenhuma | READY |
| `dotnet8` | NOT_RUN² | NOT_RUN² | NOT_RUN² | NOT_RUN² | N/A | NUNCA³ | não aplicável | `CVE-2026-47304` CRITICAL + 4 outras | BLOCKED |

¹ `test-runtime-images.yml` (onde o contrato funcional roda) é acionado por
`build-base-images.yml`, que só executa em push/schedule/dispatch na
`main` — nunca em `pull_request`. `validate-pr-full` chama
`validate-base-images.yml` diretamente, sem o job `plan`/`runtime-contract`.
Confirmado nesta rodada pela ausência desses jobs na lista real de jobs do
run `35179012804` (mesmo comportamento documentado no ADR-0006, rodapé 1 —
ainda verdadeiro, não é regressão desta sessão). Não é uma limitação desta
spec: é o `execution_scope` vigente, que esta rodada foi instruída a não
alterar.

² Nenhum build/scan real rodou para `dotnet8` nesta sessão: ele está fora
dos três lotes de `workflow.yml` desde o ADR-0001
(`policies/operations/health.json` → `exceptions.dotnet8`), e esta rodada
foi instruída a não alterar `execution_scope`/default batch. Ver seção 5
para o método usado (inspeção do registro Wolfi ao vivo, sem build).

³ Nunca produziu artifact aprovado desde a exclusão (ADR-0001).

### Confirmação da CVE-2026-85091 (zlib) — seção 7 do pedido

Nenhuma das 16 × 2 = 32 combinações framework/arquitetura reportou
`CVE-2026-85091`. Onde `zlib` está presente no closure (13 dos 16 —
`go1-25`/`go1-26`/`go1-26-dev` não dependem de `libz.so.1`, binários
estáticos), a versão resolvida em **todas** é `1.3.2.1_rc20260601-r0` —
confirmado pelo `Packages[].Version` do relatório Trivy, não inferido da
ausência de CVE. Ausência de CVE **correlacionada** com essa versão
instalada específica, exatamente como pedido:

```
ZLIB_85091_STATUS = FIXED_BY_WOLFI
```

## 4. Diferença de closure Go 1.25 vs Go 1.26 (seção 12)

Reconfirmado com o build real (não assumido por analogia): `go1-25-dev`
resolve `zlib` (presente no relatório Trivy, `1.3.2.1_rc20260601-r0`, sem
CVE); `go1-25`, `go1-26` e `go1-26-dev` não têm `zlib` no `Packages[]` — os
binários Go 1.25/1.26 são estaticamente linkados e não dependem de
`libz.so.1`. Mesmo padrão do ADR-0006 (que descrevia isso só para
Java 21/Go 1.26); agora confirmado para `go1-25`/`go1-25-dev` com dados
reais desta sessão.

## 5. `dotnet8` — evidência sem build (seção 11)

`dotnet8` está estruturalmente fora de `validate-pr` e `validate-pr-full`
(ADR-0001); esta rodada foi instruída a não alterar essa exclusão. A
evidência abaixo vem de duas fontes reais, **sem build/scan de CI**:

**a) APKINDEX ao vivo** (`https://packages.wolfi.dev/os/x86_64/APKINDEX.tar.gz`,
consultado 2026-09-17T03:48:54Z): maior versão publicada de
`dotnet-8-sdk`/`dotnet-8-runtime`/`aspnet-8-runtime` = `8.0.127-r0` (idêntico
ao que o run real anterior já havia observado, ver
`specs/2026-09-16-v1-reference-go126/evidence.md`, rodapé 4).

**b) Resolução do closure + Trivy local** (rootfs sintético com o banco APK
real resolvido do APKINDEX acima; Trivy `0.74.0` local, DB baixado
2026-09-17T01:13Z — versão de Trivy **diferente** da pinada pela fábrica,
`0.72.0`, registrado aqui para transparência de método):

```
CVE-2026-47304  CRITICAL  aspnet-8-runtime/aspnet-8-targeting-pack/dotnet-8-runtime/dotnet-8-sdk/dotnet-8-targeting-pack
                          8.0.127-r0 -> 8.0.131-r0
CVE-2026-47302  HIGH      (mesmos 5 pacotes)  8.0.127-r0 -> 8.0.131-r0
CVE-2026-50525  HIGH      (mesmos 5 pacotes)  8.0.127-r0 -> 8.0.131-r0
CVE-2026-50648  HIGH      (mesmos 5 pacotes)  8.0.127-r0 -> 8.0.131-r0
CVE-2026-69304  MEDIUM    (mesmos 5 pacotes)  8.0.127-r0 -> 8.0.131-r0
```

O alvo de correção mudou de `8.0.129-r1` (citado na matriz de 09-16) para
`8.0.131-r0` — o upstream .NET 8 continua publicando patches; o Wolfi
continua sem acompanhar. Nenhuma dessas 5 CVEs é `CVE-2026-85091`/zlib —
`dotnet8` bloqueia por um problema real e não relacionado, sem qualquer
suposição.

```
DOTNET8_BLOCKER:
  package atual: dotnet-8-sdk 8.0.127-r0 (+ dotnet-8-runtime, aspnet-8-runtime,
                  aspnet-8-targeting-pack, dotnet-8-targeting-pack)
  CVEs: CVE-2026-47304 (CRITICAL), CVE-2026-47302/50525/50648 (HIGH),
        CVE-2026-69304 (MEDIUM)
  versão corrigida requerida: 8.0.131-r0
  versão mais recente no Wolfi: 8.0.127-r0
  contexto de suporte: .NET 8 é LTS; ADR-0001 já documenta o padrão
  (rebuild não resolve — pacote corrigido não existe na origem consultada)
```

## 6. Fechamento do PR de trigger

PR [`#81`](https://github.com/alric-corp/alric-containers-image-base/pull/81)
fechado sem merge após a coleta de evidência (run `35179012804` já
concluído e artifacts baixados); branch `ops/full-catalog-revalidation-20260917`
removida local e remotamente. Nenhum código do produto foi alterado por
essa branch — ela nunca chegou a `main`.

## Revisão

Investigação/evidência conduzida nesta sessão a partir de dados reais (run
de CI real, `APKINDEX` ao vivo, `security.json` do Wolfi, `zlib.yaml` e
`APKBUILD` públicos). Não houve revisão independente de code owner até este
ponto — mesma ressalva que o ADR-0006 já registrava. Recomenda-se revisão
antes de qualquer decisão de rollout baseada nesta matriz.

## Limites e resultado

**Implementado/comprovado:** build+scan real para 16/16 definições, ambas
arquiteturas, via mecanismo de fábrica inalterado; correlação
versão-instalada↔ausência-de-CVE para `CVE-2026-85091`; evidência real
(não sintética) de que o blocker de zlib está resolvido nas 16 definições
onde `zlib` está presente.

**Não implementado/não executado:** contrato funcional (fora do
`execution_scope` de PR, por desenho); build/scan de CI para `dotnet8`
(fora de todos os lotes por ADR-0001, não alterado nesta rodada — evidência
por inspeção de registro ao vivo, não por build); captura de metadado do
Trivy DB no mecanismo de evidence do reusable workflow (recomendação, não
implementação, por viver em repositório diferente e revisado
separadamente); qualquer decisão de rollout, arquitetura ou política de
versões (são decisões do Tech Lead, não desta spec).
