# HANDOFF — P0-04: First Corporate E2E

- Repositório, branch e commit base: `alric-corp/alric-containers-image-base`,
  `main`, `1833dfef608fe7ad9bb9703d5a7637f33d2f5aee` (após merge do PR #69,
  encerramento documental do P1-02).
- Objetivo e pasta da spec: `specs/2026-09-15-first-corporate-e2e/` —
  planejamento do primeiro E2E corporativo, sem execução.
- Estado do diff: 6 arquivos novos nesta pasta (`spec.md`, `plan.md`,
  `tasks.md`, `acceptance.md`, `evidence.md`, `handoff.md`). Nenhum outro
  arquivo do repositório foi alterado.
- Tasks concluídas: Stage 0 — criação dos 6 arquivos (ver `tasks.md`).
- Verificações e resultados: `make test-unit`/`test-integration`/lints/
  `check_ai_context`/`git diff --check` executados sobre o repositório com
  esta pasta nova (ver relatório da sessão).
- Decisões e hipóteses pendentes: candidato único `go1-26`, Profile A para
  IAM, `stable` fora de escopo — todas registradas em `plan.md` como
  hipóteses a validar, não decisões corporativas tomadas.
- Dependências/autorizações ainda necessárias: ver "What is blocked" e
  "External owners" abaixo.
- Próximo passo: revisão independente deste spec, seguida de
  encaminhamento formal das decisões de Stage 1 aos owners nomeados.

```text
P0-04 = PLANNED
EXECUTION = BLOCKED ON CORPORATE PREREQUISITES
Candidate = go1-26 (com go1-26-dev)
Stable = OUT OF SCOPE
```

## What is ready

- Objetivo, non-goals, candidato e justificativa (spec.md).
- 15 requisitos (CR1–CR15) com owner, evidência esperada, blocking e
  capability class (spec.md).
- Capability Matrix formal, preservando a distinção entre autoria de
  workflow federado e acesso corporativo (plan.md).
- 8 estágios de execução (0–7), cada um com inputs/ações permitidas e
  proibidas/owner/critérios de entrada-saída/condição de parada/evidência
  (plan.md).
- Dependency Matrix com 11 dependências, todas classificadas (plan.md).
- 15 critérios de aceite formais (CE2E-01–15), todos `NOT RUN`, com
  evidência exigida/owner/acceptor/blocking (acceptance.md).
- Estrutura de evidência vazia, pronta para preenchimento real, com o
  precedente técnico do P1-02 citado corretamente como precedente, não
  como prova corporativa (evidence.md).
- Checklist ordenado por estágio, com owners externos explícitos
  (tasks.md).

## What is blocked

Bloqueadores obrigatórios (impedem o Stage 4, execução real):

1. Conta/região/role AWS corporativos não nomeados.
2. Trust OIDC corporativa não confirmada (claims reais não observadas).
3. Repositório(s) ECR corporativo(s) não provisionados.
4. CA corporativa real não disponível (perfil `public`/mock ainda ativo).
5. Decisão Sigstore (ADR-0002 Option A/B) não tomada — bloqueia
   CE2E-09/10/11.
6. Regras centrais/proteções efetivas do(s) repositório(s) GitHub não
   confirmadas.

Bloqueadores condicionais (podem não bloquear, dependendo da decisão):

7. Network/mirror para Wolfi — só bloqueia se isolamento corporativo for
   exigido.
8. Scanner/AppSec adicional — não bloqueia o mínimo, a menos que
   formalmente exigido antes do Stage 4.

## External owners

| Área | Owner | O que falta |
| --- | --- | --- |
| AWS account/region/role/ECR | Cloud/IAM | Nomear conta, aplicar Profile A, provisionar ECR |
| OIDC trust | Cloud/IAM + Admin GitHub | Confirmar claims reais emitidas |
| CA corporativa | PKI/Segurança | Fonte/manifesto real, sem MOCK |
| Sigstore | Segurança/AppSec | Decisão Option A/B do ADR-0002 |
| Network/mirror Wolfi | Network/Segurança | Decisão de isolamento, se exigido |
| Scanner/AppSec adicional | AppSec/Segurança | Confirmar adequação de Trivy / exigência adicional |
| Repository protection | Admin GitHub/Segurança | Confirmar regras centrais aplicáveis |

## First action after approval

Após revisão independente deste spec: encaminhar formalmente as perguntas
do Stage 1 (ver `tasks.md`) aos owners da tabela acima, começando por
Cloud/IAM (conta/região/role/ECR) e PKI/Segurança (CA), por serem
bloqueadores obrigatórios sem via alternativa. Não iniciar Stage 2 antes
de todas as respostas obrigatórias do Stage 1.

## Stop conditions

- Qualquer decisão obrigatória ausente ou rejeitada no Stage 1: não
  inventar alternativa, não prosseguir.
- Qualquer divergência entre configuração observada (Stage 2) e o
  aprovado no Stage 1: devolver a Cloud/IAM.
- Qualquer falha de gate técnico (scan, contrato, digest) no Stage 3/4:
  preservar evidência, diagnosticar causa, não relaxar severity, não criar
  exceção, não repetir automaticamente.
- Qualquer tentativa de promover `stable` fora do Stage 6 explicitamente
  autorizado: parar e reportar, não corrigir automaticamente.

## Non-claims

Este planejamento **não** representa:

- Aceite corporativo de qualquer natureza.
- Conclusão do P1-04 (o contrato de permissões IAM mantém sua própria
  validação/aceite, independentes deste spec).
- Homologação AppSec ou aceite de scanner adicional.
- Decisão tomada sobre Sigstore (ADR-0002 continua `PROPOSED`).
- Resolução do bloqueio upstream de zlib/CVE em outros frameworks.
- Declaração de produção pronta ou de nível SLSA formal.
- Autorização para qualquer execução AWS, workflow, IAM ou ECR — nenhuma
  foi realizada nesta sessão.

## Follow-up documentation debt (não corrigido nesta sessão)

1. `specs/2026-09-13-stable-promotion-readback/evidence.md` e `handoff.md`
   ainda registram `HOSTED ACCEPTANCE = NOT RUN`, embora a RFC-013 e
   múltiplas outras specs confirmem, por referência cruzada, o hosted PASS
   real (run `34768459323`, commit `e3ed682`, `go1-26`/`go1-26-dev`). A
   spec dedicada de P1-01 nunca foi atualizada para refletir esse
   resultado.
2. `docs/corporate-adoption.md`, seção 6-B, ainda registra "P1-02: ... a
   continuação de publicação permanece pendente", embora o P1-02 esteja
   `CLOSED` com `PUBLICATION_CONTINUATION = PASS` (ver
   [specs/2026-09-13-partial-retry-without-rebuild/acceptance.md](../2026-09-13-partial-retry-without-rebuild/acceptance.md#hosted-acceptance-final--2026-09-15)).

Essas inconsistências **não bloqueiam** a criação ou o planejamento do
P0-04 — são registradas aqui para correção futura, em sessão própria, sem
escopo nesta entrega.

Confirme o estado real do Git antes de continuar.
