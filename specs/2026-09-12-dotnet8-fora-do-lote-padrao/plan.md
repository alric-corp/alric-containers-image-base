# PLAN — 2026-09-12-dotnet8-fora-do-lote-padrao

## Pesquisa

Estado observado em 12/09/2026 (branch `main` = `517d2bf`, origin igual):

- A cadeia completa na `main` está comprovada: push `34555637518` e builds
  diários seguintes publicaram 14/15 frameworks; o único `failure` em cada run é
  `Validate dotnet8` → `Build & push dotnet8`. O run diário de 11/09
  (`34574793032`) concluiu `failure` só por isso.
- `packages.wolfi.dev/os` (APKINDEX x86_64 lido em 12/09/2026) ainda publica no
  máximo `dotnet-8-sdk 8.0.127-r0`; a correção `8.0.129-r1` não existe.
- `dotnet8` nunca publicou imagem nem teve `stable` (histórico da RFC-013,
  décima quinta/sexta entregas). O repositório ECR existe e está
  `IMMUTABLE_WITH_EXCLUSION`, aplicado por API sem imagem.
- O lote padrão está escrito três vezes em `.github/workflows/workflow.yml`
  (`validate-pr`, `build-base-images`, `promote-stable`), como string JSON,
  porque `with:` de workflow reutilizável não aceita cálculo por job sem um job
  intermediário. Não há lint que compare essas listas com o catálogo.
- `policies/operations/health.json` já tem `exceptions.dotnet8` com `reason`,
  `owner` e `review_by` (`2026-10-09`); `operational_health.evaluate` já
  classifica como `known` e alerta quando `review_by` vence (testes existentes).
- Lints offline do required check `lint-workflows`: `make lint-local`
  (hardening + pins) e `make lint-shared` (dependências + retenção/cron).
- PR #50 (`fix/image-composition`) altera as mesmas três linhas (acrescenta
  `java25-dev` e `go1-25-dev`) e mantém `dotnet8`. Conflito textual trivial na
  reconciliação; o lint novo garante o resultado final.
- Não existe convenção de ADR no repositório; o roadmap prevê ADRs (dotnet8,
  scanner, Sigstore público) e a RFC prevê "ADRs extraídos listados".

Fontes: `README.md`, `RFC-013-*.md`, `docs/m11-m04-operational-health.md`,
os documentos históricos daquela rodada,
`policies/`, `scripts/pipeline/{catalog,operations,governance}/`, testes
unitários, `gh run list`/`gh run view` (leitura), APKINDEX do Wolfi (leitura).

## Estratégia

Menor mudança que satisfaz a spec, uma única fonte de verdade para a exclusão:

1. **Política:** manter a lista em `policies/operations/health.json` →
   `exceptions` (já revisada por code owner, já consumida pela saúde). Nova
   semântica explícita no `$comment`: toda exceção está fora do lote padrão.
   Acrescentar `adr` à entrada `dotnet8`. Nenhum limite muda.
2. **Lint:** novo módulo `scripts/pipeline/catalog/default_batch.py`
   (domínio `catalog`, sem imports de outros domínios): lê catálogo, política e
   `workflow.yml`; `lint` compara os três lotes com `catálogo − exclusões` e
   valida os campos das exclusões; `list` imprime o lote efetivo em JSON.
   Entra em `make lint-local`, que o required check `lint-workflows` executa.
3. **Workflow:** remover `"dotnet8"` das três listas de `workflow.yml`.
4. **ADR:** `docs/adr/README.md` (índice, convenção mínima) e
   `docs/adr/0001-dotnet8-fora-do-lote-padrao.md`.
5. **Documentação consistente com a implementação:** README (tabela de imagens,
   pipeline, lints obrigatórios), `policies/README.md`, `docs/README.md`,
   `docs/m11-m04-operational-health.md`, `docs/repository-architecture.md`,
   `scripts/README.md`, `CONTRIBUTING.md`, Makefile `help`, e a linha de
   decisão de catálogo da RFC-013. Frases curtas, sem duplicar a política.
6. **Testes:** `tests/unit/pipeline/catalog/test_default_batch.py` com os
   positivos (árvore real) e negativos N01–N05 usando fixtures em diretório
   temporário; testes existentes de saúde cobrem N06.

## Decisões e hipóteses

- **Lista em `health.json`, não em arquivo novo.** Alternativa: criar
  `policies/release/catalog-exclusions.json` e fazer a saúde ler dois
  arquivos. Rejeitada: duplicaria motivo/dono/data ou exigiria mudar
  `operational_health.py` e seus testes para um ganho apenas nominal. A
  invariante "exceção de saúde ⇔ fora do lote" é a mais simples e
  verificável; um framework no lote que não publica **deve** alertar.
- **Lint em `catalog/`, não em `governance/`.** O lote padrão é uma regra de
  catálogo ("quais entradas o pipeline pede"); `catalog` não depende de
  outros domínios e lê só arquivos. Verificado pelo teste de arquitetura.
- **`workflow_dispatch` continua aceitando `dotnet8`.** É o mecanismo de
  reteste quando o Wolfi publicar a correção; o gate de CVE segue intacto.
- **`review_by` vencido não falha o lint.** Bloquearia todos os PRs por uma
  data; o mecanismo especificado é o alerta diário de saúde, já existente.
- **Validação da política acontece no lint, não só na saúde.** Exceção sem
  campos obrigatórios passa a falhar antes do merge (fail closed), em vez de
  só no job de saúde do dia seguinte.
- **Hipótese:** o job de `promote-stable` sem `dotnet8` não altera nada no ECR
  (nunca houve candidato). Sustentada pelo histórico; não há operação AWS.
- **Status do ADR:** "Proposto"; passa a "Aceito" com a aprovação de code
  owner do PR que o integra (owner CP + Owner RFC). O agente não simula essa
  autoridade.

## Risco e rollback

- Risco baixo: nenhuma credencial, gate, pin ou contrato compartilhado muda.
  O pior caso é o lint novo reprovar uma reconciliação futura (PR #50) — que
  é o efeito desejado, com mensagem citando job e framework.
- Rollback: reverter os arquivos desta spec (workflow, política, módulo,
  testes, docs). Sem estado remoto a desfazer.

## Validação

Ambiente: macOS arm64, Python 3.9.6, PyYAML 6.0.3, actionlint 1.7.12,
checkout `.reusable-workflows` em `0459275b…`. Comandos e critérios:

| Comando | Critérios |
| --- | --- |
| `python3 -B -m scripts.pipeline.catalog.default_batch lint` / `list` | A01, A02 |
| `make test-unit` | A04, A07, N01–N06 |
| `make lint-local` | A03, A07 |
| `make lint-shared` | A04 |
| `actionlint .github/workflows/workflow.yml` | A07 |
| `python3 -B tools/check_ai_context.py` | A05 (links) |
| `git diff --stat` / `git status --short` | A06, A08 |

Não executado nesta sessão (registrar como NOT RUN): build diário hospedado
após o merge e `pipeline-health` subsequente.

## Autoridade

- LOCAL-EXECUTE: código, política, ADR, docs, testes e lints locais.
- EXTERNAL-WRITE (não executado): commit/push/PR, revisão de code owner,
  merge.
- EXTERNAL-DECISION: aceite formal da decisão de catálogo (Containers
  Products + Owner RFC) — o ADR prepara o artefato; a aprovação é humana.
