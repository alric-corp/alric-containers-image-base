# SPEC — P0-04: First Corporate E2E

## Status inicial

**PLANNED / BLOCKED ON CORPORATE PREREQUISITES.**

Este spec descreve o que precisa ser verdadeiro para que a primeira cadeia
corporativa end-to-end seja executada e aceita. Nenhuma parte foi
implementada em ambiente corporativo. Nada aqui deve ser lido como
`IMPLEMENTED`: é planejamento, não execução.

## Propriedade

P0-04 corresponde tecnicamente ao **Estágio E** já definido em
[docs/corporate-adoption.md](../../docs/corporate-adoption.md#4-ordem-de-execução-posterior)
("Executar a primeira cadeia no ambiente autorizado"). Não é um conceito
novo: é a formalização, em spec próprio, de um estágio que o pacote P0-03
já antecipava, incluindo a indicação de `go1-26` como candidato possível.
P0-04 herda as pré-condições dos Estágios A–D de P0-03 (decisões, recursos,
identidades configuradas, validação sem publicação) e não substitui nenhuma
delas.

## Objetivo

Provar a cadeia mínima end-to-end da fábrica no ambiente corporativo
autorizado, usando exatamente os controles/integrações que forem
formalmente decididos (não os do sandbox P1-02):

```
build
  → scan (Trivy)
  → functional contract (compilado, par -dev)
  → OCI multiarch (amd64 + arm64)
  → publication by digest
  → ECR read-back
  → Cosign (assinatura)
  → SPDX SBOM
  → provenance
  → evidence
```

Resultado observável: um índice OCI construído, escaneado, testado
funcionalmente e publicado por digest em um repositório ECR corporativo
isolado e explicitamente aprovado, com assinatura/SBOM/provenance
verificáveis e evidência completa preservada — sem promover `stable`.

## Candidato inicial

```
CORPORATE_E2E_CANDIDATE = go1-26 (com o companion go1-26-dev)
```

Nenhum outro framework deve ser incluído no primeiro E2E. Justificativa,
baseada em evidência já obtida (não em preferência):

- **Sandbox hosted acceptance completo**: `specs/2026-09-13-partial-retry-without-rebuild/`
  comprovou, no run `34986578076`, retry/reuse sem rebuild, `selected_attempt=1`,
  `reused=true`, publicação por digest, read-back, Cosign, SPDX SBOM e
  provenance — todos `VERIFIED`/`PASS` — especificamente para `go1-26`/`go1-26-dev`.
- **Scan atualmente saudável**: `go1-26`/`go1-26-dev` não constam na lista de
  frameworks bloqueados pela CVE upstream de zlib (ver
  [Parallel Track — zlib/CVE](plan.md#parallel-track--zlibcve) no plan.md).
- **Functional contract comprovado**: contrato compilado, par `-dev` no
  mesmo run, ambas as arquiteturas, sem rebuild entre gates.
- **Multiarch comprovado**: `linux/amd64` e `linux/arm64` publicados e
  verificados por digest no registry real (sandbox).
- **Publication/read-back comprovados**: cadeia completa
  `gate_digest == verified_digest == validated_digest == copied_digest == remote_digest`
  observada em execução hospedada real, não apenas em fixture.
- **Assinatura/SBOM/provenance comprovados**: Cosign keyless, SPDX attestado
  (index + ambas as plataformas) e provenance SLSA-shaped, todos verificados
  sob identidade própria do workflow, em execução hospedada real.
- Já indicado textualmente em `docs/corporate-adoption.md`, Estágio E:
  "Primeiro piloto runtime com seu par -dev quando exigido pelo plano;
  Go1-26 é candidato possível somente se ainda elegível, não promessa de
  scan verde." — P0-04 confirma essa elegibilidade com evidência atual, não
  promete resultado.

## Non-goals

P0-04 explicitamente **não** se propõe a:

- Provar o catálogo completo (11 contratos, demais frameworks).
- Promover `stable` automaticamente ou como consequência do E2E
  (`STABLE_PRODUCTION_PROMOTION = OUT_OF_SCOPE`, ver plan.md).
- Declarar produção pronta (a RFC-013 já registra
  "Prontidão para produção: **Não**" como estado vigente do produto).
- Concluir o P1-04 (contrato de permissões IAM) — P0-04 consome a proposta
  P1-04 como referência, mas não substitui sua validação/aceite próprios
  (`AWS_VALIDATOR_CHECKED`/`AWS_SIMULATION_CHECKED`/`SANDBOX_EXECUTION_VERIFIED`
  continuam sob responsabilidade do P1-04).
- Homologar AppSec (Trivy continua o gate técnico vigente; adequação formal
  e integração adicional — Veracode/SCA — permanecem decisão do ADR-0003).
- Resolver o bloqueio upstream de zlib/CVE em outros frameworks.
- Provar nível SLSA formal (provenance é produzida e verificada; nenhuma
  classificação de nível é reivindicada).
- Provar consumo cross-account completo (`docs/consumer-verification-contract.md`
  e PAR-11 continuam com aceite externo separado).
- Substituir decisões de Cloud/IAM, PKI/Segurança, Network/Segurança ou
  AppSec — P0-04 solicita e consome essas decisões, nunca as toma.

## Requisitos

Cada requisito registra owner, evidência esperada, se é bloqueante para o
E2E mínimo e sua classe de capability (ver
[Capability Matrix](plan.md#capability-matrix) no plan.md para a definição
completa das classes).

| ID | Requisito | Owner | Evidência esperada | Blocking? | Capability class |
| --- | --- | --- | --- | --- | --- |
| CR1 | Identidade corporativa autorizada: o workflow federado executa na main corporativa autorizada, sob a premissa de autoria do ADR-0003 | Admin GitHub + Containers Products | Run hospedado real, guard de evento/ref/repository conferido | Sim | SANDBOX-EXECUTE (código) / EXTERNAL-DECISION (regras centrais) |
| CR2 | Alvo AWS corporativo: conta/região/role corporativos nomeados e distintos do sandbox `712107929769` | Cloud/IAM | Conta/região/role documentados com owner e data | Sim | EXTERNAL-DECISION |
| CR3 | CA corporativa real instalada, sem MOCK, verificada nas duas arquiteturas | PKI/Segurança | Manifesto real + evidência de stage/verify amd64 e arm64 | Sim (CE2E-15) | EXTERNAL-DECISION |
| CR4 | Confiança de rede/pacotes: acesso a Wolfi (direto ou mirror aprovado), sem expor `apk-configuration`/JWKS se isolamento for exigido | Network/Segurança | Decisão registrada + evidência de build usando a origem aprovada | Condicional (só bloqueia se corporate exigir isolamento) | EXTERNAL-DECISION |
| CR5 | Scan técnico (Trivy) PASS, política vigente, sem exceção nova | Containers Products (execução) / AppSec (adequação) | Relatório de scan por arquitetura, severidade bloqueante ativa | Sim | SANDBOX-EXECUTE / CORPORATE-PROPOSE |
| CR6 | Contrato funcional PASS (compilado, par `-dev`, ambas arquiteturas) | Containers Products | Relatório funcional com run/attempt/revisão | Sim | SANDBOX-EXECUTE |
| CR7 | Identidade multiarch: `linux/amd64` e `linux/arm64` com digests verificados | Containers Products | Manifests de plataforma no OCI validado | Sim | SANDBOX-EXECUTE |
| CR8 | Publicação por digest no(s) repositório(s) ECR corporativo(s) autorizado(s) | Containers Products (execução) / Cloud/IAM (recurso) | `skopeo copy --all --preserve-digests`, sem rebuild/repack | Sim | SANDBOX-EXECUTE (código) / CORPORATE-PROPOSE (destino) |
| CR9 | Read-back: digest observado no ECR == digest validado | Containers Products | Comparação `validated_digest == copied_digest == remote_digest` | Sim | SANDBOX-EXECUTE |
| CR10 | Assinatura Cosign conforme decisão corporativa do ADR-0002 (Option A/B) | AppSec/Segurança (decisão) / Containers Products (execução) | `cosign verify` com identidade/issuer aprovados | Sim | EXTERNAL-DECISION (decisão) / SANDBOX-EXECUTE (execução após decisão) |
| CR11 | SBOM SPDX verificável, subjects vinculados aos digests publicados (index + plataformas) | Containers Products | `cosign verify-attestation --type spdxjson` | Sim | SANDBOX-EXECUTE |
| CR12 | Provenance verificável, `signer-workflow`/`source_ref` corretos | Containers Products | `gh attestation verify` | Sim | SANDBOX-EXECUTE |
| CR13 | Evidência completa preservada (contexto, gate, publicação, verificação, resultado final) | Containers Products | Artifact de evidência, mesmo padrão do P1-02 | Sim | LOCAL-EXECUTE / SANDBOX-EXECUTE |
| CR14 | Nenhuma promoção de `stable` durante o E2E | Containers Products + Cloud/IAM | Ausência de `promote-stable`/`recover-stable`/`imagetools create --tag stable`; repositório operacional sem escrita nova | Sim (guard) | FORBIDDEN (ação) |
| CR15 | Zero privilege escalation: nenhum grant além do inventário aprovado, sem `ecr:*`, sem criação de recurso pelo workflow recorrente | Cloud/IAM (aprovação) / Containers Products (execução) | Policy efetivamente anexada revisada; ausência de `CreateRepository`/`PutImageTagMutability` no perfil recorrente (Profile A) | Sim | EXTERNAL-DECISION (aprovação) / FORBIDDEN (qualquer escalonamento) |

## Restrições e invariantes

- Preservar a distinção do ADR-0003: autoria/manutenção dos workflows
  federados **não** é federação de identidade OIDC e **não** dispensa
  requisitos de AppSec, auditoria, IAM, PKI ou rede.
- Preservar o modelo de isolamento de stable já documentado no P1-04: não
  existe condition key IAM por tag Docker; `PutImage` não separa build tags
  de `stable` dentro do mesmo repositório. P0-04 mitiga isso mantendo
  `stable` inteiramente fora de escopo, não por uma restrição IAM que não
  existe.
- Preservar Profile A (recursos pré-provisionados + role de execução) como
  recomendação, já validada tecnicamente no sandbox P1-02 (papel
  funcionalmente equivalente, contexto AWS distinto).
- Não presumir que a conta corporativa permitirá `CreateRepository` ou
  `PutImageTagMutability` no workflow recorrente.
- Não enfraquecer Trivy (severity, `ignore-unfixed`, exit-code, policy) para
  viabilizar o E2E.
- Não usar a evidência sandbox do P1-02 como prova de aceite corporativo —
  apenas como precedente técnico (ver evidence.md).
- Não tratar bloqueio de CVE upstream em outros frameworks (zlib) como
  impedimento ao E2E de `go1-26`, nem a saúde de `go1-26` como prova de que
  o bloqueio de outros frameworks não é real.

## Fora do escopo

Ver seção "Non-goals" acima — lista completa e vinculante. Adicionalmente,
fora do escopo desta spec: qualquer alteração em `retry_lab.py`,
`retry_lab_publish.py`, `partial-retry-lab.yml`, políticas IAM propostas em
`policies/aws/proposals/`, ADRs, ou no pacote `docs/corporate-adoption.md`
— mudanças nesses artefatos, se necessárias, pertencem às suas próprias
specs.

## Dependências

Ver [Dependency Matrix](plan.md#dependency-matrix) completa no plan.md.
Resumo dos bloqueantes obrigatórios: conta/região AWS corporativa, role de
execução IAM, trust OIDC, repositório(s) ECR corporativo(s), CA corporativa
real, decisão Sigstore (ADR-0002 Option A/B). Nenhum deles está sob controle
deste produto — todos exigem decisão/provisionamento externo antes do
Stage 4 (ver plan.md).

## Conclusão

Ver [acceptance.md](acceptance.md) para os critérios formais (CE2E-01–15,
todos `NOT RUN` nesta entrega) e [evidence.md](evidence.md) para a
estrutura de coleta, ainda vazia. `P0-04 HOSTED_ACCEPTANCE` só pode passar
de `NOT RUN` para `PASS` após execução real no ambiente corporativo,
seguindo os estágios definidos em [plan.md](plan.md).

## Perfil temporário de execução

Para a preparação do primeiro E2E, o entrypoint `.github/workflows/workflow.yml`
usa uma seleção explícita e exata:

```text
P0_04_EXECUTION_SCOPE = [go1-26, go1-26-dev]
P0_04_CATALOG_REDUCTION = EXECUTION ONLY
CATALOG_DEFINITIONS = UNCHANGED
OTHER_FRAMEWORK_EXECUTION = DISABLED FOR P0-04
STABLE = OUT_OF_SCOPE
```

`go1-26` é o runtime do contrato funcional; `go1-26-dev` permanece somente o
companion de build multi-stage. Java, Node, Python, .NET, Go 1.25 e versões
futuras não são selecionados neste rollout. O catálogo continua completo e
versionado. A expansão exige decisão explícita e revisão; ela não ocorre
automaticamente.

O scan de zlib/CVE dos demais frameworks segue em trilha paralela. Falhas
relacionadas a frameworks fora do perfil não bloqueiam o candidato Go 1.26 e
não são ignoradas, removidas ou declaradas saudáveis.

## Ownership do ECR e preflight obrigatório

`alric-corp/alric-containers-registry` é a source of truth da configuração dos
repositórios ECR. Este repositório é a source of truth somente do conteúdo e
das evidências dos artifacts publicados. O publisher assume destinos
pré-provisionados e executa `DescribeRepositories` seguido de validação
fail-closed antes do login/publicação. Ele não cria, configura nem repara ECR.

O contrato validado exige nome, ARN/account, URI/região, `IMMUTABLE`, nenhuma
exclusion filter, `scanOnPush=true` e encryption `AES256`. Qualquer ausência ou
divergência encerra a publicação antes de `PutImage`. Não há compatibilidade
temporária para `IMMUTABLE_WITH_EXCLUSION`.

O run sandbox `35022270017` observou o comportamento anterior alterando
`image-base-go1-26` e `image-base-go1-26-dev` para
`IMMUTABLE_WITH_EXCLUSION` com exclusion `stable`. Isso é finding técnico
histórico, não aceite corporativo e não é erro do Terraform. A remediação do
estado AWS deve ocorrer posteriormente pelo source of truth de Infra:
`IMMUTABLE_WITH_EXCLUSION` → `IMMUTABLE`.

```text
CONTAINERS_ECR_DRIFT_OBSERVED = YES — HISTORICAL RUN 35022270017
AWS_REMEDIATION_REQUIRED = YES
IAM_ENFORCED_SEPARATION = NO
PROCESS_ENFORCED_SEPARATION = YES
ARCHITECTURE_ENFORCED_SEPARATION = YES
```

Para PRs, o resolver `scripts/pipeline/governance/pr_execution_scope.py`
seleciona `P0_04` somente para paths específicos do candidato, documentação
ou spec. Qualquer alteração compartilhada, não-P0 ou ambígua seleciona
`FULL`. Durante o rollout, o schedule de promoção usa o mesmo par Go; o
workflow reutilizável de promoção permanece capaz de receber FULL de um
caller autorizado. Essa restrição é isolamento de recursos do rollout, não
autorização para promover `stable` no E2E corporativo.
