# PLAN — P0-04: First Corporate E2E

## Execution scope do rollout

Durante este primeiro E2E, o workflow raiz passa explicitamente apenas
`["go1-26", "go1-26-dev"]` ao caminho de validação e build/publicação. O
catálogo de `frameworks/` permanece intacto (`CATALOG_SCOPE = unchanged`);
trata-se de redução somente na execução. O contrato funcional planejado é
`go1-26` nas duas arquiteturas, usando `go1-26-dev` como companion de
build-stage, sem contrato separado para `-dev`.

O schedule diário de build usa o mesmo par. O schedule horário de promoção,
assim como recovery e health/monitoring, permanece fora do P0-04 e não é
alterado nesta preparação; `stable` permanece fora de escopo. A expansão
futura requer decisão explícita e revisão, seguindo fases de candidato único
até o catálogo completo.

O rastreio zlib/CVE dos demais frameworks continua paralelo: uma falha não
relacionada não bloqueia o Go 1.26 deste rollout, sem desabilitar ou mascarar
o scan global.

### Perfil de PR por impacto

O job `pr_execution_scope` resolve os paths alterados de forma determinística
e fail-safe. Mudanças exclusivamente em `frameworks/go1-26.yaml`,
`frameworks/go1-26-dev.yaml`, `tests/runtime/projects/go/**`, `docs/**` ou
`specs/**` usam `P0_04`; qualquer path de workflow, reusable workflow,
`scripts/pipeline/`, `distroless/`, `melange/`, `policies/`, outro framework,
ou path desconhecido usa `FULL`. Assim, alteração compartilhada nunca cai
silenciosamente no lote Go-only.

O PR P0-04 normal executa os dois frameworks; PR de impacto compartilhado
executa o catálogo FULL. O job de promoção do rollout também recebe
explicitamente `["go1-26", "go1-26-dev"]`; `promote-stable.yml` continua
reutilizável com qualquer matrix validada por caller FULL.

`TRUST_AUXILIARY_OPTIMIZATION = DEFERRED`: os cinco jobs representativos de
trust permanecem inalterados. O risco de builds Go concorrentes sem um grupo
dedicado foi observado e fica diferido nesta rodada.

## Pesquisa

Fontes consultadas para este plano (nenhum valor corporativo foi inventado;
onde a fonte não define, o item está marcado `EXTERNAL_DECISION`):

- [docs/corporate-adoption.md](../../docs/corporate-adoption.md) — pacote
  P0-03, PAR-01–20, CA-01–18, Estágios A–G.
- [docs/iam-permission-contract.md](../../docs/iam-permission-contract.md) e
  [policies/aws/proposals/factory-permissions/](../../policies/aws/proposals/factory-permissions/)
  — proposta P1-04, templates execution/provisioning/trust.
- [docs/adr/0002-sigstore-trust-model.md](../../docs/adr/0002-sigstore-trust-model.md)
  (P1-05) — estado do Sigstore público, decisão Option A/B pendente.
- [docs/adr/0003-controles-seguranca-workflows-federados.md](../../docs/adr/0003-controles-seguranca-workflows-federados.md)
  (P1-06) — premissa de autoria/sustentação, perguntas corporativas abertas.
- [docs/consumer-verification-contract.md](../../docs/consumer-verification-contract.md)
  — comandos de verificação (Cosign, `gh attestation verify`, SBOM) que o
  E2E deve reproduzir contra o registry corporativo.
- [docs/m11-m04-operational-health.md](../../docs/m11-m04-operational-health.md)
  (P1-08) — retenção, canal/observabilidade, limites declarados.
- [docs/wolfi-signing-key.md](../../docs/wolfi-signing-key.md) (P1-03) —
  seção "Corporate handoff — P0-03" (mirror/egress Wolfi).
- [specs/2026-09-13-partial-retry-without-rebuild/](../2026-09-13-partial-retry-without-rebuild/)
  — precedente técnico completo (retry/reuse, publicação por digest,
  Cosign/SBOM/provenance, todos comprovados em sandbox real).
