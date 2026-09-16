# Manifesto de migração corporativa

Classificação completa dos três repositórios da fábrica
(`alric-containers-image-base`, `alric-containers-registry`,
`alric-containers-reusable-workflows`) para facilitar a futura migração
ao repositório/organização corporativos. Produzido por inventário real
(`git ls-files`, grep de referências cruzadas, leitura de testes), não por
suposição — cada classificação abaixo tem a evidência que a sustenta.

Este documento **não migra nada**. É o mapa para quando a migração
acontecer. Ver também `docs/repository-architecture.md` (fronteiras
arquiteturais já documentadas) e `docs/adr/README.md` (decisões).

## Como ler

- **KEEP**: fica no repositório atual, sem mudança.
- **DO_NOT_MIGRATE**: existe e é válido no sandbox, mas não deve seguir
  para o repositório corporativo como está (specific do ambiente pessoal,
  ou lab-only por design).
- **MOVE_TO_SHARED**: candidato a virar capacidade reutilizável entre
  repositórios/produtos — nenhum aqui atingiu o critério de "pelo menos
  dois consumidores reais com o mesmo contrato" ainda (ver seção
  "Reusable workflows" abaixo).
- **ARCHIVE**: histórico com valor de auditoria, mantido, mas não é mais
  o estado ativo do produto.
- **GENERATED**: nunca deveria estar em controle de versão; verificado
  aqui item a item.

## `alric-containers-image-base`

### KEEP — domínio do produto (nunca migra "genérico", migra como está)

| Caminho | Motivo |
| --- | --- |
| `frameworks/`, `distroless/` | Catálogo declarativo — a razão de existir do produto |
| `melange/image-base-ca-certificates.yaml`, `melange/keys/`, `melange/certificates/manifest.json` | Fonte do pacote de CAs e chave pinada — não são output, são configuração revisada |
| `scripts/pipeline/catalog/` | Seleção de lote, exclusões (ADR-0001), `execution_scope` (ADR-0004) |
| `scripts/pipeline/release/` (todo o diretório) | `find_promotion_candidate.py`, `validate_ecr_repository.py`, `verify_promotion_pair(s).py`, `verify_promotion.py`, `report_unfixed_cves.py` — cada um codifica uma regra de negócio da fábrica (soak, preflight fail-closed, binding runtime/dev, identidade assinada, política de CVE informacional). Nenhum é mecânica genérica pura |
| `scripts/pipeline/artifacts/` | Formato OCI, digest, scan — mecanicamente genérico em espírito, mas são **módulos Python do produto**, checados out pelo reusable workflow a partir deste repositório a cada run (ver "Reusable workflows" abaixo); não há hoje um mecanismo de distribuição cross-repo para módulos Python que justifique extraí-los |
| `scripts/pipeline/governance/` | Lint das próprias pins/workflows deste repositório — inerentemente specific |
| `scripts/pipeline/operations/` | `operational_health.py` (com `execution_scope`), `pipeline_summary.py`, `tool_versions.py` — semântica de saúde do catálogo |
| `tests/` (todo o diretório) | Espelha `scripts/pipeline/`; migra junto |
| `policies/` (todo o diretório, exceto notado abaixo) | Configuração revisada que os scripts acima aplicam |
| `docs/consumer-verification-contract.md`, `docs/image-composition.md`, `docs/repository-architecture.md` | Guia de consumo e arquitetura ativos |
| `docs/adr/` (todo o diretório) | Decisões pontuais, cada uma com estado e critério de revisão explícitos |
| `RFC-013-Image-Base-Completa-com-Mermaid.md` | Documento-fonte da proposta e do estado do produto |
| `scripts/verify-image.sh` | Verificação externa de consumidor, sem contexto de CI — utilitário do produto |

### CORPORATE_MIGRATION_REFERENCE — propostas para revisão, não configuração ativa

| Caminho | Estado |
| --- | --- |
| `policies/aws/corporate-like/` | Testado (`test_corporate_like_iam_target.py`), documentado, não aplicado — é literalmente a proposta a levar para Cloud/IAM corporativo |
| `policies/aws/proposals/factory-permissions/` | Testado (`test_iam_proposal.py`); mesmo propósito |
| `docs/iam-permission-contract.md`, `docs/corporate-adoption.md` | Pacotes de adoção corporativa — o objetivo deles é justamente virar o roteiro de migração |
| `specs/2026-09-15-first-corporate-e2e/` | Planejamento do primeiro E2E corporativo (Stage 1 ainda bloqueado por decisões externas) |

### DO_NOT_MIGRATE — removidos na limpeza corporativa de 16/09/2026

O harness de laboratório do P1-02 e suas permissões IAM de lab foram
**removidos do repositório** (`.github/workflows/partial-retry-lab.yml`,
`scripts/pipeline/runtime/retry_lab.py`, `retry_lab_publish.py`, seus testes
e `policies/aws/proposals/p102-lab-permissions/`). O comportamento útil do
P1-02 permanece no produto, em `scripts/pipeline/runtime/contract_evidence.py`
e `runtime_images.py` — o lab importava do produto, nunca o contrário.
O histórico Git preserva o conteúdo removido.

