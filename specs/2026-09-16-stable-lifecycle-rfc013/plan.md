# PLAN — 2026-09-16: `stable` + lifecycle de 7 dias

## Pesquisa

- `alric-containers-registry/main.tf`: dois módulos `terraform-aws-modules/ecr/aws@3.2.0`,
  `repository_image_tag_mutability = "IMMUTABLE"`, `create_lifecycle_policy = false`.
- Módulo `.terraform/modules/go1_26/variables.tf` (cache local): confirma suporte a
  `repository_image_tag_mutability_exclusion_filter` (`list(object({filter, filter_type}))`)
  e `repository_lifecycle_policy` (string JSON) + `create_lifecycle_policy` (bool) — sem
  necessidade de módulo/versão nova.
- `alric-containers-registry/iam/policies/containers-registry-ecr-permanent.json`: já
  inclui `ecr:GetLifecyclePolicy`/`ecr:PutLifecyclePolicy` (confirmado também na policy
  de fato anexada em AWS, `alric-github-repo-1371995836-ecr`) — lifecycle não exige
  elevação de IAM. `ecr:PutImageTagMutability` está ausente das duas, como documentado.
- `alric-containers-registry/drift-remediation/`: mecanismo já preparado (política
  `policy.json` com exatamente essa ação nos dois ARNs exatos), nunca executado
  (`PREPARED_NOT_APPLIED`). Reusado como está para a reconciliação desta rodada — mesma
  ação, mesmos ARNs, direção oposta ao episódio 1 original.
- `alric-containers-image-base/scripts/pipeline/release/validate_ecr_repository.py` +
  `tests/unit/pipeline/release/test_validate_ecr_repository.py`: preflight fail-closed já
  existente; contrato anterior exigia `IMMUTABLE` puro.
- `.github/workflows/promote-stable.yml`: fluxo de promoção (candidato → verify → re-scan
  → promote → read-back) já implementado desde P1-01/P1-02; só faltava (a) a config de
  ECR por trás funcionar de forma sustentável e (b) verificação de binding runtime/dev,
  que não existia.
- `.github/workflows/recover-stable.yml`: recuperação manual já implementada, sem gate
  extra necessário (é sempre `workflow_dispatch` explícito).
- `scripts/pipeline/release/find_promotion_candidate.py`: evidência de promoção já inclui
  `tag`/`repository`/`candidate_digest` — suficiente para o binding runtime/dev sem
  mudança nesse módulo.

## Estratégia

1. **Preflight (Containers):** `validate_ecr_repository.py` passa a exigir
   `IMMUTABLE_WITH_EXCLUSION` + exatamente `[{filterType: WILDCARD, filter: stable}]`.
   Testes reescritos com os 5 casos negativos da seção 4 do pedido, um a um.
2. **Terraform (Infra):** `main.tf` dos dois módulos ganha
   `repository_image_tag_mutability_exclusion_filter` + `create_lifecycle_policy = true`
   com a policy em `locals.tf` (referenciando `policies/ecr-lifecycle-7-days.json`, arquivo
   JSON puro e testável, não `jsonencode()` inline).
3. **Lifecycle policy:** duas regras por prioridade (proteger `stable` por
   `imageCountMoreThan` alto, depois expirar `*` por `sinceImagePushed: 7 days`) — ver
   ADR-0005 para o raciocínio completo. Testes de dados em
   `alric-containers-registry/tests/test_lifecycle_policy.py`.
4. **Binding runtime/dev:** `verify_promotion_pair.py` (par único) +
   `verify_promotion_pairs.py` (descoberta de pares a partir da lista de frameworks
   pedida) + novo job `verify-pair` em `promote-stable.yml`, depois da matrix de
   promoção. Falha alto sem desfazer a escrita já feita pela matrix.
5. **Docs:** ADR-0005, `docs/adr/README.md`, `alric-containers-registry/README.md`
   (seção P0-04), `drift-remediation/README.md` (episódio 2).
6. **Execução real** (ver `tasks.md`/`evidence.md`): reconciliação one-time → terraform
   plan sem drift → build normal (só candidato) → promoção real → read-back → recovery →
   lifecycle preview (com STOP se `stable` for selecionada) → apply → terraform plan final.

## Decisões e hipóteses

- **Lifecycle policy como arquivo JSON, não `jsonencode()` inline:** decidido para reusar
  o padrão de teste já existente (`tests/test_iam_policies.py`) e permitir validação de
  dados pura, sem precisar renderizar HCL.
- **Proteção de `stable` por prioridade de regra, não por padrão:** decisão explícita do
  pedido (seção 11) — verificado no código do mecanismo ECR (regra 1 reivindica a imagem
  antes que a regra 2 possa vê-la), não assumido.
- **Binding runtime/dev como verificação pós-seleção, não pré-seleção:** evita redesenhar
  a matrix de promoção (que já roda cada framework de forma independente); a alternativa
  (selecionar os dois candidatos juntos antes de promover) seria uma mudança de fluxo maior
  do que o pedido autoriza ("não redesenhar build").
- **Reconciliação via `drift-remediation/` existente, não uma nova política:** o mecanismo
  já foi revisado e preparado para exatamente este tipo de ação (uma ação, dois ARNs
  exatos, anexar-usar-remover); reusar em vez de duplicar.

## Risco e rollback

- Preflight mais estrito: reversível revertendo o commit; nenhuma mudança de estado AWS.
- Terraform: `create_lifecycle_policy = false` + reverter mutability é reversível por PR;
  a reconciliação one-time de mutability em si exige a mesma permissão temporária para
  reverter (mesmo mecanismo, mesma política, na direção oposta).
- `verify-pair`: adiciona um job que pode falhar o run sem desfazer nenhuma escrita já
  feita pela matrix — investigação manual (possivelmente via `recover-stable.yml`) é o
  caminho de correção, não um rollback automático.
- Lifecycle: preview obrigatório com critério de parada explícito (seção 14) antes de
  qualquer apply real.

## Validação

```bash
# Containers
make test-unit && make test-integration && make lint
python3 -B tools/check_ai_context.py && git diff --check

# Infra
terraform fmt -check && terraform validate
python3 -B -m unittest discover -s tests -v

# Execução real (ver evidence.md para os resultados)
aws ecr describe-repositories --repository-names image-base-go1-26 image-base-go1-26-dev
terraform plan   # antes e depois da reconciliação
aws ecr start-lifecycle-policy-preview / get-lifecycle-policy-preview
```
