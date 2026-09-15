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
- [ ] Revisão independente desta implementação.
- [ ] Integração Git e autorização específica do ensaio.
- [ ] Executar attempt 1 e Re-run failed jobs para attempt 2; coletar evidência real.
- [ ] Revisar e autorizar fase futura de publicação em destino isolado.
- [ ] Avaliar todos os critérios originais antes de encerrar P1-02.

## Execução hospedada — 2026-09-14

- [x] Attempt 1 autorizado, executado e validado no run 34889507318.
- [x] `Re-run failed jobs` executado uma vez; attempt 2 validado sem rebuild.
- [x] Evidências, digests e retenção comparados e registrados.
- [ ] Exercitar continuação da publicação em destino isolado, sob revisão e autorização próprias.
- [ ] Encerrar o aceite integral P1-02 após publicação e verificações correspondentes.

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
- [ ] Nova revisão independente desta correção.
- [ ] Decisão externa de Cloud/IAM sobre role/repos isolados (nada aplicado).
- [ ] Execução hospedada real da continuação de publicação (fase futura, não autorizada nesta sessão).
