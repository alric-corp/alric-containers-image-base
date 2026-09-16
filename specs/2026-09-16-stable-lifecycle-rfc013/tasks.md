# TASKS — 2026-09-16: `stable` + lifecycle de 7 dias

## T01 — Preflight fail-closed para IMMUTABLE_WITH_EXCLUSION+stable
- Critério: A01.
- [x] Implementar (`scripts/pipeline/release/validate_ecr_repository.py`).
- [x] Verificar (19 testes unitários, incluindo os 5 casos negativos da seção 4 do pedido).
- [x] Registrar evidência.

## T02 — Terraform: mutability exclusion + lifecycle policy
- Critério: A02, A03.
- Arquivos: `alric-containers-registry/main.tf`, `locals.tf`,
  `policies/ecr-lifecycle-7-days.json`.
- [x] Implementar.
- [x] Verificar (`terraform fmt`, `terraform validate`, 9 testes de dados da lifecycle
  policy, 63 testes da suíte completa do repositório).
- [ ] Registrar evidência hospedada (terraform plan real via PR).

## T03 — Binding runtime/dev na promoção
- Critério: A04.
- Arquivos: `scripts/pipeline/release/verify_promotion_pair.py`,
  `verify_promotion_pairs.py`, `.github/workflows/promote-stable.yml` (job `verify-pair`).
- [x] Implementar.
- [x] Verificar (20 testes unitários; `actionlint`; `workflow_dependencies lint`).
- [ ] Registrar evidência hospedada (promoção real).

## T04 — Documentação (ADR-0005, READMEs)
- Critério: A05.
- [x] Implementar (`docs/adr/0005-...md`, `docs/adr/README.md`,
  `alric-containers-registry/README.md`, `drift-remediation/README.md`).
- [x] Verificar (`check_ai_context.py`, links locais).
- [x] Registrar evidência.

## T05 — Reconciliação one-time de mutability (execução real)
- Critério: A06.
- [ ] Anexar `drift-remediation/policy.json` à role
  `alric-github-repo-1371995836` (temporário).
- [ ] `terraform plan` mostra só `image_tag_mutability` +
  `image_tag_mutability_exclusion_filter` mudando, nada mais.
- [ ] `terraform apply` (workflow humano-aprovado).
- [ ] `terraform plan` final = `No changes`.
- [ ] `aws ecr describe-repositories` confirma `IMMUTABLE_WITH_EXCLUSION` + `stable`.
- [ ] Desanexar e apagar a policy temporária.

## T06 — Build normal (candidato apenas)
- Critério: A07.
- [ ] Disparar `workflow.yml` (caminho normal); confirmar `promote-stable` não roda
  (schedule-only) e `stable` não é tocada.

## T07 — Autorizar e executar promoção real
- Critério: A08, A09.
- [ ] `STABLE_PROMOTION_AUTHORIZED=true` (repository variable).
- [ ] Disparar `promote-stable.yml` (`frameworks: ["go1-26","go1-26-dev"]`).
- [ ] Confirmar `verify-pair` PASS (mesmo run/attempt).
- [ ] Confirmar read-back: `stable` runtime/dev == candidato runtime/dev.

## T08 — Exercitar recovery
- Critério: A10.
- [ ] Disparar `recover-stable.yml` contra um digest histórico retido, sem rebuild.
- [ ] Confirmar `stable` movida de volta e read-back.
- [ ] Reverter para o estado promovido em T07 (novo recover, ou nova promoção).

## T09 — Lifecycle preview e apply
- Critério: A11, A12.
- [ ] `aws ecr start-lifecycle-policy-preview` / `get-lifecycle-policy-preview` contra o
  conteúdo real dos dois repositórios.
- [ ] Confirmar `stable` = `NOT_SELECTED_FOR_EXPIRATION`.
- [ ] Confirmar builds >7 dias = `SELECTED` (se existir algum) e <=7 dias =
  `NOT_SELECTED`.
- [ ] STOP se `stable` for selecionada — não aplicar.
- [ ] Aplicar via Terraform (já declarado em T02) e reconfirmar preview pós-apply.

## T10 — Terraform final
- Critério: A13.
- [ ] `terraform plan` final (pós T05–T09) = `No changes`.

## Dependências externas

| Item | Owner | Estado |
| --- | --- | --- |
| Revisão dos PRs (image-base + registry) | Code owners | Pendente |
| Nenhuma outra — reconciliação e execução usam mecanismos já preparados/aprovados nesta sessão | — | — |
