# ACCEPTANCE — P0-04: First Corporate E2E

Estado geral desta entrega: **todos os critérios abaixo estão `NOT RUN`**.
Nenhum critério pode ser marcado `PASS` com base na evidência sandbox do
P1-02 — ela é citada apenas como precedente técnico
([evidence.md](evidence.md)). Um critério obrigatório não executado impede
declarar `P0-04 HOSTED_ACCEPTANCE` como concluído.

| ID | Critério | Evidence required | Owner / Acceptor | Blocking | Current state |
| --- | --- | --- | --- | --- | --- |
| CE2E-01 | Workflow federado aprovado executa na main corporativa autorizada | Run hospedado real com guard de evento/repository/ref conferido | Containers Products (executa) / Admin GitHub (confirma regras centrais) | Sim | NOT RUN |
| CE2E-02 | OIDC assume a role corporativa aprovada | `AssumeRoleWithWebIdentity` com claims (`repository`, `repository_id`, `ref`) conferidas contra a trust aprovada | Cloud/IAM (aprova) / Containers Products (executa) | Sim | NOT RUN |
| CE2E-03 | `go1-26`/`go1-26-dev` são construídos sem rebuild entre gates | Timestamps/steps/artifact IDs consistentes entre gate e publicação, mesmo padrão do P1-02 | Containers Products | Sim | NOT RUN |
| CE2E-04 | Scan técnico (Trivy) PASS | Relatório de scan por arquitetura, severidade bloqueante ativa, sem exceção nova | Containers Products (executa) / AppSec (adequação, se solicitada) | Sim | NOT RUN |
| CE2E-05 | Functional contract PASS | Relatório funcional (compilado, par `-dev`, ambas arquiteturas) com run/attempt/revisão registrados | Containers Products | Sim | NOT RUN |
| CE2E-06 | OCI multiarch validado | Digests `linux/amd64` e `linux/arm64` presentes e verificados no índice | Containers Products | Sim | NOT RUN |
| CE2E-07 | Publicação por digest para o(s) repositório(s) ECR corporativo(s) autorizado(s) | Preflight `DescribeRepositories` confirma `IMMUTABLE`, zero exclusions, scan on push e AES256 antes de `skopeo copy --all --preserve-digests`; nenhuma criação/reconfiguração pelo publisher | Containers Products (executa) / Cloud/IAM (aprova destino) | Sim | NOT RUN |
| CE2E-08 | ECR read-back == validated digest | `validated_digest == copied_digest == remote_digest` observado por leitura direta do ECR | Containers Products | Sim | NOT RUN |
| CE2E-09 | Cosign conforme decisão corporativa (Option A/B do ADR-0002) | `cosign verify` com identidade/issuer aprovados pela decisão registrada | AppSec/Segurança (decide) / Containers Products (executa) | Sim | NOT RUN — **bloqueado pela decisão Sigstore ainda pendente** |
| CE2E-10 | SPDX SBOM verificável | `cosign verify-attestation --type spdxjson`, subjects (index + plataformas) vinculados aos digests publicados | Containers Products | Sim | NOT RUN |
| CE2E-11 | Provenance verificável | `gh attestation verify`, `signer-workflow`/`source_ref` corretos | Containers Products | Sim | NOT RUN |
| CE2E-12 | `stable` untouched | Ausência de `promote-stable`/`recover-stable`/`imagetools create --tag stable`; repositório operacional sem escrita nova | Containers Products + Cloud/IAM (confirmação de leitura) | Sim (guard) | NOT RUN |
| CE2E-13 | Evidência preservada | Artifact de evidência completo (contexto, gate, publicação, verificação, resultado final), retido conforme política vigente | Containers Products | Sim | NOT RUN |
| CE2E-14 | Zero privilege escalation | Policy efetivamente anexada revisada; nenhum grant além do inventário aprovado; nenhuma criação de recurso pelo workflow recorrente | Cloud/IAM (aprova) / Containers Products (executa) | Sim | NOT RUN |
| CE2E-15 | CA corporativa real validada | Manifesto real, sem MOCK; verificação de conectividade/trust nas duas arquiteturas (amd64 e arm64) | PKI/Segurança (fornece) / Containers Products (verifica) | Sim | NOT RUN — **bloqueado pela ausência da CA corporativa real** |

## Negativos e limites

Cada critério acima é sobre o **caminho positivo** de um único candidato
(`go1-26`/`go1-26-dev`). Os seguintes casos permanecem explicitamente **fora**
do escopo de aceite desta entrega e não devem ser inferidos como cobertos:

- Nenhum negativo de acesso IAM (conta/região/recurso não autorizado) é
  exigido para o CE2E mínimo — esses casos pertencem ao laboratório
  dedicado do P1-04 (`p104-iam-lab`), não a este E2E.
- Nenhuma corrupção/ausência/formato inválido de evidência é exercitada
  aqui — essas garantias já são cobertas pelos testes locais do P1-02
  (R4/R6/A06/A07, permanecem `LOCAL_PROVEN`, não re-exercitados
  corporativamente).
- Nenhum outro framework além de `go1-26`/`go1-26-dev` é avaliado.
- Nenhuma promoção/recovery de `stable` é exercitada (CE2E-12 verifica
  apenas ausência de toque, não testa o mecanismo de promoção em si).

## Aceite externo

| Decisão externa condicionante | Owner | Estado |
| --- | --- | --- |
| Conta/região/role AWS corporativos | Cloud/IAM | Pendente |
| Aceitação Option A/B do Sigstore (ADR-0002) | Segurança/AppSec | Pendente — bloqueia CE2E-09/10/11 |
| Fonte/manifesto da CA corporativa real | PKI/Segurança | Pendente — bloqueia CE2E-15 |
| Catálogo de ARNs ECR aprovado | Cloud/IAM | Pendente — bloqueia CE2E-07/08 |
| Regras centrais/proteções do(s) repositório(s) | Admin GitHub/Segurança | Pendente — bloqueia CE2E-01 |
| Adequação formal de Trivy / integração adicional | AppSec/Segurança | Não bloqueante para o mínimo; registrar se exigida antes do Stage 4 |

Um critério obrigatório não executado impede declarar
`P0-04 HOSTED_ACCEPTANCE` como concluído. Nenhum critério deste documento
foi ou pode ser marcado `PASS` nesta sessão.