`AI-WORKSPACE.md` (no diretório pai, fora deste repositório) continua fora de
qualquer um dos três repositórios git; não migra por definição.

### Documentação histórica — removida na mesma rodada

Os documentos de milestone (`m09-m16-review.md`, `m12-gate-inventory.md`,
`m09-m16-cache-policy.md`, `old-checklist-closure.md`,
`release-readiness-2026-09-10.md`, `repository-rename.md`,
`rfc-013-historico-de-entregas.md`), o spec `2026-09-11-ai-workflow/` e as
evidências sem citação ativa foram removidos: o estado final está consolidado
na RFC-013, nos ADRs e na documentação ativa, e o histórico Git preserva o
detalhe. As citações que apontavam para eles foram reescritas como prosa
autossuficiente nos documentos ativos.

**Os specs e evidências que permanecem são os ativamente citados** por
`RFC-013...md`, algum ADR, `docs/corporate-adoption.md`, ou
`tests/unit/pipeline/governance/test_consumer_documentation.py`
(`SPEC`/`TRUST_SPEC`/`FEDERATED_SPEC`/`OPERATIONS_SPEC`/`ADOPTION_SPEC`/
`ORIGIN_SPEC`) — não são clutter, são a trilha de evidência que a própria
RFC cita para sustentar suas afirmações.

### AI development files — TEAM_DEVELOPMENT_TOOLING (não PERSONAL_ONLY)

`AGENTS.md`, `CLAUDE.md`, `docs/ai/`, `prompts/`, `.github/copilot-instructions.md`:
referenciados pelo `RFC-013...md`, `README.md`, `CONTRIBUTING.md`, testados
por `tests/unit/pipeline/governance/test_ai_context.py`. **Recomendação:
manter nas posições atuais (raiz do repositório), não consolidar em
`.ai/`.** `AGENTS.md`/`CLAUDE.md` na raiz é convenção reconhecida por
ferramentas (Codex, Claude Code, Copilot fazem descoberta automática
nesse caminho); mover quebraria essa descoberta automática para ganho
zero — seria abstração por estética, exatamente o que esta rodada
proíbe. Migra para o corporate como está, se a organização corporativa
usar o mesmo conjunto de ferramentas (decisão externa, não técnica).

### GENERATED — verificado, já correto

| Padrão | Estado real |
| --- | --- |
| `sbom-*.spdx.json` (raiz) | **Não rastreado.** `.gitignore` já contém `sbom-*.json` e `*.spdx.json`. Arquivos physicamente presentes no disco são resíduo local de um build de 08/09, sem relação com o repositório Git |
| `melange/packages/**/APKINDEX.tar.gz`, `*.apk` | **Não rastreado.** `.gitignore` já contém `melange/packages/` |
| `melange/.local-keys/` | **Não rastreado.** Já ignorado |
| `.reusable-workflows/` (checkout local para contrato offline) | **Não rastreado.** Já ignorado |

Nenhuma ação necessária nesta categoria — a higiene já existia.

## `alric-containers-registry`

### KEEP — infraestrutura real

Todo o repositório: `main.tf`/`locals.tf`/`outputs.tf`/`variables.tf`/
`providers.tf`/`versions.tf`, `bootstrap/iam/` (quebra de circularidade
documentada), `drift-remediation/` (mecanismo genérico e reusado — ver
"episódio 1" e "episódio 2" no próprio `README.md`), `iam/`, `policies/`,
`tests/`. Nada aqui é lab pessoal disfarçado — é infraestrutura real com
estado real em AWS, ainda que numa conta pessoal.

### GENERATED — verificado, já correto

| Padrão | Estado real |
| --- | --- |
| `tfplan`, `bootstrap/iam/bootstrap.tfplan` | **Não rastreado.** `.gitignore` já contém `*.tfplan`, `tfplan`, `tfplan.bin` |
| `bootstrap/iam/terraform.tfstate` | **Não rastreado.** `.gitignore` já contém `*.tfstate`, `*.tfstate.*` |
| `.terraform.lock.hcl` (raiz e `bootstrap/iam/`) | **Rastreado corretamente** — lockfile de provider deve ser versionado, e está |

Nenhuma ação necessária — a higiene já existia, inclusive mais completa
do que o pedido desta rodada exigia (`.gitignore` já cobre `*.tfstate.*`,
`crash.log`, `*.tfvars`, `*.tfbackend`, `override.tf`).

## `alric-containers-reusable-workflows`

### KEEP — capacidades técnicas genéricas já corretamente extraídas