- [specs/2026-09-13-corporate-adoption/](../2026-09-13-corporate-adoption/)
  — spec/acceptance/evidence do próprio pacote P0-03.

RFC-013 foi consultada como knowledge base, não como backlog automático:
seu conteúdo confirma `go1-26` como candidato já cogitado e confirma o
estado "Prontidão para produção: Não", mas não foi usada para derivar
nenhum requisito novo sem checagem cruzada contra a fonte primária.

## Capability Matrix

| Ação | Classificação | Nota |
| --- | --- | --- |
| Escrever/manter/operar os workflows do produto | **SANDBOX-EXECUTE / LOCAL-EXECUTE** | Autorização já concedida pela premissa do ADR-0003 |
| Criar/editar specs (`spec.md`/`plan.md`/`tasks.md`/`acceptance.md`) | **LOCAL-EXECUTE** | Esta entrega |
| Propor templates IAM (execution/provisioning/trust) | **LOCAL-EXECUTE** | Já existe em `factory-permissions/`, reaproveitado |
| Aplicar IAM corporativo (criar role/policy real) | **EXTERNAL-DECISION** → depois **CORPORATE-PROPOSE** | Cloud/IAM decide e provisiona |
| Configurar PKI/CA corporativa real | **EXTERNAL-DECISION** | PKI/Segurança |
| Configurar rede/egress/mirror corporativo | **EXTERNAL-DECISION** | Network/Segurança |
| Criar/configurar ECR corporativo | **EXTERNAL-DECISION** → **EXTERNAL-PROVISIONING** | Cloud/IAM |
| Aprovar/rejeitar scanner adicional (Veracode/SCA) | **EXTERNAL-DECISION** | AppSec/Segurança |
| Decidir aceite Sigstore público (Option A/B) | **EXTERNAL-DECISION** | Segurança/AppSec |
| Executar dry-run local dos scripts contra fixtures | **LOCAL-EXECUTE** | Stage 3 |
| Executar leitura read-only em recursos corporativos já provisionados | **CORPORATE-PROPOSE** (proposta de checklist) → execução real é **EXTERNAL-DECISION** até autorização explícita | Stage 2 |
| Executar a publicação corporativa real (Stage 4) | **EXTERNAL-DECISION** até autorização explícita e nomeada | Nunca automática |
| Promover `stable` corporativa | **FORBIDDEN** nesta spec | Ver Stage 6 |
| Bypass de gate de segurança/scan para viabilizar o E2E | **FORBIDDEN** | Sem exceção |
| Reaproveitar a infraestrutura sandbox do P1-02 para qualquer teste não relacionado a este E2E | **EXTERNAL-DECISION** (novo motivo explícito exigido) | Conforme decisão de encerramento do P1-02 |

**Distinção preservada**: a autorização de workflows federados (ADR-0003)
significa que Containers Products pode escrever, manter e operar os
workflows. Isso **não** significa acesso automático a IAM corporativo, ECR
corporativo, PKI, rede, AppSec, nem autorização para promover `stable` ou
para qualquer bypass de segurança.

## Estratégia — Estágios de execução

Cada estágio registra inputs, ações permitidas/proibidas, owner, critérios
de entrada/saída, condição de parada e evidência produzida. Nenhum estágio
além do 0 está autorizado a iniciar nesta entrega.

### Stage 0 — Evidence freeze / planning

- **Inputs**: reconciliação do roadmap (P1-02 CLOSED, P0-04 READY TO PLAN).
- **Allowed actions**: criar/revisar os 6 arquivos deste spec; rodar testes
  locais e lints sobre a documentação nova.
- **Forbidden actions**: qualquer AWS, workflow, IAM, ECR, GitHub vars.
- **Owner**: Containers Products.
- **Entry criteria**: P1-02 CLOSED (comprovado).
- **Exit criteria**: spec/plan/tasks/acceptance/evidence/handoff criados e
  revisados; `make test-unit`/lints/`check_ai_context`/`git diff --check`
  OK.
