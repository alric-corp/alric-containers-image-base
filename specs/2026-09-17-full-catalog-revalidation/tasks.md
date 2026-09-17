# TASKS — 2026-09-17 full-catalog-revalidation

## T01 — Confirmar baseline
- Critério: A02 (indireto — precondição das demais).
- Arquivos e resultado esperado: nenhum arquivo; `git status`/`git rev-parse`.
- [x] Implementar (conferir `HEAD == origin/main`, working tree limpo, staging vazio).
- [x] Verificar (`d2eac6e894a4f2f87e99a4f304775d034fcb7363`; branch local `main` divergente 4/4, registrado e não tocado).
- [x] Registrar evidência (`evidence.md` → Identidade).

## T02 — Disparar `validate-pr-full` real, sem alterar o produto
- Critério: A01, A02.
- Arquivos e resultado esperado: PR descartável, comment-only em `Makefile`.
- [x] Implementar (branch `ops/full-catalog-revalidation-20260917`, PR #81).
- [x] Verificar (`pr_execution_scope` resolveu `FULL`; 16 jobs `Validate <framework>` + `image-trust-gate` = `success`; `build-base-images`/`promote-stable`/`validate-pr` = `skipping`).
- [x] Registrar evidência (`evidence.md` §1; run `35179012804`).

## T03 — Coletar e parsear evidência real (Trivy/apko) das 16 definições
- Critério: A01, A04.
- Arquivos e resultado esperado: artifacts `build-scans-<framework>-1` baixados; matriz estruturada.
- [x] Implementar (`gh run download` por framework; parser Python sobre `trivy-{amd64,arm64}.json`).
- [x] Verificar (32/32 combinações framework×arquitetura limpas; zlib = `1.3.2.1_rc20260601-r0` onde presente; `unfixed-cves-summary.json` vazio em todas).
- [x] Registrar evidência (`evidence.md` §3).

## T04 — Evidência de `dotnet8` sem reintroduzi-lo em nenhum lote
- Critério: A05.
- Arquivos e resultado esperado: consulta ao vivo do `APKINDEX`/`security.json` do Wolfi.
- [x] Implementar (fetch direto, sem cache, `2026-09-17T03:48:54Z`).
- [x] Verificar (`dotnet-8-sdk` máximo `8.0.127-r0`; 5 CVEs reais, nenhuma relacionada a zlib).
- [x] Registrar evidência (`evidence.md` §5).

## T05 — Fechar o mecanismo de trigger sem deixar rastro no produto
- Critério: A03.
- Arquivos e resultado esperado: PR #81 fechado sem merge; branch removida.
- [x] Implementar.
- [x] Verificar (`gh pr view 81` mostra `CLOSED`, não `MERGED`).
- [x] Registrar evidência (`evidence.md` §6).

## T06 — Atualizar ADR-0006 e a matriz vigente sem apagar histórico
- Critério: A06.
- Arquivos e resultado esperado: `docs/adr/0006-*.md` (Addendum, sem reescrever o corpo), `docs/adr/README.md`, nota (sem edição de conteúdo histórico) em `specs/2026-09-16-v1-reference-go126/evidence.md`.
- [x] Implementar.
- [x] Verificar (`git diff` mostra só adição de seção + linha de status; nenhuma linha do corpo original removida).
- [x] Registrar evidência (`evidence.md` §6 e este arquivo).

## T07 — Suíte de verificação após mudanças de evidência/docs
- Critério: todas (regressão).
- Arquivos e resultado esperado: nenhuma mudança de código; `make test-unit`, `check_ai_context.py`, `git diff --check`.
- [x] Implementar.
- [x] Verificar (achado: `test_ai_context` exigia `plan.md`/`tasks.md` completos nesta spec — corrigido criando estes dois arquivos; suíte 100% verde após a correção).
- [x] Registrar evidência (`evidence.md`; este PR).

## Dependências externas

Nenhuma. Revisão independente de code owner segue pendente para este PR e
para o Addendum do ADR-0006 (mesmo padrão do ADR-0006 original).
