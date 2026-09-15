# EVIDENCE — P0-04: First Corporate E2E

Estado: **NOT RUN**.

Nenhuma evidência corporativa existe ainda. As seções abaixo estão vazias
por estrutura, para preenchimento exclusivo durante os Stages 1–7 definidos
em [plan.md](plan.md). Nenhuma linha desta página comprova execução
corporativa até que uma coleta real seja registrada com run/artifact/commit
reais.

## Identidade

- Data e ambiente: N/A (nenhuma execução).
- Branch e commit base: N/A.
- Diff ou commits implementados: N/A (esta entrega é documental).
- Ferramenta/sessão: N/A.

## Prior technical evidence / precedent

A execução hospedada real do laboratório P1-02
([specs/2026-09-13-partial-retry-without-rebuild/evidence.md](../2026-09-13-partial-retry-without-rebuild/evidence.md#hosted-acceptance-final--2026-09-15))
é citada aqui **apenas como precedente técnico**, nunca como evidência
corporativa:

- Run `34986578076`, sandbox AWS `712107929769`/`us-east-1`, role
  `github-actions-image-base-p102-lab`, repositórios
  `p102-lab-go1-26`/`p102-lab-go1-26-dev`.
- Demonstrou, em execução real (não fixture): retry/reuse sem rebuild,
  publicação por digest com read-back exato, Cosign keyless, SPDX SBOM e
  provenance verificados, `stable_touched=false`.
- **Isso prova que o mecanismo funciona tecnicamente em AWS real.** Não
  prova nada sobre a conta corporativa, a role corporativa, a CA
  corporativa, a decisão Sigstore corporativa ou qualquer aceite externo.

Nenhuma linha deste precedente deve ser copiada para as seções abaixo como
se fosse evidência corporativa.

## External decisions

| Decisão | Owner | Estado | Referência |
| --- | --- | --- | --- |
| Conta/região/role AWS | Cloud/IAM | NOT RUN | — |
| ECR corporativo | Cloud/IAM | NOT RUN | — |
| CA corporativa | PKI/Segurança | NOT RUN | — |
| Sigstore Option A/B | Segurança/AppSec | NOT RUN | ADR-0002 PROPOSED |
| Network/mirror Wolfi | Network/Segurança | NOT RUN | — |
| Scanner/AppSec adicional | AppSec/Segurança | NOT RUN | ADR-0003 PROPOSED |

## IAM

_Vazio até execução do Stage 1/2._

## OIDC

_Vazio até execução do Stage 1/2._

## CA

_Vazio até execução do Stage 1/2. CE2E-15 depende diretamente desta seção._

## Network

_Vazio até decisão de Stage 1, se aplicável._

## Build

_Vazio até execução do Stage 3._

## Scan

_Vazio até execução do Stage 3._

## Contract

_Vazio até execução do Stage 3._

## OCI

_Vazio até execução do Stage 3/4._

## Publication

_Vazio até execução do Stage 4._

## Read-back

_Vazio até execução do Stage 4/5._

## Signature

_Vazio até execução do Stage 4/5. CE2E-09 depende da decisão Sigstore
registrada em "External decisions" acima._

## SBOM

_Vazio até execução do Stage 4/5._

## Provenance

_Vazio até execução do Stage 4/5._

## Stable isolation

_Vazio. Esperado permanecer `stable_touched=false`/ausência de toque
durante toda a execução (CE2E-12), sem exercitar promoção/recovery neste
E2E._

## Final acceptance

_Vazio até execução do Stage 7._

## Revisão

Autor/contexto: Containers Products, sessão de planejamento (2026-09-15).
Nenhuma revisão independente foi realizada sobre este arquivo ainda —
consultar [handoff.md](handoff.md) para o próximo passo. Auto-revisão não
equivale a revisão independente.

## Limites e resultado

Implementado nesta entrega: estrutura documental completa (spec, plan,
tasks, acceptance, evidence, handoff). Não implementado: qualquer execução
corporativa, qualquer decisão externa, qualquer recurso AWS real. Depende
inteiramente de terceiros (Cloud/IAM, PKI/Segurança, Network/Segurança,
AppSec/Segurança, Admin GitHub) para sair do estado `NOT RUN`. Nenhum
identificador de run/artifact foi inventado.
