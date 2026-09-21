# ADR-0005 — `stable` e lifecycle de 7 dias: realinhamento à RFC-013

| Informação | Valor |
| --- | --- |
| Estado | Aceito |
| Data | 16/09/2026 |
| Owners | Containers Products (`@alric-corp/github_xj7_maintainer`) + Infra (`alric-containers-image-base/infra`) |
| Revisão | Sem data de expiração — isto é a intenção original da RFC-013 restaurada, não uma exceção temporária |
| Aplicação | `infra/ecr/main.tf` (mutability exclusion) e `infra/ecr/locals.tf` (lifecycle); `scripts/pipeline/release/validate_ecr_repository.py` (preflight); `.github/workflows/promote-stable.yml` (kill switch + pair binding) |
| Origem | RFC-013 "Convenção de imagens"/"Publicação e retenção"; achado operacional de 16/09/2026 (ADR-0004) que desativou a promoção automática como mitigação temporária |
| Substitui | Nenhum ADR anterior. Refina o estado que o [ADR-0004](0004-v1-referencia-go126.md) deixou como `STABLE = OUT_OF_SCOPE` — este ADR reverte especificamente essa parte, para `go1-26`/`go1-26-dev` |

## Contexto

A RFC-013 sempre definiu três identidades de consumo — `stable` (ponteiro de
conveniência), build tag imutável (rastreabilidade) e OCI index digest
(identidade exata) — e uma retenção de 7 dias para builds históricos
(`docs/consumer-verification-contract.md`, "Publicação e retenção" da RFC).
Nenhuma dessas duas coisas nunca foi implementada de fato: os dois ECRs Go
foram provisionados em 15/09/2026 (P0-04) como `IMMUTABLE` puro, sem
exclusão para `stable`, e sem lifecycle policy (`create_lifecycle_policy =
false`, adiado por `OCI_ATTESTATION_LIFECYCLE_RISK = TO_BE_VALIDATED`).

Em 16/09/2026, a V1 de referência ([ADR-0004](0004-v1-referencia-go126.md))
encontrou o cron de promoção já com um candidato elegível contra esse ECR
`IMMUTABLE` sem exclusão — a primeira promoção teria sucesso, mas toda
promoção seguinte falharia ao tentar mover a tag (immutable tag mutation).
A mitigação foi um kill switch (`STABLE_PROMOTION_AUTHORIZED`) que desativa
o job de promoção inteiro, e `STABLE = OUT_OF_SCOPE` foi registrado como
estado da V1 de referência — correto como mitigação de emergência, mas não
como intenção final: a RFC nunca pretendeu que `stable` ficasse fora de
escopo permanentemente, só que a fábrica não deveria escrevê-la sem a
configuração de ECR correta por trás.

Este ADR fecha essa lacuna: implementa o que a RFC sempre descreveu, em vez
de continuar adiando.

## Decisão

1. **`infra/ecr`** (image-base) muda o `image_tag_mutability` desejado
   dos dois repositórios Go de `IMMUTABLE` para `IMMUTABLE_WITH_EXCLUSION`,
   com exatamente uma exclusão: `{filterType: WILDCARD, filter: "stable"}`.
   Nenhum outro filtro (`latest`, `*`, `build*`) é aceito. Mutability
   continua sendo responsabilidade exclusiva de Infra — o publisher nunca
   volta a chamar `ecr:PutImageTagMutability`.

2. **Reconciliação one-time (nota histórica de implementação no LAB).** A
   role Infra corporate-like não tem `ecr:PutImageTagMutability` (decisão
   deliberada, não um bug). Trazer os dois repositórios então existentes ao
   novo estado desejado usou o mecanismo preparado em `drift-remediation/`,
   no repositório pré-greenfield `alric-containers-registry`: política
   temporária, anexada, usada uma vez, removida — nunca uma concessão
   permanente. Esse mecanismo pertencia à topologia legada; o rehearsal
   greenfield de 19–20/09/2026 recriou os repositórios já no estado
   desejado, e nenhuma implementação atual depende de
   `alric-containers-registry` ou do seu `drift-remediation/`. Repositórios
   novos (expansão futura) já nascem no formato correto, sem precisar dessa
   reconciliação.

