# ADR-0004 — V1 de referência: Go 1.26 como primeiro fluxo completo, catálogo preservado

| Informação | Valor |
| --- | --- |
| Estado | Proposto (Aceito com a aprovação de code owner do PR que o integra) |
| Data | 16/09/2026 |
| Owners | Containers Products (`@alric-corp/github_xj7_maintainer`) + Owner da RFC-013 |
| Revisão | `execution_scope.review_by` em [`policies/operations/health.json`](../../policies/operations/health.json) (`2026-09-30`); vencida, vira alerta do job de saúde |
| Aplicação | `execution_scope` na política de saúde (visibilidade); `P0_04_BATCH` em [`default_batch.py`](../../scripts/pipeline/catalog/default_batch.py) (execução, já em produção desde o PR #70) |
| Origem | `specs/2026-09-15-first-corporate-e2e/`; achado operacional de 16/09/2026 (ver `evidence.md` da mesma spec) |

## Contexto

`go1-26` e `go1-26-dev` são hoje o único par do catálogo com cadeia
completa demonstrada de ponta a ponta, com evidência hospedada real: build
único (Melange + Apko), multiarch `linux/amd64`/`linux/arm64` obrigatório
por código (`scripts/pipeline/artifacts/oci_artifact.py::verify`), gate
Trivy bloqueante nas duas arquiteturas, contrato funcional compilado,
publicação por digest preservado (`skopeo copy --preserve-digests` +
read-back independente), assinatura Cosign keyless, attestation SBOM SPDX e
provenance SLSA v1 — todos verificáveis por um consumidor externo sem
contexto de CI (`scripts/verify-image.sh`).

Os outros 15 pares/definições do catálogo (17 no total) não estão no mesmo
estado, por duas razões distintas que este ADR separa explicitamente:

1. **Execução restrita de propósito (P0-04, PR #70):** o lote automático de
   build/promoção já roda só `go1-26`/`go1-26-dev` desde 15/09/2026
   (`P0_04_BATCH` em `default_batch.py`), para isolar o primeiro E2E
   corporativo. Isso é seleção de execução, não exclusão de catálogo — as
   17 definições continuam em `frameworks/`, o lote FULL continua existindo
   e sendo exercitado em PRs de impacto compartilhado.
2. **Bloqueio upstream real (`CVE-2026-85091`, zlib):** confirmado em
   16/09/2026 contra o `APKINDEX` vivo de `packages.wolfi.dev/os/x86_64`
   (parse estrutural, não grep): o pacote `zlib` tem 14 builds publicados,
   o mais recente é `1.3.2.1_rc20260601-r0` (um *release candidate*), e a
   versão corrigida que o advisory do Trivy exige (`1.3.3-r0`) **não
   existe** nessa origem. Todos os 13 frameworks que falham hoje na
   validação FULL (`java21[-dev]`, `java25[-dev]`, `nodejs22[-dev]`,
   `nodejs24[-dev]`, `python3-13`, `python3-14`, `dotnet10[-dev]`,
   `go1-25-dev`) falham exatamente nesse único CVE, confirmado
   individualmente por framework nos relatórios Trivy do run
   `35049596440` — não é suposição agregada. `go1-25` passa (não resolve
   `zlib` na sua árvore de dependências). `dotnet8` já tem exceção própria
   e ADR dedicado ([ADR-0001](0001-dotnet8-fora-do-lote-padrao.md)), por um
   CVE diferente (`dotnet-8-sdk`), preservada sem alteração por este ADR.

Sem uma distinção explícita entre essas duas categorias, o job de saúde
(`pipeline-health.yml`) trata os 15 frameworks fora da execução atual como
se estivessem simplesmente quebrados — gerando alerta vermelho diário por
ausência de publicação/`stable` que a própria política de execução já
previa, o que treina quem lê a ignorar o alerta (mesmo problema de
princípio do ADR-0001, mecanismo diferente).

## Decisão

1. **Definir formalmente:**

   ```
   V1_REFERENCE_RUNTIME = go1-26
   V1_REFERENCE_DEV     = go1-26-dev
   CATALOG_DEFINITIONS  = 17  (inalterado)
   ```

   Essa definição significa apenas "primeiro fluxo completamente funcional
   e demonstrável" — nunca "únicas imagens suportadas pelo produto".

2. **Introduzir `execution_scope` em `policies/operations/health.json`**,
   um campo novo e distinto de `exceptions`: declara os frameworks
   ativamente publicados/promovidos hoje (`current`), com `reason`,
   `owner`, `review_by` e este ADR. Frameworks fora de `current` recebem,
   no relatório de saúde, o nível `out_of_scope` (visível, não bloqueante)
   em vez de `alert` para `publication_age_hours`/`stable_age_hours` — sem
   tocar `exceptions` (que continua reservado à exclusão permanente do lote
   padrão, mecanismo do ADR-0001) e sem alterar `default_batch.py` ou o
   lote FULL/DEFAULT.

3. **Não alterar o gate de CVE.** `--ignore-unfixed` e a lista de
   severidades bloqueantes permanecem exatamente como são; nenhuma
   exceção, allowlist ou relaxamento foi introduzido para os 13
   frameworks bloqueados por `CVE-2026-85091`.

4. **`stable` continua fora de escopo** para a V1 de referência
   (`STABLE = OUT_OF_SCOPE`), com o kill switch de
   `.github/workflows/promote-stable.yml`
   (`vars.STABLE_PROMOTION_AUTHORIZED`) como controle técnico associado —
   ver achado operacional na spec `2026-09-15-first-corporate-e2e`.

## Consequências

- `pipeline-health.yml` para de gerar alerta vermelho diário por
  frameworks que a própria política de execução já não publica; o relatório
  continua mostrando cada um deles, com o motivo explícito.
- Qualquer pessoa lendo `health.json` vê duas categorias diferentes e não
  as confunde: `exceptions` (fora do catálogo automático, precisa de ADR
  próprio para reentrar) vs. `execution_scope` (fora da execução atual,
  reentra quando a política mudar — sem precisar de código novo).
- A expansão de catálogo (widening de `execution_scope.current`) continua
  dependendo de dois eixos independentes: decisão corporativa (Stage 1 de
  `specs/2026-09-15-first-corporate-e2e/`) e o upstream do zlib — nenhum
  dos dois é resolvido por este ADR.

## Alternativas rejeitadas

- **Reusar `exceptions` para os 15 frameworks fora do escopo atual:**
  rejeitada. `exceptions` alimenta `default_batch.py::exclusions()`, que
  remove o framework do lote padrão FULL/DEFAULT — exatamente o efeito que
  a tarefa que originou este ADR proíbe explicitamente ("não transformar
  Go-only no produto final"). Usar o mecanismo certo (`execution_scope`)
  em vez de forçar o existente evita esse efeito colateral.
- **Silenciar o alerta sem registrar motivo:** rejeitada pelo mesmo
  princípio do ADR-0001 — visibilidade sem alarme, nunca ausência de
  visibilidade.
- **Esperar o zlib ou a decisão corporativa antes de declarar qualquer V1:**
  rejeitada — bloquearia reconhecer o que já está provado (a cadeia Go) por
  algo que não depende deste produto (upstream) nem desta rodada (decisão
  corporativa).

## Critério de expansão (revisão deste ADR)

`execution_scope.current` amplia quando, para o framework candidato:
(a) a validação FULL passa nas duas arquiteturas sem exceção de CVE, e
(b) há decisão de estender build/promoção automáticos a ele. Isso não
exige um ADR novo por framework — só atualizar `execution_scope` com a
data e o motivo. Revisão obrigatória em `2026-09-30`: nessa data, reavaliar
`CVE-2026-85091` contra o `APKINDEX` vivo e o estado das decisões
corporativas do Stage 1; renovar a data se nenhum dos dois mudou, ou
propor a expansão se o zlib corrigido publicar antes disso.

## Evidência

- Cadeia Go completa: `docs/consumer-verification-contract.md`,
  `scripts/verify-image.sh` (execução real registrada contra
  `sha256:6582880f48e9374df03b241c28242c28772086fef50ebcaf87e03662f95916bc`
  em 16/09/2026).
- CVE por framework: relatórios Trivy do run `35049596440` (13 frameworks,
  cada um com exatamente uma vulnerabilidade, `CVE-2026-85091`, `zlib`,
  `1.3.2.1_rc20260601-r0` → `1.3.3-r0` ausente do `APKINDEX`).
- `dotnet8`: inalterado, ver [ADR-0001](0001-dotnet8-fora-do-lote-padrao.md).
