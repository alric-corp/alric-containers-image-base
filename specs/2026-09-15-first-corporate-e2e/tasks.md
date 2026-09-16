# TASKS — P0-04: First Corporate E2E

Checklist ordenado por estágio (ver [plan.md](plan.md) para inputs/critérios
completos de cada estágio). Tarefas marcadas com owner externo não podem ser
executadas por este produto.

## Stage 0 — Evidence freeze / planning

- [x] Reconciliar o roadmap e confirmar P1-02 = CLOSED antes de propor P0-04.
- [x] Criar `spec.md`/`plan.md`/`tasks.md`/`acceptance.md`/`evidence.md`/`handoff.md`.
- [ ] Revisão independente deste spec.
- [ ] Baseline freeze confirmado após a revisão (registrar SHA da main no
      momento da aprovação, distinto do SHA de criação).

## Stage 1 — Corporate prerequisites (external)

- [ ] Obter account/region AWS corporativos nomeados. — **Owner: Cloud/IAM**
- [ ] Obter IAM role/trust (Profile A recomendado; ver [plan.md](plan.md#estratégia--estágios-de-execução)). — **Owner: Cloud/IAM**
- [ ] Obter catálogo de ARNs ECR aprovado. — **Owner: Cloud/IAM**
- [ ] Obter fonte/manifesto da corporate CA real, sem MOCK. — **Owner: PKI/Segurança**
- [ ] Decisão Sigstore Option A/B (ADR-0002). — **Owner: Segurança/AppSec**
- [ ] Decisão de network/mirror para Wolfi, se isolamento for exigido. — **Owner: Network/Segurança**
- [ ] Confirmar adequação de Trivy / necessidade de scanner adicional (ADR-0003). — **Owner: AppSec/Segurança**
- [ ] Confirmar regras centrais/proteções do(s) repositório(s) GitHub. — **Owner: Admin GitHub/Segurança**

## Stage 2 — Read-only preflight

- [x] Remover criação/configuração automática de ECR do publisher.
- [x] Implementar validação pura e fail-closed do descriptor retornado por
      `DescribeRepositories`.
- [x] Cobrir o drift `IMMUTABLE_WITH_EXCLUSION` + wildcard `stable` como
      regressão negativa.
- [ ] Leitura read-only da role/trust IAM aprovada (confirmar contra o
      documentado em Stage 1).
- [ ] Leitura read-only da(s) configuração(ões) ECR (mutability, encryption,
      scanning).
- [ ] Verificar configuração da CA corporativa (manifesto/fonte, sem
      aplicar).
- [ ] Verificar GitHub vars/proteções de repositório observáveis.

## Stage 3 — Dry-run/build only

- [ ] Validação local/build do candidato (`go1-26`/`go1-26-dev`), sem
      credenciais AWS.
- [ ] Scan técnico (Trivy) sobre o candidato, ambas as arquiteturas.
- [ ] Contrato funcional (compilado, par `-dev`).
- [ ] Verificação multiarch (`linux/amd64`/`linux/arm64`) do OCI candidato.

## Stage 4 — Corporate isolated publication

- [ ] Autorização explícita e nomeada (escopo/destino/janela) registrada
      antes de qualquer execução.
- [ ] Uma execução controlada do workflow federado contra o destino
      corporativo isolado.
- [ ] Publicação por digest isolada (sem tocar recursos operacionais/`stable`).

## Stage 5 — Verification

- [ ] Read-back independente (`aws ecr describe-images`).
- [ ] Verificação de assinatura (`cosign verify`).
- [ ] Verificação de SBOM (`cosign verify-attestation --type spdxjson`).
- [ ] Verificação de provenance (`gh attestation verify`).
- [ ] Revisão de evidência completa.

## Stage 6 — Stable decision

Stable decision — **intentionally NOT REQUIRED for P0-04**. Este estágio só
é aberto mediante autorização explícita e separada, fora do escopo padrão
desta spec. Nenhuma tarefa está listada aqui propositalmente.

## Stage 7 — Final acceptance

- [ ] Revisão final de aceitação (todos os CE2E-xx aplicáveis).
- [ ] Decisão de release ou não-release registrada, com escopo, digests,
      aprovadores e pendências remanescentes.

## Dependências externas

| Item | Owner | Estado |
| --- | --- | --- |
| Conta/região/role AWS | Cloud/IAM | Pendente |
| ECR corporativo | Cloud/IAM | Pendente |
| CA corporativa | PKI/Segurança | Pendente |
| Decisão Sigstore | Segurança/AppSec | Pendente |
| Network/mirror Wolfi | Network/Segurança | Pendente (condicional) |
| Scanner/AppSec adicional | AppSec/Segurança | Pendente (não bloqueante para o mínimo) |
| Proteções de repositório | Admin GitHub/Segurança | Pendente |

Nenhuma tarefa dos Stages 1, 4, 6 ou das dependências externas acima pode
ser executada por este produto sem autorização/decisão do owner nomeado.