3. **Preflight fail-closed.** `validate_ecr_repository.py` (Containers)
   passa a exigir exatamente `IMMUTABLE_WITH_EXCLUSION` com exatamente
   `[{filterType: WILDCARD, filter: "stable"}]` — rejeita `MUTABLE`,
   `IMMUTABLE` puro, exclusão diferente de `stable`, ou `stable` combinada
   com qualquer segunda exclusão.

4. **Promoção continua no workflow dedicado** (`promote-stable.yml`, já
   existente desde P1-01): candidato validado → re-scan → contrato →
   publicação/read-back → evidência de trust → promove por referência
   (`docker buildx imagetools create`, sem rebuild/repack). O kill switch
   (`STABLE_PROMOTION_AUTHORIZED`) permanece como controle operacional
   permanente, não como uma bandeira temporária a remover depois.

5. **Binding runtime/dev antes da escrita.** Os pares compilados são
   derivados do catálogo. `promotion_batch.py` resolve ambos os candidatos,
   exige soak/quarentena e a mesma identidade `r<run_id>-a<attempt>` via
   `verify_promotion_pair.py`, verifica trust e re-scan de ambos antes de
   permitir a primeira escrita de `stable`. Lote incompleto ou um membro
   inelegível bloqueia as escritas. `verify_promotion_pairs.py` repete o
   binding após as escritas/read-backs, sem substituir a autorização prévia.
   O controle anterior apenas posterior fica registrado no histórico Git.
   Framework interpretado mantém sua semântica individual.

   ECR não oferece transação atômica entre duas tags. Falha da segunda
   escrita ou de qualquer read-back mantém o par com `promoted=false`,
   preserva os snapshots anteriores e exige triagem/recuperação do par
   conhecido, sem rebuild. Promoção e recovery compartilham o lock por
   role/região e não cancelam a execução ativa; escritores externos não
   participam dessa exclusão.

6. **Lifecycle de 7 dias**, com `stable` protegida por prioridade de regra
   (não por "não bater no padrão da build tag" — uma mesma imagem pode ter
   as duas). Ver `infra/ecr/locals.tf` (image-base) para o mecanismo
   exato (duas regras, a primeira reivindica qualquer imagem tagueada
   `stable` antes que a segunda possa expirá-la por idade).

## Consequências

- `stable` volta a significar o que a RFC sempre disse: conveniência para
  quem aceita mudança de conteúdo, não uma segunda fonte de verdade.
- Builds imutáveis (rastreabilidade/rollback) e o digest (identidade exata,
  supply-chain) continuam existindo exatamente como antes — nada nessa
  camada muda.
- A retenção de 7 dias reduz o acúmulo de builds históricos sem afetar
  `stable` nem a capacidade de recuperação (`recover-stable.yml` continua
  funcionando contra qualquer build ainda retido).
- `POST_PUBLICATION_TERRAFORM_DRIFT` deve continuar `NONE` depois da
  reconciliação one-time — o objetivo não é criar um novo desvio permanente
  entre Terraform e AWS, é fechar o que já existia.

## Alternativas rejeitadas

- **Deixar `stable` fora de escopo indefinidamente:** rejeitada — contraria
  a RFC-013 sem necessidade técnica; o bloqueio identificado no ADR-0004 era
  a configuração do ECR, não uma limitação de design.
- **Conceder `ecr:PutImageTagMutability` permanentemente à role Infra:**
  rejeitada — amplia a superfície de permissão além do modelo
  corporate-like sem necessidade recorrente (mutability muda uma vez por
  repositório, não a cada run).
- **Confiar em "stable nunca bate no padrão da build tag" para proteger a
  lifecycle policy:** rejeitada explicitamente — uma imagem pode ter as
  duas tags ao mesmo tempo; só a ordem de prioridade das regras garante a
  proteção.
- **Promover runtime e dev sem verificar binding:** rejeitada — permitiria
  publicar um par cujo runtime e toolchain nunca foram testados juntos no
  mesmo release, contrariando o próprio propósito do par runtime/-dev.

## Critério de revisão

Nenhum — isto é a RFC-013 sendo implementada como sempre esteve descrita,
não uma exceção. Revisar apenas se a RFC-013 for formalmente alterada nesse
ponto.

## Evidência

Binding runtime/dev, preview de lifecycle antes da aplicação e read-back de
`stable` após a promoção real foram verificados em execução hospedada real;
detalhe no histórico Git.
