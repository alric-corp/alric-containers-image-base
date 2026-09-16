# HANDOFF — 2026-09-16: V1 de referência Go 1.26

- Repositório, branch e commit base: `alric-corp/alric-containers-image-base`,
  branch desta spec a partir de `main` `841e5e7` (pós-merge PR #72).
- Objetivo e pasta da spec: `specs/2026-09-16-v1-reference-go126/` — fechar
  Go 1.26 como V1 de referência, catálogo preservado.
- Estado do diff: `scripts/verify-image.sh` (novo),
  `tests/integration/scripts/test_verify_image.py` (novo),
  `docs/adr/0004-v1-referencia-go126.md` (novo), `docs/adr/README.md`
  (atualizado), `policies/operations/health.json` (`execution_scope`
  adicionado), `scripts/pipeline/operations/operational_health.py`
  (nível `out_of_scope` + alerta `execution_scope_review`),
  `tests/unit/pipeline/operations/test_operational_health.py` (6 testes
  novos), `docs/consumer-verification-contract.md` (seção nova). T01
  (kill switch) já mergeado separadamente como PR #72.
- Tasks concluídas: T01–T05 (ver `tasks.md`).
- Verificações e resultados: `make test-unit` 505/505, `make test-integration`
  33/33, `make lint` limpo, `check_ai_context.py` OK, `git diff --check` OK,
  `shellcheck scripts/verify-image.sh` limpo, execução real de
  `verify-image.sh` contra o digest publicado (PASS).
- Decisões e hipóteses pendentes: nenhuma bloqueia esta entrega — ver
  "Perguntas para o Tech Lead" abaixo para decisões que bloqueiam a
  **expansão**, não esta spec.
- Dependências/autorizações ainda necessárias: nenhuma para mergear esta
  spec (segue revisão normal: CODEOWNERS + `test`/`lint-workflows`).
- Próximo passo: revisão independente deste PR; depois, encaminhar as 5
  perguntas abaixo ao Tech Lead antes de qualquer ampliação de
  `execution_scope` ou de Stage 1 do P0-04.

## Achado operacional registrado nesta sessão (fora desta spec, T01)

Antes desta spec existir, o cron de `promote-stable.yml` (`17 * * * *`) já
tinha um candidato elegível para `go1-26`/`go1-26-dev`. PR #72 (kill switch)
foi aberto, teve `test`+`lint-workflows` verdes, e foi **mergeado pelo
usuário** em `2026-09-16T05:08:55Z`, antes do disparo `05:17Z`. Duas
tentativas de mitigação mais rápida (merge com bypass de revisão via
`--admin`; pausar o workflow via `gh workflow disable`) foram bloqueadas
pelo classificador de modo automático da sessão — corretamente, e não houve
tentativa de contornar isso. Risco real do não-mergeado a tempo, para
registro: a primeira promoção provavelmente teria sucesso (ECR aceita criar
tag nova mesmo em repositório `IMMUTABLE`), mas o ciclo seguinte falharia
permanentemente ao tentar mover essa tag — não destrutivo, mas um job
vermelho recorrente e uma promoção sem a autorização exigida pelo Stage 6.

## Perguntas para o Tech Lead

Só perguntas que exigem decisão humana — nada que o código já responda.

1. **`stable` faz parte da V1 de referência, ou só o consumo por digest
   (`OCI_DIGEST`)?** Hoje `STABLE = OUT_OF_SCOPE` por decisão de escopo
   (ADR-0004) e por bloqueio técnico real (ECR `IMMUTABLE` sem exclusion
   filter). Se `stable` for exigido para a V1, é necessário: (a) Infra
   adicionar o exclusion filter, e (b) autorização explícita do Stage 6
   antes de definir `STABLE_PROMOTION_AUTHORIZED=true`.
2. **É aceitável lançar/expandir Go 1.26/1.25 enquanto `CVE-2026-85091`
   (zlib) bloqueia Java/Node/Python/.NET 10?** O bloqueio é
   genuinamente upstream (confirmado no `APKINDEX` vivo, sem correção
   publicada) — a alternativa seria relaxar o gate, o que este produto não
   faz por política.
3. **Esperamos o Wolfi publicar o zlib corrigido, ou existe uma origem/
   pacote interno aprovado para adiantar isso?** Se houver uma origem
   corporativa aprovada (mirror/build próprio de zlib), a expansão dos 13
   frameworks bloqueados deixa de depender só do upstream. Sem essa
   aprovação, este produto não constrói pacotes por conta própria.
4. **Todos os 15 ECRs de expansão (`docs/adr/0004…` + `evidence.md` desta
   spec) precisam existir antes de ampliar `execution_scope`, ou a
   ampliação pode ser incremental (framework por framework, conforme cada
   ECR for provisionado)?** Afeta a ordem de trabalho de
   `alric-containers-registry`.
5. **Qual o destino operacional real para `external_destination`
   (canal/e-mail de plantão)?** Sem essa decisão, o alerta de saúde
   continua limitado ao próprio job do GitHub Actions — que já funciona,
   mas não notifica ninguém fora de quem acompanha o repositório.

## P0 / P1 / P2

### P0 — necessário para fechar o fluxo Go funcional
- [x] Kill switch de `stable` automático (T01, PR #72 — feito).
- [x] Script de verificação externa do consumidor (T02 — feito).
- [x] `execution_scope` no job de saúde, sem afetar `default_batch.py`
  (T03 — feito).
- [x] Matriz completa + causa individual por framework (T04 — feito).

### P1 — necessário para expandir as demais linguagens
- [ ] Decisão do Tech Lead sobre as 5 perguntas acima.
- [ ] Provisionar os 15 ECRs de expansão (`alric-containers-registry`,
  Terraform) — só depois da decisão da pergunta 4.
- [ ] Monitorar `packages.wolfi.dev` para `zlib >= 1.3.3-r0`; ao publicar,
  reexecutar a validação FULL antes de qualquer ampliação de escopo.
- [ ] Desenhar (não aplicar) um check agregador `v1-reference-validation`
  que represente build+scan+contrato+trust do escopo atual, para não
  tornar as 17 linguagens bloqueio da V1 de referência quando/se
  `required_status_checks` for revisado. Não aplicado nesta sessão —
  mudar branch protection é decisão de escopo largo, fora do que esta
  spec deveria decidir sozinha.
- [ ] Decisão de destino de alerta externo (pergunta 5).

### P2 — hardening/melhorias
- [ ] Investigar por que `go1-25-dev` resolve `zlib` na árvore de
  dependências e `go1-26-dev` não (diferença real observada, causa raiz
  de empacotamento Wolfi não perseguida nesta sessão).
- [ ] Estender `default_batch.py::adr_problem` (ou equivalente) para
  também validar o campo `execution_scope.adr`, hoje só verificado à mão.
- [ ] Corrigir a documentação já identificada como desatualizada (fora do
  escopo desta spec, registrada para sessão própria): `alric-containers-registry/README.md`
  ainda descreve drift/`terraform apply` não executado (ambos falsos após
  o apply `35054207015`); `docs/corporate-adoption.md` ainda trata P1-02
  como pendente (está `CLOSED`); a spec de P1-01 ainda registra
  `HOSTED ACCEPTANCE = NOT RUN` (há PASS hospedado desde 13/09).

## Estado final

```
ENGINE_V1 = PASS
REFERENCE_PRODUCT_V1_GO = PASS
FULL_CATALOG = PRESERVED (17 definições, inalterado)
FULL_CATALOG_V1 = IN_PROGRESS
OTHER_LANGUAGES_REMOVED = NO
SECURITY_GATE_RELAXED = NO
STABLE = OUT_OF_SCOPE
STABLE_AUTOMATIC_PROMOTION = DISABLED_FOR_V1_REFERENCE
```

**GO 1.26 REFERENCE V1 READY — FULL CATALOG PRESERVED, EXPANSION BLOCKERS
DOCUMENTED**

Confirme o estado real do Git antes de continuar.
