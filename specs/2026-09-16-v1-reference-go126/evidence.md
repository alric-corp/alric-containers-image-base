# EVIDENCE — 2026-09-16: V1 de referência Go 1.26

Estado: **PASS** (A01–A05, com os limites registrados em `acceptance.md`).

> **Nota (17/09/2026):** a matriz completa do catálogo abaixo (`§ Matriz
> completa do catálogo`) é um retrato de 16/09/2026 e **não reflete o
> estado atual** — o bloqueio `CVE-2026-85091`/zlib registrado para 13 das
> 17 definições foi resolvido pelo Wolfi no dia seguinte. Estado atual e
> revalidado via CI real:
> [`specs/2026-09-17-full-catalog-revalidation/evidence.md`](../2026-09-17-full-catalog-revalidation/evidence.md).
> Este arquivo não foi editado além desta nota — preserva o registro
> histórico do que se sabia em 16/09/2026.

## Identidade

- Data e ambiente: 2026-09-16, sandbox `alric-corp` (GitHub) + conta AWS
  pessoal (`712107929769`, `us-east-1`).
- Branch e commit base: `alric-corp/alric-containers-image-base`, criado a
  partir de `main` `841e5e7` (pós-merge do PR #72).
- Diff: ver PR desta spec (T01 já mergeado separadamente como PR #72, por
  urgência operacional; T02–T05 nesta spec).
- Ferramenta/sessão: Claude Code (Sonnet 5).

## Resultados

| Critério | Estado | Comando, exit code e evidência |
| --- | --- | --- |
| A01 | PASS | PR #72 mergeado `2026-09-16T05:08:55Z`; `actionlint` exit 0; `gh variable list` confirma `STABLE_PROMOTION_AUTHORIZED` ausente antes e depois |
| A02 | PASS | `./scripts/verify-image.sh go1-26 sha256:6582880f48e9374df03b241c28242c28772086fef50ebcaf87e03662f95916bc --account 712107929769 --region us-east-1` → exit 0, `RESULTADO: PASS` nas três verificações; também testado por tag (`160926-0054-r35049882743-a3`), mesmo digest resolvido |
| A03 | PASS | `make test-unit` 505/505 (24 em `test_operational_health.py`, 6 novos); `default_batch.py lint` → "17 framework(s) no catálogo, 1 excluído(s)" (inalterado) |
| A04 | PASS | Ver matriz completa abaixo |
| A05 | PASS | Ver lista de expansão abaixo |

`make lint` completo, `python3 -B tools/check_ai_context.py` e
`git diff --check`: todos exit 0 nesta sessão, depois de todas as mudanças.

## Matriz completa do catálogo (17 definições)

Fonte: run `35049596440` (validação FULL, PR #71→#72, commit `5e60b28`),
13 artifacts `build-scans-<framework>-1` baixados e parseados
individualmente (não suposição agregada); `aws ecr describe-repositories`
ao vivo; `packages.wolfi.dev/os/x86_64/APKINDEX.tar.gz` parseado
estruturalmente (blocos `P:`/`V:`, não `grep` isolado).

| Framework | Build | amd64 | arm64 | Trivy | Unfixed CVE visibility | Contrato funcional | ECR provisionado | Publicação | Blocker atual | Dono |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `go1-26` | PASS | PASS | PASS | PASS | — | PASS (compilado) | PASS | PASS (publicado, assinado, atestado) | nenhum | — |
| `go1-26-dev` | PASS | PASS | PASS | PASS | — | PASS (companion) | PASS | PASS | nenhum | — |
| `go1-25` | PASS | PASS | PASS | PASS | — | NOT_TESTED¹ | NÃO | NOT_READY | fora do `execution_scope` + sem ECR | INFRA_REQUIRED / EXTERNAL_DECISION |
| `go1-25-dev` | PASS | PASS | PASS | **FAIL** | N/A² | NOT_TESTED¹ | NÃO | NOT_READY | `CVE-2026-85091` (zlib) | UPSTREAM |
| `java21` | PASS | PASS | PASS | **FAIL** | N/A² | NOT_TESTED¹ | NÃO | NOT_READY | `CVE-2026-85091` (zlib) | UPSTREAM |
| `java21-dev` | PASS | PASS | PASS | **FAIL** | N/A² | NOT_TESTED¹ | NÃO | NOT_READY | `CVE-2026-85091` (zlib) | UPSTREAM |
| `java25` | PASS | PASS | PASS | **FAIL** | N/A² | NOT_TESTED¹ | NÃO | NOT_READY | `CVE-2026-85091` (zlib) | UPSTREAM |
| `java25-dev` | PASS | PASS | PASS | **FAIL** | N/A² | NOT_TESTED¹ | NÃO | NOT_READY | `CVE-2026-85091` (zlib) | UPSTREAM |
| `nodejs22` | PASS | PASS | PASS | **FAIL** | N/A² | NOT_TESTED¹ | NÃO | NOT_READY | `CVE-2026-85091` (zlib) | UPSTREAM |
| `nodejs22-dev` | PASS | PASS | PASS | **FAIL** | N/A² | NOT_TESTED¹ | NÃO | NOT_READY | `CVE-2026-85091` (zlib) | UPSTREAM |
| `nodejs24` | PASS | PASS | PASS | **FAIL** | N/A² | NOT_TESTED¹ | NÃO | NOT_READY | `CVE-2026-85091` (zlib) | UPSTREAM |
| `nodejs24-dev` | PASS | PASS | PASS | **FAIL** | N/A² | NOT_TESTED¹ | NÃO | NOT_READY | `CVE-2026-85091` (zlib) | UPSTREAM |
| `python3-13` | PASS | PASS | PASS | **FAIL** | N/A² | NOT_TESTED¹ | NÃO | NOT_READY | `CVE-2026-85091` (zlib) | UPSTREAM |
| `python3-14` | PASS | PASS | PASS | **FAIL** | N/A² | NOT_TESTED¹ | NÃO | NOT_READY | `CVE-2026-85091` (zlib) | UPSTREAM |
| `dotnet10` | PASS | PASS | PASS | **FAIL** | N/A² | NOT_TESTED¹ | NÃO | NOT_READY | `CVE-2026-85091` (zlib) | UPSTREAM |
| `dotnet10-dev` | PASS | PASS | PASS | **FAIL** | N/A² | NOT_TESTED¹ | NÃO | NOT_READY | `CVE-2026-85091` (zlib) | UPSTREAM |
| `dotnet8` | PASS³ | PASS³ | PASS³ | FAIL³ | N/T⁴ | NUNCA (excluído desde ADR-0001) | NÃO | NOT_READY | `dotnet-8-sdk` sem `8.0.129-r1` | UPSTREAM (já com [ADR-0001](../../docs/adr/0001-dotnet8-fora-do-lote-padrao.md)) |

¹ `build-base-images.yml` (onde o contrato funcional roda) só executa para
o lote da `execution_scope` atual em push/schedule/dispatch na `main`; PRs
nunca o executam. Não é falha — é escopo de execução, e é exatamente o que
esta spec passou a distinguir de falha real no job de saúde.

² A vulnerabilidade **tem** `FixedVersion` segundo o banco do Trivy
(`1.3.3-r0`) — não é "sem correção" pela definição usada por
`--ignore-unfixed`/`report_unfixed_cves.py`. Por isso não aparece no
relatório informacional de CVEs sem correção (confirmado:
`unfixed-cves-summary.json` vazio para `dotnet10`) e por isso
`--ignore-unfixed` não a filtra: o bloqueio é por o pacote corrigido não
existir na origem Wolfi consultada, não por severidade/política.

³ Histórico documentado pelo [ADR-0001](../../docs/adr/0001-dotnet8-fora-do-lote-padrao.md)
(build/scan reais anteriores a esta sessão); `dotnet8` está excluído de
`validate-pr`, `build-base-images` e `promote-stable` desde então, então
não foi re-executado nesta sessão. Não confundir com os outros 15
frameworks, cujo Trivy `FAIL` **foi** reconfirmado nesta sessão
(run `35049596440`, hoje).

⁴ Não verificado nesta sessão (framework não roda nos lotes automáticos);
não presumido igual aos outros por analogia — é um CVE diferente
(`dotnet-8-sdk`, não `zlib`).

### Confirmação do bloqueio upstream (zlib)

`packages.wolfi.dev/os/x86_64/APKINDEX.tar.gz`, parseado por blocos
estruturados (`P:`/`V:`, 16/09/2026):

```
P:zlib — 14 builds históricos
mais recente: V:1.3.2.1_rc20260601-r0  (release candidate, ainda vulnerável)
1.3.3-r0 (versão corrigida exigida pelo advisory): AUSENTE
```

`dotnet-8-sdk` (mesma origem, mesma data): máximo `8.0.127-r0`;
`>= 8.0.129-r1` exigido pelo ADR-0001 continua ausente — sem mudança desde
09/09 e 12/09/2026.

## Lista de expansão de ECR (`ECR_REQUIRED_FOR_EXPANSION`)

Confirmado ao vivo (`aws ecr describe-repositories`): só
`image-base-go1-26` e `image-base-go1-26-dev` existem hoje. Nenhum
provisionado nesta rodada — lista apenas, para quando a decisão de ampliar
`execution_scope` for tomada. Owner do provisionamento:
`alric-containers-registry` (Terraform), nunca o publicador
(`PREPROVISIONED_ONLY`).

| Repositório ECR necessário | Framework(s) |
| --- | --- |
| `image-base-go1-25` | `go1-25` |
| `image-base-go1-25-dev` | `go1-25-dev` |
| `image-base-java21` | `java21` |
| `image-base-java21-dev` | `java21-dev` |
| `image-base-java25` | `java25` |
| `image-base-java25-dev` | `java25-dev` |
| `image-base-nodejs22` | `nodejs22` |
| `image-base-nodejs22-dev` | `nodejs22-dev` |
| `image-base-nodejs24` | `nodejs24` |
| `image-base-nodejs24-dev` | `nodejs24-dev` |
| `image-base-python3-13` | `python3-13` |
| `image-base-python3-14` | `python3-14` |
| `image-base-dotnet10` | `dotnet10` |
| `image-base-dotnet10-dev` | `dotnet10-dev` |
| `image-base-dotnet8` | `dotnet8` (mantido no catálogo pelo ADR-0001; ECR só se pedido manualmente) |

```
ECR_REQUIRED_FOR_EXPANSION = YES (15 repositórios)
ECR_PROVISIONED_TODAY = 2 (go1-26, go1-26-dev)
```

## Revisão

Auto-revisão nesta sessão (implementação e verificação pelo mesmo agente).
Não equivale a revisão independente — o PR desta spec segue o fluxo normal
de CODEOWNERS antes do merge (diferente do PR #72/T01, mergeado sob
urgência operacional documentada em `handoff.md`).

## Limites e resultado

Implementado e comprovado nesta sessão: kill switch de `stable`,
`execution_scope` no job de saúde (código + testes), ADR-0004,
`scripts/verify-image.sh` (execução real contra artifact publicado),
matriz completa dos 17 itens do catálogo com causa individual verificada,
lista de expansão de ECR.

Não implementado, não decidido, e não presumido: fix do zlib upstream,
ampliação de `execution_scope`, provisionamento de qualquer ECR novo,
destino externo de alerta, qualquer mudança de branch protection/required
checks, qualquer aceite corporativo do P0-04 (Stage 1 continua bloqueado
nos mesmos itens de `specs/2026-09-15-first-corporate-e2e/`).