| Caminho | Papel |
| --- | --- |
| `.github/workflows/validate-apko-images.yml` | Build once (melange+apko) + Trivy nas duas arquiteturas — já é exatamente o que as seções 11/12 do pedido descreveriam como `container-build.yml`/`container-security.yml`, combinados numa única chamada porque build e scan sempre acontecem juntos, sem consumidor real que precise dos dois separados |
| `.github/workflows/test-runtime-images.yml` | Execução do contrato funcional (mecânica de container real, runtime vs -dev) |
| `actions/setup-trivy/` | Composite action de setup, já reusada por `promote-stable.yml` e `recover-stable.yml` no image-base — padrão correto, preservado |
| `.github/workflows/update-v1-tag.yml` | Canal de consumo `@v1` opcional (mecanismo de proteção interno: só avança por fast-forward, nunca recua) — real, testado (`tests/test_contracts.py`), documentado no `README.md`. O consumidor real (image-base) optou por pin de SHA em vez de `@v1` por política própria mais estrita — isso não torna o canal `@v1` morto, é uma opção legítima para futuros consumidores |
| `policies/main-protection.json`, `scripts/check_contracts.py`, `tests/` | Governança do próprio repositório reusable |

### Reusable workflows — avaliação das seções 11–14 (build/security/publish/attest)

**Nenhum novo reusable workflow foi criado nesta rodada.** Avaliação, não
implementação, conforme pedido ("avaliar criação de"):

| Candidato | Veredito | Motivo |
| --- | --- | --- |
| `container-build.yml` | **Já existe**, como parte de `validate-apko-images.yml` | Build once já é uma capacidade genérica funcionando, testada em produção real (V1 Go fechado) |
| `container-security.yml` | **Já existe**, como parte de `validate-apko-images.yml` | Scan sempre acontece imediatamente após o build, no mesmo job/filesystem; separar em duas chamadas reusable exigiria upload/download de artifact entre elas só para reconstituir o que hoje é sequencial e local — complexidade adicionada sem consumidor que precise de build sem scan |
| `container-publish.yml` | **Não extraído — PREMATURE_EXTRACTION** | Publicação (`skopeo copy --preserve-digests`, read-back, Cosign, SBOM, provenance) é hoje código único, um consumidor único (`build-base-images.yml`), sem duplicação para eliminar. Está entrelaçada com decisões de domínio que a seção 9 do pedido explicitly proíbe mover (binding de candidato do P1-02, preflight `PREPROVISIONED_ONLY`) |
| `container-attest.yml` | **Não extraído — PREMATURE_EXTRACTION** | Mesmo motivo — Cosign/SBOM/provenance hoje são ~30 linhas dentro do job de publicação, um único consumidor |

**Critério objetivo usado** (mesmo da seção 16 do pedido, generalizado):
extrair um reusable workflow novo exige pelo menos dois consumidores
reais com o mesmo contrato. Hoje há exatamente um produto
(`image-base`) consumindo qualquer uma dessas capacidades. Forçar a
extração agora seria "criar abstração apenas por estética" — exatamente
o que esta rodada proíbe. **Gatilho para reconsiderar**: quando um
segundo framework/produto real precisar publicar/atestar imagens pelo
mesmo contrato.

### Terraform reusable (seção 16)

Não avaliado como candidato — `containers-registry` é o único consumidor
de Terraform hoje. `KEEP LOCAL`, conforme o próprio critério do pedido.

### Versionamento (seção 18) — já correto, nenhuma mudança necessária

```
image-base pins reais hoje:
  validate-apko-images.yml@7a9b055a462eeb8552d3404c26538b44e8ccd83f
  test-runtime-images.yml@7a9b055a462eeb8552d3404c26538b44e8ccd83f
  actions/setup-trivy@eea2d2f4c4102ded74204e4131c1417f444ae3fc
```

Nenhum `@main` em uso. `policies/governance/reusable-workflows.json` +
`scripts/pipeline/governance/workflow_dependencies.py` (image-base) já
fazem lint obrigatório disso: SHA completo, literal, consistente entre
chamadas e checkouts locais de contrato.

**Achado, não aplicado**: a tag `v1` não tem uma *ruleset*/tag-protection
real no GitHub — a proteção existe só na lógica do próprio
`update-v1-tag.yml` (fast-forward-only). Tentei adicionar uma ruleset de
proteção (`deletion` + `non_fast_forward`) e revertive imediatamente: o
próprio `update-v1-tag.yml` move a tag via
`PATCH .../git/refs/tags/v1` com `force=true`, e não tenho como
confirmar com segurança, dentro desta sessão, se a ruleset trataria essa
chamada como "force push" (bloqueando a automação existente) ou
respeitaria a ancestralidade real (permitindo, já que o script só avança
quando `compare` confirma `ahead`). **Recomendo testar isso separado,
fora desta rodada** — não presumido seguro, não aplicado.

## Resumo por repositório

| Repositório | Papel | Estado da higiene |
| --- | --- | --- |
| `alric-containers-image-base` | PRODUCT / DOMAIN | Já limpo; 2 arquivos históricos de baixo valor identificados (não removidos) |
| `alric-containers-registry` | INFRASTRUCTURE | Já limpo; `.gitignore` mais completo que o exigido |
| `alric-containers-reusable-workflows` | SHARED EXECUTION CAPABILITIES | Já correto; nenhuma nova extração se qualifica ainda pelo critério de 2+ consumidores |
