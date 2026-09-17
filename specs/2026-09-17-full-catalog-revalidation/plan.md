# PLAN — 2026-09-17 full-catalog-revalidation

## Pesquisa

Baseline `d2eac6e894a4f2f87e99a4f304775d034fcb7363` (`HEAD` == `origin/main`).
Lidos: [ADR-0006](../../docs/adr/0006-java21-zlib-blocker-remediation-options.md)
(investigação original do bloqueio zlib), [ADR-0001](../../docs/adr/0001-dotnet8-fora-do-lote-padrao.md)
(exclusão permanente de `dotnet8`), `.github/workflows/workflow.yml`
(`pr_execution_scope`, `validate-pr` vs `validate-pr-full`),
`scripts/pipeline/governance/pr_execution_scope.py` (lógica exata de
profile P0_04/FULL por path alterado), `.github/workflows/validate-base-images.yml`
e `build-base-images.yml` (onde o contrato funcional roda e por que não
roda em PR), `policies/operations/health.json` (`exceptions.dotnet8`).

Achado central da pesquisa: não existe hoje nenhum entrypoint de CI que
valide as 17 definições de uma vez sem publicar. `validate-pr-full` cobre
16 (todas exceto `dotnet8`, hardcoded); `dotnet8` está fora de todos os
lotes por desenho (ADR-0001) e esta rodada foi instruída a não alterar essa
exclusão. `validate-base-images.yml` só aceita `workflow_call` — não pode
ser disparado diretamente.

## Estratégia

1. Confirmar baseline (`main == origin/main`, working tree limpo) sem
   reconciliar a branch local `main` divergente (fora de escopo).
2. Acionar `validate-pr-full` via um PR real e descartável, usando o mesmo
   padrão já estabelecido neste repositório para disparar CI sem mudar
   comportamento (`test/m12-doc-only`: "comment-only change to a protected
   path"). Escolhido: uma linha de comentário em `Makefile` (caminho no
   filtro de `workflow.yml`, não classificado como `P0_ONLY`/`docs`/`specs`
   por `pr_execution_scope.py`).
3. Monitorar o run real (`gh run watch`), baixar os artifacts
   `build-scans-<framework>-1` de todas as 16 legs e parsear
   `trivy-{amd64,arm64}.json` estruturalmente (não `grep`).
4. Para `dotnet8`: consultar `APKINDEX`/`security.json` do Wolfi ao vivo
   (mesma fonte que o `apko` consultaria) em vez de reintroduzi-lo em
   qualquer lote de CI.
5. Fechar o PR de trigger sem merge; remover a branch descartável.
6. Registrar a matriz e atualizar ADR-0006 num PR separado e real
   (`docs/full-catalog-revalidation-20260917`), sem misturar o
   commit-de-trigger com o commit-de-evidência.

## Decisões e hipóteses

- **Por que um PR descartável em vez de rootfs sintético como resultado
  final:** o pedido explicitamente exige o mecanismo real (apko/melange +
  Trivy da fábrica), não uma aproximação local — rootfs sintético já havia
  sido usado como evidência auxiliar antes desta rodada e não substitui um
  build real.
- **Por que Makefile e não um framework YAML para o trigger:** qualquer
  toque em `frameworks/**` seria lido como alteração de produto sob medição
  (mesmo comment-only); `Makefile` é comportamentalmente inerte para os
  targets existentes (comentário `#`) e já está no filtro de path do
  workflow.
- **Por que não alterar `validate-pr-full` para incluir `dotnet8`:** isso
  exigiria remover a exclusão do ADR-0001 ou duplicar a lista de
  frameworks num arquivo diferente — ambos são "alterar execution_scope"
  ou "alterar default batch", explicitamente fora do permitido. A
  alternativa (inspeção de registro ao vivo) usa a mesma fonte de dados
  que o `apko` consultaria, sem essa alteração.
- **Como validar:** comparar os resultados do run real com a investigação
  anterior (ADR-0006, `specs/2026-09-16-v1-reference-go126/evidence.md`) —
  mesmas versões de pacote resolvidas (`openjdk-21-jre`, `libpng`,
  `freetype` idênticos), mesma diferença de closure Go 1.25 vs Go 1.26,
  como controle de consistência do método.

## Risco e rollback

PR de trigger nunca mergeado; branch removida após coleta de evidência.
Nenhuma mudança de produto (framework YAML, gate, severidade, execution
scope, default batch, ECR) foi feita ou é revertível porque nenhuma foi
feita. Documentação (ADR-0006, índice de ADRs, nota no evidence.md antigo,
esta spec) é aditiva e reversível por `git revert` como qualquer outro PR
de docs.

## Validação

- Run real: `35179012804` (PR #81), todos os 16 jobs `Validate <framework>`
  e `image-trust-gate` = `success`.
- `make test-unit` e `python3 -B tools/check_ai_context.py` (via
  `test_ai_context.py`) após as mudanças de documentação.
- `git diff --check` sem espaço em branco inválido.
