# EVIDENCE — 2026-09-16: `stable` + lifecycle de 7 dias

Estado: **PASS** (A01–A11, A13); **A12 parcial** (limite de tempo real,
não fabricado — ver abaixo).

## Identidade

- Data e ambiente: 2026-09-16, sandbox `alric-corp` + conta AWS pessoal
  (`712107929769`, `us-east-1`).
- Branch e commit base: `alric-containers-image-base` main `140b26f`
  (merge PR #75); `alric-containers-registry` main `94c32b5` (merge PR #4).
- Ferramenta/sessão: Claude Code (Sonnet 5).

## Resultados

| Critério | Estado | Comando, exit code e evidência |
| --- | --- | --- |
| A01 | PASS | `make test-unit` — 19/19 em `test_validate_ecr_repository.py` |
| A02 | PASS | Plan real do PR #4: `image_tag_mutability: IMMUTABLE -> IMMUTABLE_WITH_EXCLUSION` + `image_tag_mutability_exclusion_filter {filter=stable, filter_type=WILDCARD}`, 2 to add / 2 to change / 0 to destroy |
| A03 | PASS | 9/9 em `tests.test_lifecycle_policy` (registry) |
| A04 | PASS | 20/20 em `test_verify_promotion_pair(s).py`; confirmado hospedado (ver A09) |
| A05 | PASS | `check_ai_context.py` OK; ADR-0005 |
| A06 | **PASS** | Antes: 2 policies anexadas à role Infra. Reconciliação: `create-policy`+`attach-role-policy` (drift-remediation), `terraform-apply.yml` run [`35065814431`](https://github.com/alric-corp/alric-containers-registry/actions/runs/35065814431) → `Apply complete! Resources: 2 added, 2 changed, 0 destroyed`. Verificação: `terraform-apply.yml` run [`35065966981`](https://github.com/alric-corp/alric-containers-registry/actions/runs/35065966981) → `No changes`. `detach-role-policy`+`delete-policy`. Depois: 2 policies anexadas — idêntico ao antes |
| A07 | **PASS** | Run [`35066081529`](https://github.com/alric-corp/alric-containers-image-base/actions/runs/35066081529) (`workflow_dispatch`, caminho normal): publicou `160926-0404-r35066081529-a1` para os dois; `promote-stable` = `skipped`; `stable` inexistente antes e depois deste run. **Achado ao vivo não planejado, mantido como evidência**: o run [`35065030357`](https://github.com/alric-corp/alric-containers-image-base/actions/runs/35065030357) (push automático do merge do PR #75, `06:43:32Z`) **falhou** no step "Validate pre-provisioned ECR repository" — o preflight novo (`IMMUTABLE_WITH_EXCLUSION`+`stable` exigido) rejeitou corretamente o ECR ainda não reconciliado (reconciliação só terminou `~06:56Z`). Fail-closed funcionando contra uma janela real, não hipotética |
| A08 | **PASS** | `STABLE_PROMOTION_AUTHORIZED=true`; run [`35066851483`](https://github.com/alric-corp/alric-containers-image-base/actions/runs/35066851483) (`soak-hours=0`, candidato recém-publicado): `Promote go1-26` = success, `Promote go1-26-dev` = success, `Verify runtime/dev promotion pair binding` = success, `Promotion summary` = success |
| A09 | **PASS** | `promotion-evidence.json` de ambos: `promoted:true`, `read_back_status:"confirmed"`, `candidate_digest == stable_digest_observed`. `promotion-pair-binding.json`: `status:"PAIR_BOUND"`, `source_run_id:"35066081529"`, `source_attempt:"1"` para os dois. Read-back **independente** desta máquina (`aws ecr describe-images --image-ids imageTag=stable`) confirma os mesmos dois digests. `scripts/verify-image.sh <framework> stable` → PASS (assinatura+SBOM+provenance) para os dois |
| A10 | **PASS** | Run [`35067110376`](https://github.com/alric-corp/alric-containers-image-base/actions/runs/35067110376) (`recover-stable.yml`, digest histórico `sha256:d9342b26...`, sem rebuild): `completed success`; read-back independente confirma `stable` movida para esse digest exato. Restaurado ao par de T07 pelo run [`35067210461`](https://github.com/alric-corp/alric-containers-image-base/actions/runs/35067210461); estado final: os dois `stable` == par promovido em A08/A09 |
| A11 | **PASS** | `aws ecr start-lifecycle-policy-preview` contra a policy real anexada (7 dias): `expiringImageTotalCount: 0` para os dois — `stable` não selecionada. Teste adicional (preview-only, nunca aplicado): mesma policy com o limiar mínimo permitido pela API (1 dia) em vez de 7 — ainda `0` selecionado, confirmando a proteção mesmo sob limiar agressivo |
| A12 | **PARCIAL — NOT YET OBSERVABLE** | Nenhuma imagem nos dois repositórios tem idade suficiente para ser selecionada (repositórios criados `2026-09-15T17:41Z`, imagem mais antiga com ~13h de idade no momento do teste; a API rejeita limiar `< 1 dia`, e mesmo a 1 dia não há seleção). A seleção positiva (`>7d SELECTED`) está provada pelos 9 testes de dados da policy e pela semântica documentada do ECR (prioridade de regra), mas **não foi observada contra dado real** nesta sessão — genuína limitação de tempo decorrido, não uma lacuna do mecanismo. Reverificar depois que uma imagem realmente ultrapassar 7 dias |
| A13 | **PASS** | `terraform-apply.yml` run [`35067477599`](https://github.com/alric-corp/alric-containers-registry/actions/runs/35067477599), job `plan`: `No changes. Your infrastructure matches the configuration.` — depois de reconciliação, build, promoção e dois recoveries |

## Digests e tags reais desta execução

| | Runtime (`go1-26`) | Dev (`go1-26-dev`) |
| --- | --- | --- |
| Build tag (candidato T06) | `160926-0404-r35066081529-a1` | `160926-0404-r35066081529-a1` |
| Digest promovido a `stable` (T07/T08 final) | `sha256:05041b2ceaacce333174bf033842b3bd716d1e3379ca418f5dcc62ab2277604b` | `sha256:2d55366a623e5f1f258bc213cb10a68cae18f5654f7e263d61ac2e8fff5286eb` |
| Digest de teste de recovery (T08, revertido) | `sha256:d9342b2688702ebc1e442e1f0bbff50c5520979d730aa6d81df2495f7aedd3b8` | — |

## Revisão

Auto-revisão nesta sessão (implementação, PR, execução real e verificação
pelo mesmo agente). Não equivale a revisão independente. Os dois PRs
(#75 image-base, #4 registry) passaram pelos checks obrigatórios
(`test`/`lint-workflows` e `fmt/init/validate/plan`, respectivamente)
antes do merge.

## Limites e resultado

Implementado, comprovado e executado nesta sessão, com evidência
hospedada real (não apenas testes locais): reconciliação one-time de
mutability sem mudança permanente de IAM, preflight fail-closed
(inclusive um achado real não planejado), build normal sem tocar
`stable`, promoção real coordenada com binding runtime/dev verificado,
read-back independente, recovery real sem rebuild, preview de lifecycle
contra dado real (com teste adicional de limiar agressivo), e Terraform
final sem drift.

Não comprovado nesta sessão, por limite de tempo genuíno (não por lacuna
de mecanismo): a seleção positiva de expiração por idade (`>7 dias`) —
nenhuma imagem nos dois repositórios tem essa idade ainda. Recomendação:
reverificar o preview em ~7 dias corridos após a primeira publicação
(`2026-09-15T17:41Z` + 7d) para fechar A12 com dado real.
