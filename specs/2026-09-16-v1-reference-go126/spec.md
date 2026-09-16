# SPEC — 2026-09-16: V1 de referência Go 1.26

## Objetivo

Fechar `go1-26`/`go1-26-dev` como **V1 de referência** — o primeiro fluxo
completamente funcional, demonstrável e verificável externamente da
plataforma — sem remover, excluir ou despriorizar permanentemente nenhuma
das outras 16 definições do catálogo, e sem relaxar o gate de CVE.

```
V1_REFERENCE_RUNTIME = go1-26
V1_REFERENCE_DEV      = go1-26-dev
CATALOG_DEFINITIONS   = 17  (inalterado por esta spec)
```

Ver [ADR-0004](../../docs/adr/0004-v1-referencia-go126.md) para o registro de
decisão completo. Esta spec cobre apenas o trabalho de código/documentação
desta sessão; não substitui aceites hospedados anteriores (P1-01, P1-02,
P1-03, P0-04) nem decide sobre eles.

## Requisitos

- R1: nenhum disparo automático (cron ou `workflow_dispatch`) de
  `promote-stable.yml` pode escrever `stable` enquanto `STABLE` estiver
  `OUT_OF_SCOPE` para a V1 de referência.
- R2: um consumidor externo, sem checkout do repositório e sem contexto de
  CI, deve conseguir verificar assinatura, SBOM attestation e provenance de
  um digest publicado usando só `aws`, `docker`, `cosign` e `gh`.
- R3: o job de saúde operacional não deve gerar `alert` só porque um
  framework fora do escopo de execução atual não tem publicação/`stable`
  recentes — sem remover esse framework do catálogo nem do lote
  FULL/DEFAULT (`default_batch.py`).
- R4: a causa de bloqueio de cada um dos 17 itens do catálogo deve estar
  registrada individualmente, com evidência (não suposição agregada), e
  classificada por dono (`OUR_CODE` / `UPSTREAM` / `INFRA_REQUIRED` /
  `EXTERNAL_DECISION` / `NOT_TESTED`).

## Restrições e invariantes

- Não alterar `--ignore-unfixed`, a lista de severidades bloqueantes, nem
  qualquer allowlist/exceção de CVE.
- Não remover nenhum arquivo de `frameworks/`.
- Não alterar `default_batch.py::exclusions()` nem o mecanismo de
  `exceptions` já usado pelo ADR-0001 (`dotnet8`) — o novo mecanismo desta
  spec (`execution_scope`) é deliberadamente separado, para não produzir o
  mesmo efeito de exclusão permanente do lote padrão.
- Não provisionar ECR novo nesta rodada (`alric-containers-registry` só
  provisiona `go1-26`/`go1-26-dev` hoje); apenas listar o que a expansão
  vai exigir.
- Não modificar branch protection/required checks nesta rodada — registrar
  como recomendação (P1), não aplicar.

## Fora do escopo

- Resolver `CVE-2026-85091` (zlib) — bloqueio upstream, sem ação possível
  deste produto além de monitorar o APKINDEX.
- Ampliar `execution_scope.current` para outros frameworks.
- Configurar destino externo de alerta (`external_destination`) — decisão
  corporativa pendente, não inventada aqui.
- Qualquer aceite corporativo do P0-04 (Stage 1 de
  `specs/2026-09-15-first-corporate-e2e/` continua bloqueado nos mesmos
  itens externos).

## Dependências

| Item | Owner | Bloqueia esta entrega? |
| --- | --- | --- |
| Fix de `zlib` no Wolfi (`>= 1.3.3-r0`) | Upstream (Wolfi) | Não — bloqueia expansão, não a V1 de referência |
| `dotnet-8-sdk >= 8.0.129-r1` no Wolfi | Upstream (Wolfi) | Não — já isolado pelo ADR-0001 |
| ECR corporativo/decisões do Stage 1 | Cloud/IAM, PKI, AppSec, Segurança | Não — fora do escopo desta spec |
| Revisão independente deste PR | Code owner do repositório | Sim, para merge (CODEOWNERS + `test`/`lint-workflows`) |

## Conclusão

Ver [acceptance.md](acceptance.md) e [evidence.md](evidence.md).
