# TASKS — P1-02

- [x] T01 / A01–A08: ler contexto, reconstruir producer/consumer e semântica oficial.
- [x] T02 / A01–A08: escrever spec, plano e aceite antes da implementação.
- [x] T03 / A03/A04: registrar contexto do producer e validar binding por digest.
- [x] T04 / A02/A05/A06/A07: seleção determinística fail-closed e metadados por run.
- [x] T05 / A02/A08: integrar consumer sem rebuild nem alteração shared.
- [x] T06 / A01–A08: testes e verificações locais, negativos explícitos.
- [x] T07 / A01–A08: atualizar documentação, evidence e handoff final.

Revisão Opus 5 MAX e hosted rerun posteriores. Não commit/push/PR nesta fatia.


## Rodada local do laboratório — 2026-09-14

Os itens anteriores preservam o histórico da implementação/reconciliação.

- [x] Confirmar merge do PR #63 e avançar main por fast-forward limpo.
- [x] Acrescentar requisitos do laboratório na spec existente antes do código.
- [x] Workflow dedicado, guard de evento/revisão e par Go fixo; sem AWS/publicação.
- [x] Executar gate real e preservar baseline antes da barreira determinística.
- [x] Comparar artifacts, reports e execução dos producers através de metadados reais.
- [x] Testar CLI, ambos attempts e negativos em fixtures locais.
- [x] Preparar plano de execução, retenção e checklist de evidências.
- [x] Revisão independente desta implementação — concluído posteriormente: revisões independentes retornaram CHANGES REQUIRED (F1/F2, ver "Implementação local do job de publicação — 2026-09-15") e depois APPROVE ("Correção F1/F2..." e "Correção do job_inventory para reconhecer Lab publish — 2026-09-15").
- [x] Integração Git e autorização específica do ensaio — concluído posteriormente: PRs #63/#64/#66/#67/#68 mergeados; autorização explícita concedida para cada attempt hospedado (execução hospedada — 2026-09-14 e ciclo final do run 34986578076).
- [x] Executar attempt 1 e Re-run failed jobs para attempt 2; coletar evidência real — concluído posteriormente: run 34889507318 (primeiro ciclo) e, principalmente, o ciclo final no run 34986578076 (Attempt 1 + Attempt 2, ver "Hosted acceptance final — 2026-09-15" abaixo).
- [x] Revisar e autorizar fase futura de publicação em destino isolado — concluído posteriormente: proposta de infraestrutura revisada/corrigida/entregue, provisionamento real e execução hospedada com `PUBLICATION_CONTINUATION = PASS` (run 34986578076, publication artifact ID `10405325731`).
- [x] Avaliar todos os critérios originais antes de encerrar P1-02 — concluído posteriormente: ver [acceptance.md](acceptance.md#hosted-acceptance-final--2026-09-15), mapeamento final R1–R8/A01–A08 e revisão independente final (APPROVE WITH MINOR CHANGES).

## Execução hospedada — 2026-09-14

- [x] Attempt 1 autorizado, executado e validado no run 34889507318.
- [x] `Re-run failed jobs` executado uma vez; attempt 2 validado sem rebuild.
- [x] Evidências, digests e retenção comparados e registrados.
- [x] Exercitar continuação da publicação em destino isolado, sob revisão e autorização próprias — concluído no run 34986578076.
- [x] Encerrar o aceite integral P1-02 após publicação e verificações correspondentes — ver seção "Hosted acceptance final" abaixo.

## Implementação local do job de publicação — 2026-09-15

- [x] Job `lab-publish` implementado, condicionado a attempt 2 + `lab-retry` verde.
- [x] Binding fail-closed antes de qualquer auth AWS, reutilizando `retry_lab.context`/`valid_gate`.
- [x] Guard de destino (conta/região/role/repos exatos) e tag determinística, sem input livre.
- [x] Profile A: preflight somente leitura, sem `CreateRepository`/`PutImageTagMutability`.
- [x] Publicação por digest, read-back, Cosign, provenance e SBOM reutilizando o caminho produtivo.
- [x] Autoverificação com identidade própria do laboratório; `signing-identities.json` inalterado.
- [x] Guard de stable/latest/`image-base-*` testado fail-closed; sem caminho de promote/recovery.
- [x] Testes locais novos e dedicados; `make test-unit`/`test-integration`/lints/actionlint OK.
- [x] Revisão independente desta implementação (retornou CHANGES REQUIRED: F1/F2).

## Correção F1/F2 da revisão adversarial — 2026-09-15

- [x] F1: `require_gate_layout_binding` liga o OCI revalidado ao `index_digest`/`dev_index_digest` do gate, antes de qualquer auth AWS.
- [x] F1: `finalize()` reforça a mesma cadeia gate↔verified↔validated↔copied↔remote.
- [x] F1: teste do cenário `overwrite: true` (artifact substituído, digest B internamente coerente) no guard pré-AWS e em `finalize`.
- [x] F2: `digest_equal` passou a usar `contract_evidence.digest()` antes de comparar.
- [x] Novo step no workflow entre revalidação OCI e auth AWS, sem `continue-on-error`, valores via `env:`.
- [x] `make test-unit`/`test-integration`/lints/actionlint OK após a correção.
- [x] Nova revisão independente desta correção.
- [x] Decisão externa de Cloud/IAM sobre role/repos isolados — infraestrutura real provisionada e verificada.
- [x] GitHub Repository Variables `LAB_*` configuradas e verificadas.
- [x] Execução hospedada real do run `34976226951`: attempt 1 PASS.
- [ ] Execução hospedada real do run `34976226951`: attempt 2 — FAILED antes do gate de retry/reuse (`job_inventory` rejeitava `Lab publish`).

## Correção do job_inventory para reconhecer Lab publish — 2026-09-15

- [x] Bug reproduzido isoladamente (fora do contexto hospedado) antes de qualquer alteração de código.
- [x] Causa raiz confirmada: `job_inventory()` não reconhecia o job `Lab publish`.
- [x] Nova constante `PUBLISHER = 'Lab publish'`; `job_inventory()` passou a reconhecê-lo e ignorá-lo, sem tratá-lo como producer.
- [x] Fail-closed preservado: nomes desconhecidos (`'Lab unknown'`, `'Lab publisher'`, etc.) continuam rejeitados; sem `startswith('Lab ')` permissivo.
- [x] Testes novos: presença de `Lab publish` em qualquer estado não altera manifesto/producers/`latest_producer_attempt`/`selected_attempt`/`reused`; reuse válido com `Lab publish` presente; newer-producer-failure continua invalidando reuse; teste de drift nomes-do-workflow ↔ constantes.
- [x] `retry_lab_publish.py`/AWS/ECR/IAM não alterados (nenhuma dependência demonstrada).
- [x] `make test-unit`/`test-integration`/lints/actionlint/`check_ai_context`/`git diff --check` OK.
- [x] Nova revisão independente desta correção (retornou APPROVE).
- [x] Novo attempt hospedado (dispatch novo, não rerun) após a revisão — run 34986578076, attempt 1.

## Hosted acceptance final — 2026-09-15

- [x] Novo `workflow_dispatch` (run `34986578076`, baseline `b910bd076021fc349615ee7dd191c7da9f3a009e`); attempt 1 PASS (barreira controlada, exit 42).
- [x] `gh run rerun --failed` (mesmo run); attempt 2 PASS — `job_inventory` reconhece `Lab publish` em produção hospedada, sem "unexpected job".
- [x] No rebuild confirmado: `execution_metadata_equal=true` em 12/12 producers; digests/report hashes idênticos; nenhum `runtime-go1-26-2` criado.
- [x] Gate-to-layout binding validado (`layout-binding.json`, `LAYOUT_BOUND_TO_GATE`) antes de qualquer auth AWS.
- [x] Role OIDC isolada (`github-actions-image-base-p102-lab`) assumida pela primeira vez; `RoleLastUsed` preenchido.
- [x] ECR preflight `IMMUTABLE` sem exclusion filters, ambos os repositórios.
- [x] Publicação runtime+dev por digest com read-back idêntico (`gate == verified == validated == copied == remote`).
- [x] Multiarch (amd64/arm64) preservado para runtime e dev, confirmado no registry real.
- [x] Cosign (assinatura) verificado com identidade do laboratório (não a identidade produtiva).
- [x] SBOM SPDX attestado e verificado, subjects vinculados aos digests publicados.
- [x] Provenance SLSA attestado e verificado, `signer-workflow` do laboratório.
- [x] Stable isolation: `stable_touched=false`; repositórios operacionais `image-base-go1-26`/`-dev` sem escrita nova.
- [x] Evidência de publicação preservada (`runtime-lab-p1-02-publication-34986578076-2`, ID `10405325731`).
- [ ] Aceite corporativo, P1-04, homologação AppSec, promoção de stable em produção — fora de escopo desta spec, não iniciados.