- **Stop conditions**: nenhuma — este estágio é documental.
- **Evidence produced**: os 6 arquivos desta pasta.

### Stage 1 — Corporate prerequisites

- **Inputs**: decisões e recursos nomeados por owner (ver
  [Dependency Matrix](#dependency-matrix)).
- **Allowed actions**: solicitar decisões por escrito; registrar
  respostas com owner/data/referência. Nenhuma aplicação de recurso.
- **Forbidden actions**: qualquer AWS real, criação de IAM/ECR, alteração
  de rede/PKI.
- **Owner**: cada owner nomeado (Cloud/IAM, PKI/Segurança, Network/Segurança,
  AppSec/Segurança, Admin GitHub) — Containers Products coordena.
- **Entry criteria**: Stage 0 concluído.
- **Exit criteria**: conta/região AWS, role/trust IAM, ECR, CA corporativa
  e decisão Sigstore (Option A/B) resolvidos e documentados com owner.
- **Stop conditions**: decisão obrigatória ausente ou rejeitada — não
  inventar alternativa; não prosseguir para Stage 2 com pendência
  bloqueante.
- **Evidence produced**: decisões registradas (fora deste repositório
  quando restritas), com referência sanitizada em `evidence.md`.

### Stage 2 — Read-only preflight

- **Inputs**: recursos provisionados por Cloud/IAM conforme Stage 1.
- **Allowed actions**: leitura (`aws iam get-role`, `aws ecr
  describe-repositories`, `aws ecr describe-images`, verificação de
  proteções de repositório GitHub) — somente consulta.
- **Publisher contract**: `DescribeRepositories` produz JSON validado
  localmente antes do login/publicação. Nome, ARN/account, URI/região,
  `IMMUTABLE` sem exclusions, `scanOnPush=true` e `AES256` precisam coincidir.
- **Forbidden actions**: qualquer escrita, criação ou alteração de
  configuração; em especial `CreateRepository`, `PutImageTagMutability`,
  `PutImageScanningConfiguration`, lifecycle, policy ou tags de recurso.
- **Owner**: Containers Products, com suporte de Cloud/IAM.
- **Entry criteria**: recursos existem e credenciais de leitura
  disponíveis.
- **Exit criteria**: configuração observada corresponde exatamente ao
  aprovado em Stage 1 (trust, permissões, mutabilidade, encryption).
- **Stop conditions**: qualquer divergência entre o observado e o
  aprovado — devolver a Cloud/IAM, não prosseguir e não reparar
  automaticamente.
- **Evidence produced**: snapshot sanitizado da configuração observada.

### Stage 3 — Dry-run/build only

- **Inputs**: ambiente validado (Stage 2), sem credenciais AWS.
- **Allowed actions**: `make test-unit test-integration lint-local
  lint-shared lint-workflows`, `python3 -B tools/check_ai_context.py`,
  `git diff --check`; build local do candidato (`go1-26`/`go1-26-dev`) e
  contrato funcional, sem publicação.
- **Forbidden actions**: qualquer `configure-aws-credentials`, push de
  imagem, assinatura real contra identidade corporativa.
- **Owner**: Containers Products.
- **Entry criteria**: Stage 2 sem divergência.
- **Exit criteria**: build, scan (CR5) e contrato funcional (CR6) PASS
  localmente/no runner autorizado, sem publicação.
- **Stop conditions**: falha de pin/PKI/scan/contrato — diagnosticar e
  corrigir a causa, sem relaxar gates.
- **Evidence produced**: logs completos, versões de ferramentas, planos de
  contrato, scans por arquitetura.

### Stage 4 — Corporate isolated publication

- **Inputs**: Stages 1–3 satisfeitos; autorização explícita e nomeada para
  esta execução específica (lote, destino, janela).
- **Allowed actions**: **uma** execução controlada do workflow federado
  contra o destino corporativo isolado e aprovado; publicação por digest
  (CR8); assinatura/SBOM/provenance (CR10–CR12).
- **Forbidden actions**: segundo dispatch/rerun sem nova autorização;
  qualquer escrita em `stable`; qualquer recurso fora do catálogo
  aprovado.
- **Owner**: Containers Products executa; Cloud/AppSec dão suporte.
- **Entry criteria**: autorização explícita registrada, com escopo/destino/
  janela.
- **Exit criteria**: OCI aprovado → publicado por digest → assinatura/
  provenance/SPDX gerados, tudo contra o destino corporativo isolado.
- **Stop conditions**: qualquer gate falho ou evidência incompleta —
  preservar artifacts, não corrigir automaticamente, não repetir sem nova
  autorização.
- **Evidence produced**: gate/bind/publicação/verificação, mesmo padrão do
  P1-02 (`gate.json`, `layout-binding.json` ou equivalente, `publication-*.json`,
  `signature-verification-*.json`, `sbom-verification-*.json`,
  `provenance-verification-*.json`, `final-result.json`).

### Stage 5 — Verification

- **Inputs**: evidência produzida no Stage 4.
- **Allowed actions**: leitura/verificação independente (`aws ecr
  describe-images`, `cosign verify`, `cosign verify-attestation`,
  `gh attestation verify`).
- **Forbidden actions**: qualquer escrita, correção automática de achado.
- **Owner**: Containers Products + revisão independente.
- **Entry criteria**: Stage 4 concluído com evidência completa.
- **Exit criteria**: `read-back == validated`; assinatura/SBOM/provenance
  verificados de forma independente (não apenas confiando no output do
  próprio job).
- **Stop conditions**: qualquer mismatch — bloquear, não promover, não
  repetir automaticamente.
- **Evidence produced**: relatório de verificação independente.

### Stage 6 — Optional stable decision

- **Inputs**: Stage 5 PASS **e** decisão explícita e separada de promover.
- **Allowed actions**: nenhuma, a menos que uma autorização específica e
  distinta desta spec seja concedida.
- **Forbidden actions**: qualquer promoção de `stable` como consequência
  automática do Stage 5.
- **Owner**: Cloud/IAM + Containers Products.
- **Entry criteria**: autorização explícita e nomeada, fora do escopo
  padrão de P0-04.
- **Exit criteria**: N/A para esta entrega — `STABLE_PRODUCTION_PROMOTION
  = OUT_OF_SCOPE`.
- **Stop conditions**: ausência de autorização — o estágio simplesmente não
  ocorre.
- **Evidence produced**: nenhuma nesta entrega.

### Stage 7 — Final evidence/acceptance

- **Inputs**: todos os estágios anteriores executados conforme aplicável.
- **Allowed actions**: consolidar evidência; revisão independente; registrar
  decisão de liberação ou não liberação (equivalente ao Estágio G de
  P0-03).
- **Forbidden actions**: inferir aceite de ausência de resposta.
- **Owner**: aceitantes designados + Containers Products.
- **Entry criteria**: Stage 5 concluído (Stage 6 opcional).
- **Exit criteria**: termo de decisão com escopo, digests, aprovadores e
  pendências remanescentes.
- **Stop conditions**: requisito obrigatório sem decisão/teste, identidade
  ou PKI não verificada, IAM incompatível — não liberar.
- **Evidence produced**: `acceptance.md` atualizado com estado final por
  CE2E-xx.

## Dependency Matrix

| Dependency | Owner | Required? | Blocking? | Current state | Next action |
| --- | --- | --- | --- | --- | --- |
| Corporate AWS account/region | Cloud/IAM | Sim | **Sim** | Não nomeada | Solicitar via Stage 1 |
| Execution IAM role | Cloud/IAM | Sim | **Sim** | PROPOSED (template local, `factory-permissions/`) | Decisão Profile A + aplicação |
| OIDC trust | Cloud/IAM + Admin GitHub | Sim | **Sim** | PROPOSED, claims não confirmadas na conta real | Confirmar claims (`repository`/`repository_id`/`ref`/`job_workflow_ref`) |
| ECR repositories | Cloud/IAM | Sim | **Sim** | Não provisionados | Catálogo de ARNs aprovado (PAR-10) |
| Corporate CA | PKI/Segurança | Sim (CR3/CE2E-15) | **Sim** | Mecanismo pronto; perfil `public`/mock ativo | Fonte/manifesto real (PAR-12/13) |
| Network egress/mirror (Wolfi) | Network/Segurança | Condicional | Só se isolamento exigido | Acesso direto hoje | Decisão de mirror/proxy controlado |
| Sigstore (público) | AppSec/Segurança | Sim (CR10) | **Sim** | ADR-0002 PROPOSED | Decisão Option A/B |
| Scanner/AppSec adicional | AppSec/Segurança | Não, para o mínimo | Não | ADR-0003 sem resposta | Confirmar adequação de Trivy, se exigido |
| GitHub variables (role/region/repos) | Admin GitHub | Sim | **Sim** | Não criadas | Após decisão IAM/ECR |
| Repository protection | Admin GitHub/Segurança | Sim | Sim (CA-01) | Sandbox atual, `enforce_admins=false` | Confirmar regras centrais corporativas |
| Observability/evidence destination | Operação + Containers Products | Não, para o mínimo | Não | `external_destination = null` (P1-08) | Tratado em fatia própria |

## Parallel Track — zlib/CVE

Estado observado (`specs/2026-09-13-wolfi-signing-key/evidence.md`):
CVE-2026-85091 em zlib bloqueia o scan de `nodejs22` (e potencialmente
outros frameworks que compartilham a dependência). `go1-26`/`go1-26-dev`
**não** constam nessa lista de bloqueio.

```
DOES NOT BLOCK P0-04 go1-26
```

Continua sendo um blocker real para os frameworks afetados. Nenhum bypass,
nenhuma exceção e nenhuma mudança de severity são propostos aqui ou em
qualquer outra parte deste spec — este item é rastreado como investigação
paralela, fora do escopo de aceite do candidato `go1-26`. Fundamento textual
(`docs/corporate-adoption.md`, seção 7): "Bloqueio upstream de CVE pode
coexistir com funcionamento correto do gate; não autoriza liberar o
framework bloqueado nem contar exclusão formal como saúde."

## Decisões e hipóteses

- **Hipótese de candidato único**: `go1-26` é o único candidato deste E2E.
  Validar: nenhuma evidência nova de bloqueio específico a `go1-26` surgir
  antes do Stage 3.
- **Hipótese de Profile A**: recursos ECR pré-provisionados por Cloud/IAM +
  role de execução somente leitura/escrita de imagem é a recomendação.
  Validar: decisão explícita de Cloud/IAM no Stage 1; se rejeitada, revisar
  o modelo `provisioning` do P1-04 antes de Stage 4.
- **Hipótese de stable fora de escopo**: minimiza blast radius e evita
  depender de uma restrição IAM que não existe (retag por `PutImage`).
  Validar: nenhuma mudança até decisão explícita e separada (Stage 6).

## Risco e rollback

- Nenhuma execução real ocorre nesta entrega; não há estado a reverter.
- Quando Stage 4 for autorizado: preservar toda a evidência antes de
  qualquer ação corretiva; não repetir a publicação sem nova autorização
  explícita; não usar a role/recursos do laboratório P1-02 para o E2E
  corporativo (contextos AWS distintos, propositalmente).
- Se qualquer gate técnico (scan, contrato, digest) falhar durante o Stage
  3/4, a causa deve ser diagnosticada e corrigida em revisão própria — não
  relaxar severity, não criar exceção, não bypassar.

## Validação

Comandos locais desta entrega (documentação apenas):

```bash
make test-unit test-integration lint-local lint-shared lint-workflows
python3 -B tools/check_ai_context.py
git diff --check
```

Critérios relacionados: [acceptance.md](acceptance.md) (CE2E-01–15, todos
`NOT RUN` até execução real).
