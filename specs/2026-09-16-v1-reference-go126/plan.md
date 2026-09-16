# PLAN — 2026-09-16: V1 de referência Go 1.26

## Pesquisa

Fontes consultadas nesta sessão (todas ao vivo, não só documentação):

- `aws ecr describe-repositories` / `describe-images`: só `image-base-go1-26`
  e `image-base-go1-26-dev` existem hoje; ambos `IMMUTABLE`, sem exclusion
  filter, sem repository policy, sem lifecycle. Nenhuma tag `stable` em
  nenhum dos dois.
- `find_promotion_candidate.py` executado localmente contra o
  `describe-images` real: o build de 15/09 18:01 já era elegível para
  promoção antes desta sessão — a rotina de soak não olha para
  `execution_scope`, só para idade e ausência de `stable`.
- `.github/workflows/promote-stable.yml` / `workflow.yml`: o job
  `promote` do primeiro é disparável por `schedule` OU `workflow_dispatch`
  independente de `workflow.yml` (o segundo só gateia o cron, não o
  dispatch direto do arquivo reusável).
- `.reusable-workflows/.github/workflows/validate-apko-images.yml`: prova
  code-level de build-once (`Build multi-architecture OCI artifact once`
  roda uma vez, scan roda em cima do mesmo `${FRAMEWORK}.oci`, artifact
  `validated-oci-${framework}` é o que o publicador consome depois).
- `scripts/pipeline/artifacts/oci_artifact.py::verify`: aborta se o índice
  não tiver exatamente `linux/amd64` + `linux/arm64` — multiarch é
  code-enforced, não so observado.
- `.github/workflows/build-base-images.yml`: `EXPECTED` (digest validado)
  == `ACTUAL` (`skopeo copy --preserve-digests --digestfile`) ==
  read-back independente da tag — os três comparados por `test`.
- Run `35049596440` (FULL catalog validation do PR #71/#72): 16 jobs de
  `validate` (dotnet8 fica fora de todo lote desde o ADR-0001); 3
  `success` (`go1-25`, `go1-26`, `go1-26-dev`), 13 `failure`, todos no
  step "Scan both architectures".
- 13 artifacts `build-scans-<framework>-1` desse run baixados e
  parseados individualmente (`trivy-amd64.json`): as 13 falhas são,
  cada uma, exatamente 1 vulnerabilidade, `CVE-2026-85091`, pacote
  `zlib`, `1.3.2.1_rc20260601-r0` → `1.3.3-r0`, `MEDIUM`.
- `packages.wolfi.dev/os/x86_64/APKINDEX.tar.gz` baixado e parseado por
  blocos `P:`/`V:` (não `grep` isolado, que deu falso positivo): 14 builds
  históricos de `zlib`, o mais novo é o RC vulnerável; `1.3.3-r0` não
  existe nessa origem. Mesma verificação para `dotnet-8-sdk`: máximo
  `8.0.127-r0`, `>= 8.0.129-r1` ainda ausente — ADR-0001 continua atual.
- `policies/operations/health.json` / `operational_health.py`:
  `exceptions` alimenta `default_batch.py::exclusions()` (remove do lote
  padrão) — mecanismo errado para "fora do escopo de execução atual, mas
  ainda no catálogo". Confirmado lendo `default_batch.py::exclusions()`
  antes de escrever qualquer policy nova.
- `docs/consumer-verification-contract.md`: os três comandos de
  verificação (`cosign verify`, `cosign verify-attestation`,
  `gh attestation verify`) já documentados manualmente; executados de
  verdade contra `sha256:6582880f…` nesta e na sessão anterior — todos
  `PASS`.

## Estratégia

1. **Urgente, fora desta spec formalmente mas registrado aqui:** kill
   switch em `promote-stable.yml` (`vars.STABLE_PROMOTION_AUTHORIZED`) —
   PR #72, já mergeado antes do próximo disparo do cron (`17 * * * *`).
2. `scripts/verify-image.sh` + `tests/integration/scripts/test_verify_image.py`
   + referência em `docs/consumer-verification-contract.md`.
3. `docs/adr/0004-v1-referencia-go126.md` + entrada em `docs/adr/README.md`.
4. `policies/operations/health.json#execution_scope` (campo novo,
   independente de `exceptions`).
5. `scripts/pipeline/operations/operational_health.py::evaluate` — nível
   `out_of_scope` + alerta `execution_scope_review`; `render()` atualizado.
6. Testes unitários novos em
   `tests/unit/pipeline/operations/test_operational_health.py`.
7. Matriz completa dos 17 frameworks + lista de ECRs de expansão +
   perguntas ao Tech Lead + prioridades P0/P1/P2 → `evidence.md` desta
   spec (registro durável) e relatório final da sessão.

## Decisões e hipóteses

- **`execution_scope` separado de `exceptions`**: ver "Alternativas
  rejeitadas" no ADR-0004. Verificado lendo o código antes de decidir —
  não é suposição.
- **Não tocar branch protection**: ação de escopo largo e reversão
  custosa; registrado como recomendação P1 (ver `handoff.md`), não
  aplicado.
- **Não configurar `external_destination`**: nenhum destino real pessoal
  disponível que não seja inventado; mantido como finding
  `EXTERNAL_DECISION`, conforme a própria instrução da tarefa.
- **`review_by` de `execution_scope` em 2026-09-30**: horizonte curto (2
  semanas), mais agressivo que o do ADR-0001 (~1 mês), porque esta é uma
  decisão de rollout ativo, não uma exceção crônica de fim de vida.

## Risco e rollback

- Kill switch: reversível setando `STABLE_PROMOTION_AUTHORIZED=true`
  (repo variable) quando o Stage 6 for autorizado. Sem efeito colateral
  em build/validate.
- `execution_scope`: reversível removendo o campo (volta ao comportamento
  anterior, testado explicitamente em
  `test_absent_execution_scope_behaves_exactly_as_before`) ou ampliando
  `current`.
- `verify-image.sh`: arquivo novo, sem dependência de nada existente;
  remoção não afeta nenhum outro componente.
- Nenhuma mudança altera `default_batch.py::exclusions()`,
  `--ignore-unfixed`, severidades, ECR, ou o catálogo em `frameworks/`.

## Validação

```bash
make test-unit          # 505 testes — inclui os novos de operational_health
make test-integration   # 33 testes — inclui os 9 novos de verify-image.sh
make lint                # workflow hardening, pins, default_batch, workflow
                          # deps, operational_health lint, actionlint
python3 -B tools/check_ai_context.py
git diff --check
./scripts/verify-image.sh go1-26 sha256:6582880f... --account 712107929769 \
  --region us-east-1   # execução real contra o artifact publicado
```

Ver resultados reais em [evidence.md](evidence.md).
