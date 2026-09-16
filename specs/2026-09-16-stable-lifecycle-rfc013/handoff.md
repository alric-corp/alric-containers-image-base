# HANDOFF — 2026-09-16: `stable` + lifecycle de 7 dias

- Repositórios: `alric-corp/alric-containers-image-base` (main `140b26f`
  + esta evidência) e `alric-corp/alric-containers-registry` (main
  `94c32b5`).
- Objetivo e pasta da spec: `specs/2026-09-16-stable-lifecycle-rfc013/`.
- Estado: **T01–T10 concluídos**, com execução real (não só código/testes
  locais). Ver `evidence.md` para todos os run IDs e digests.
- Tasks concluídas: todas (`tasks.md`), exceto a metade positiva de A12
  (seleção de expiração por idade >7 dias — nenhuma imagem tem essa idade
  ainda; não é lacuna de mecanismo, é limite de tempo decorrido real).
- Verificações e resultados: PRs #75/#4 mergeados com checks obrigatórios
  verdes; reconciliação one-time de IAM sem mudança permanente; promoção
  real com binding runtime/dev verificado; recovery real exercitado e
  revertido; Terraform final sem drift.
- Decisões e hipóteses pendentes: nenhuma.
- Dependências/autorizações ainda necessárias: nenhuma para o estado
  atual. Reverificação futura recomendada (não bloqueante): repetir o
  preview de lifecycle depois que uma imagem realmente ultrapassar 7 dias
  (repositórios criados `2026-09-15T17:41Z`), para fechar A12 com dado
  positivo real.
- Próximo passo: nenhum obrigatório. `image-base-go1-26:stable` e
  `image-base-go1-26-dev:stable` já são consumíveis pela forma oficial da
  RFC-013 (`FROM image-base-go1-26:stable`).

## Estado final real (verificado, não projetado)

```
stable (go1-26)     = sha256:05041b2ceaacce333174bf033842b3bd716d1e3379ca418f5dcc62ab2277604b
stable (go1-26-dev) = sha256:2d55366a623e5f1f258bc213cb10a68cae18f5654f7e263d61ac2e8fff5286eb
STABLE_TOUCHED = true (só via promote-stable.yml/recover-stable.yml)
ECR mutability (ambos) = IMMUTABLE_WITH_EXCLUSION, exclusão única: stable
lifecycle (ambos) = 7 dias, stable protegida (confirmado por preview real)
IAM da role Infra = idêntica ao estado anterior à reconciliação (2 policies)
terraform plan = No changes
```

Confirme o estado real do Git antes de continuar.
