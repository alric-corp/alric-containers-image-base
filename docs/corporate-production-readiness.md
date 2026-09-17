# Corporate Production Readiness — Hardened Image Factory

Baseline: main `30fb7132f879e58c06f56e5bf5d2c34fbb061ebd`, 17/09/2026 (estado do
Registry/AWS conferido após a remoção do `image-base-dotnet8`). Este
documento é um **resumo de readiness e handoff**: diz o que a fábrica já provou
no LAB e o que ainda precisa ser adaptado e validado ao levá-la para o ambiente
corporativo. Não substitui o [pacote de adoção](corporate-adoption.md) (parâmetros,
responsáveis, checklist CA-xx) nem o [manifesto de migração](corporate-migration-manifest.md)
(classificação arquivo a arquivo); é a porta de entrada para os dois.

> **Não estamos levando um POC para o corporativo. Estamos levando uma
> implementação de referência já comprovada, que precisa ser portada e
> revalidada contra as dependências do ambiente corporativo.**

## Documentos relacionados

| Necessidade | Documento |
| --- | --- |
| Parâmetros a fornecer, responsáveis e checklist de aceite do destino (CA-01–18) | [Pacote de adoção corporativa](corporate-adoption.md) |
| Classificação KEEP / DO_NOT_MIGRATE / GENERATED por arquivo e repositório | [Manifesto de migração](corporate-migration-manifest.md) |
| Fronteiras de domínio, workflows e contrato com o executor compartilhado | [Arquitetura do repositório](repository-architecture.md) |
| Proposta, estado M01–M16 e "Prontidão para produção" | [RFC-013](../RFC-013-Image-Base-Completa-com-Mermaid.md) |
| Decisões pontuais e seu estado | [Índice de ADRs](adr/README.md) — em especial [ADR-0002](adr/0002-sigstore-trust-model.md) (Sigstore), [ADR-0003](adr/0003-controles-seguranca-workflows-federados.md) (fábrica federada), [ADR-0004](adr/0004-v1-referencia-go126.md) (V1 Go 1.26), [ADR-0005](adr/0005-stable-lifecycle-realinhamento-rfc013.md) (`stable`/lifecycle) |
| O que o consumidor verifica e como | [Consumer Verification Contract](consumer-verification-contract.md) |
| Permissões AWS, trust OIDC e proposta para Cloud/IAM | [Contrato IAM](iam-permission-contract.md) |
| Saúde, alertas, SLI/SLO propostos e limites da coleta | [Contrato operacional](m11-m04-operational-health.md) |
| Fechamento hospedado do golden path Go 1.26 | [V1 de referência — fechamento](v1-reference-closure-2026-09-16.md) |

## A pergunta

**A solução está pronta para ser levada ao ambiente corporativo?**

- **Sim** — como arquitetura, implementação de referência e conjunto de
  contratos comprovados em infraestrutura real (GitHub Actions + ECR + Terraform)
  no LAB.
- **Não** — como copy/paste. Nenhuma execução aconteceu ainda em conta,
  registry, rede, PKI, runner ou IAM corporativos.

São duas prontidões diferentes, e este documento as separa deliberadamente:

| | O que significa | Estado |
| --- | --- | --- |
| **REFERENCE IMPLEMENTATION READINESS** | Engine, gates, contratos, modelo de release e governança existem, estão testados e foram exercitados de ponta a ponta num ambiente real | **READY** |
| **CORPORATE ENVIRONMENT VALIDATION** | Os mesmos mecanismos executados contra as dependências reais do corporativo, com as decisões externas tomadas e os aceites registrados | **PENDING** |

Nem "production ready sem ressalvas", nem "é apenas um POC". O estado correto
está entre os dois: arquitetura, engine e supply chain provados; integração
corporativa por executar e validar.

## Estado atual da referência

Descoberto na árvore da baseline acima, não copiado de números históricos.

| Item | Estado em `main` |
| --- | --- |
| Definições no catálogo (`frameworks/*.yaml`) | **16**: `dotnet10`, `dotnet10-dev`, `go1-25`, `go1-25-dev`, `go1-26`, `go1-26-dev`, `java21`, `java21-dev`, `java25`, `java25-dev`, `nodejs22`, `nodejs22-dev`, `nodejs24`, `nodejs24-dev`, `python3-13`, `python3-14` |
| Package source ativa | **Wolfi** (`packages.wolfi.dev/os`), única — `distroless/image-base.yaml` |
| Alpine / multi-source | Não adotados como source ativa. Investigados e recusados por decisão de produto ([ADR-0007](adr/0007-multi-source-alpine-recusado.md)); permanecem como evidência histórica |
| .NET | `dotnet10` / `dotnet10-dev`. `dotnet8` removido do catálogo em 17/09/2026 — fim de suporte LTS em 11/2026 ([ADR-0001](adr/0001-dotnet8-fora-do-lote-padrao.md), adendo) |
| Exceções ao lote padrão (`policies/operations/health.json` → `exceptions`) | Nenhuma. Lote FULL = catálogo inteiro |
| Golden path (`execution_scope.current`) | `go1-26` + `go1-26-dev` — build automático, publicação e promoção restritos a esse par ([ADR-0004](adr/0004-v1-referencia-go126.md)); os outros 14 permanecem no catálogo e no lote FULL, sem publicação automática |
| Publicação / promoção no LAB | Par Go publicado por digest, assinado, atestado e verificado externamente; `stable` promovida com read-back e recuperada sem rebuild; Terraform sem drift depois de tudo ([fechamento V1](v1-reference-closure-2026-09-16.md), [evidence ADR-0005](../specs/2026-09-16-stable-lifecycle-rfc013/evidence.md)). Promoção automática protegida por kill switch (`STABLE_PROMOTION_AUTHORIZED`) |
| Catálogo completo | 16/16 definições **buildam e passam no Trivy nas duas arquiteturas** em run real de CI (17/09/2026, [revalidação completa](../specs/2026-09-17-full-catalog-revalidation/evidence.md)). O contrato funcional não roda no caminho de PR por desenho; para os 14 fora do `execution_scope` ele existe em código e foi exercitado em runs anteriores, mas não faz parte da execução automática atual |
| Bloqueios upstream | Nenhum aberto. O bloqueio zlib (`CVE-2026-85091`) que travava Java 21 e mais 12 definições foi resolvido pelo próprio Wolfi em 17/09/2026 ([ADR-0006](adr/0006-java21-zlib-blocker-remediation-options.md), addendum); gate não relaxado |
| Registry (`alric-containers-registry`) | Terraform declara os mesmos 16 repositórios ECR do catálogo; AWS tem 16 `image-base-*`. O `image-base-dotnet8` vazio foi destruído pelo Terraform em 17/09/2026 (episódio 4 de `drift-remediation/`, permissão de delete temporária, removida em seguida). O corporativo provisiona primeiro só o que o golden path precisa |
| Decisões externas em aberto | Sigstore (ADR-0002), scanner/requisitos da fábrica federada (ADR-0003), CA corporativa, IAM/OIDC, destino de alerta e SLA — todas `EXTERNAL_PENDING`, listadas em [RFC-013 → Prontidão](../RFC-013-Image-Base-Completa-com-Mermaid.md#prontidão-para-produção) |

## Capacidades já comprovadas no LAB

Legenda: **PROVEN** = exercitado em run hospedado real com evidence versionada;
**DESIGNED** = implementado e testado localmente, sem exercício hospedado
completo; **TO_VALIDATE** = depende do ambiente corporativo para ser provado.

### Composição

| Capacidade | Estado |
| --- | --- |
| Melange (pacote de CAs compilado na fábrica) + Apko (composição declarativa OCI) + Wolfi | PROVEN |
| Base distroless sem shell nem gerenciador de pacotes; non-root por padrão | PROVEN |
| Variantes runtime / `-dev` (toolchain e shell só no estágio de build) para Go, Java e .NET; Node e Python interpretados | PROVEN |
| Multiarch `amd64` + `arm64` em um único índice OCI, exigido em código | PROVEN |
| Sem Dockerfile para as imagens base; `apko.lock.json` e data do commit fixam o build | PROVEN |

### Build

| Capacidade | Estado |
| --- | --- |
| Build once: o mesmo `image.oci` segue por scan, contrato e publicação | PROVEN |
| Sem rebuild entre validação e publicação; `validated == copied == remote digest` | PROVEN |
| Binding runtime/`-dev` do mesmo run na promoção (`PAIR_BOUND`) | PROVEN |
| Retry parcial sem rebuild (reuso de contrato válido no mesmo run) | PROVEN o reuso; continuação completa da publicação após retry ainda `PENDING` de aceite hospedado |

### Security

| Capacidade | Estado |
| --- | --- |
| Trivy como gate bloqueante, por arquitetura, `--ignore-unfixed`, `CRITICAL,HIGH,MEDIUM,LOW` + segredos | PROVEN |
| Gate nunca relaxado: nenhuma exceção de CVE, inclusive na recuperação | PROVEN |
| Fail closed em toda ausência/corrupção de evidence, artifact ou read-back | PROVEN |
| Verdict de scan entendido como `f(digest, versão do scanner, estado da advisory DB)` — CVEs sem correção reportadas separadamente, sem falhar o job | PROVEN o modelo; captura do metadado da Trivy DB no evidence do executor compartilhado é recomendação, não implementação |
| Trust store: bundle de CAs na imagem, `SSL_CERT_FILE`/`NODE_EXTRA_CA_CERTS`, Java cacerts, .NET `CustomRootTrust`; gate `image-trust.yml` com CA sintética | PROVEN o mecanismo; **TO_VALIDATE** com a PKI corporativa (perfil atual é `public`, âncoras corporativas vazias) |
| Chave Wolfi versionada + pin + preflight offline + drift detect-only | PROVEN como defense-in-depth; apko ainda descobre chaves pela rede — não é trust exclusiva ([risco residual](wolfi-signing-key.md)) |

### Functional contracts

| Capacidade | Estado |
| --- | --- |
| Contrato executado sobre o próprio artifact candidato, `amd64` e `arm64`, sem rebuild | PROVEN (Go 1.26 hospedado; demais famílias em runs anteriores) |
| Verificação: versão do runtime, UID/GID 10000 herdados, raiz somente leitura com áreas graváveis explícitas, bundle de CAs, timezone, TLS positivo **e** negativo | PROVEN |
| Compilados (Go/Java/.NET): projeto mínimo versionado, multi-stage `-dev` → runtime, sem rede no build | PROVEN |
| Toolchain e shell presentes na `-dev`, ausentes no runtime | PROVEN |
| Cobertura decidida em código (`runtime_images.plan`): 11 contratos diretos, seis interpretados e cinco compilados; skip explícito nunca conta como PASS | PROVEN |

### Registry / release

| Capacidade | Estado |
| --- | --- |
| ECR `PREPROVISIONED_ONLY`: o publicador não cria, não repara e não reconfigura repositório (`CONTAINERS_INFRA_MUTATIONS = 0`) | PROVEN |
| Preflight fail-closed contra ECR fora do contrato — observado ao vivo rejeitando um repositório ainda não reconciliado | PROVEN |
| `IMMUTABLE_WITH_EXCLUSION`, `stable` como única tag móvel, build tags imutáveis | PROVEN |
| OCI index digest como identidade forte; `stable` e build tag como conveniência/versão | PROVEN |
| Lifecycle de 7 dias com `stable` protegida por prioridade de regra | PROVEN a proteção (preview real, 0 selecionadas); expiração positiva `>7d` ainda não observada contra dado real — genuína limitação de tempo decorrido |
| Candidato → soak → re-scan → `stable` por referência → read-back (`observed == candidate`) → `promoted=true` | PROVEN |
| Recovery para digest anterior com as mesmas verificações, sem rebuild; quarentena versionada | PROVEN |

### Supply chain

| Capacidade | Estado |
| --- | --- |
| Cosign keyless sobre o índice, identidade exata do workflow assinante e `refs/heads/main`, vinculada a IDs imutáveis de repository/owner | PROVEN |
| SPDX SBOM gerado pelo apko e atestado por digest (índice + duas plataformas) | PROVEN |
| Provenance GitHub (SLSA v1) sobre o índice | PROVEN |
| Verificação por consumidor externo, sem checkout do repositório (`scripts/verify-image.sh`) | PROVEN |
| Modelo de leitura das três evidências | SBOM → **WHAT** (o que está na imagem) · Provenance → **HOW / WHERE** (quem/como a produziu) · Signature → **WHO / INTEGRITY** (identidade e integridade do índice). Evidence disponível não é enforcement no runtime |

### Infra / governance

| Capacidade | Estado |
| --- | --- |
| Terraform como único dono do ECR (mutabilidade, lifecycle, repository policy); plan/apply por workflow controlado, com apply human-approved | PROVEN |
| OIDC sem credenciais estáticas; trust ligada a IDs imutáveis; PR/fork sem AWS | PROVEN |
| Separação lógica Infra / Containers: roles distintas, capability model corporate-like documentado | PROVEN o desenho e a operação; `IAM_ENFORCED_SEPARATION = NO` — a role Containers do LAB ainda pode mais do que o publicador faz (ver [contrato IAM](iam-permission-contract.md)) |
| No-drift pós-publicação/promoção/recovery (`terraform plan` → `No changes.`) | PROVEN |
| Permissões destrutivas fora da role permanente; concessão temporária one-off auditada (`drift-remediation/`) | PROVEN |
| CODEOWNERS + revisão obrigatória de code owner + checks `test`/`lint-workflows` + lints de hardening/pins/retenção/lote | PROVEN no LAB; `enforce_admins` desligado por decisão do sandbox — **TO_VALIDATE** como controle corporativo |
| Health diário, drift Wolfi, resumo por framework, `execution_scope` visível | PROVEN a detecção; destino externo de alerta `null` e SLA — **TO_VALIDATE** |
| Renovate/Dependabot configurados | DESIGNED; ativação depende do administrador |

## Classificação de readiness

| Capability | Readiness |
| --- | --- |
| Architecture | READY |
| Image composition engine (Melange / Apko / Wolfi) | READY |
| Multiarch build (build once, digest preservado) | READY |
| Security gates (Trivy, fail closed, sem exceção) | READY |
| Functional contracts | READY |
| OCI supply chain (Cosign, SBOM, provenance, verificação externa) | READY |
| Release / promotion model (soak, `stable`, read-back) | READY |
| Recovery model | READY |
| Infrastructure-as-Code model (Terraform-owned ECR, preprovisioned-only) | READY |
| Governance model (CODEOWNERS, gates, lints, ADRs) | READY |
| Corporate IAM / OIDC | TO VALIDATE |
| Corporate network / proxy / egress | TO VALIDATE |
| Corporate CA / PKI | TO VALIDATE |
| Corporate runner (Docker privilegiado, QEMU) | TO VALIDATE |
| Corporate ECR (resource policies, Org IDs, contas consumidoras) | TO VALIDATE |
| Corporate Sigstore / scanner decisions | TO DECIDE (ADR-0002, ADR-0003) |
| Corporate golden path Go 1.26 | TO PROVE |

## Valores do LAB que não são portáveis

O corporativo reutiliza **mecanismos, contratos, testes, arquitetura e
governança**. Não copia valores concretos. Cada item abaixo existe no LAB
com um valor real que deve ser substituído pelo equivalente corporativo,
fornecido pelo owner competente (ver [pacote de adoção → §2 e §3](corporate-adoption.md#2-mapa-de-parâmetros-e-ajustes)):

- AWS account IDs e regiões;
- Organization IDs usados nas resource policies de ECR;
- GitHub repository IDs e owner IDs (trust OIDC e `signing-identities.json`);
- nomes de roles (Infra e Containers) e ARNs;
- OIDC subjects, issuer, audience e demais valores de trust;
- bucket e configuração do Terraform backend;
- localização, fontes e hashes das CAs corporativas (manifesto de âncoras);
- repositórios internos e URLs (produto, biblioteca de workflows, registry);
- endpoints de rede, proxy e mirrors;
- runners (labels, capacidades, grupos);
- tags obrigatórias de recursos;
- nomes de Environments e suas proteções;
- `CODEOWNERS` e slugs de times;
- resource policies e lifecycle policies de ECR;
- `external_destination`, owners e escalonamento em `health.json`.

Nenhum ID corporativo real deve entrar em documentação versionada de LAB;
nenhum ID de LAB deve ser tratado como corporativo. Placeholders neutros
(`<corporate-account-id>`, `<corporate-role>`, `<corporate-ca>`) são a forma
correta até que o valor seja fornecido e revisado no destino.

## Adaptação para monorepo

No LAB a fábrica ocupa três repositórios (`alric-containers-image-base`,
`alric-containers-registry`, `alric-containers-reusable-workflows`). No
corporativo a implementação **pode** usar um único repositório sem perder os
boundaries arquiteturais. Estrutura conceitual, não prescritiva:

```text
containers-image-factory/
├── infra/
│   ├── ecr/            # Terraform: repositórios, mutabilidade, lifecycle, resource policy
│   └── iam/            # bootstrap da role Infra, trust, policies corporate-like
├── factory/
│   ├── frameworks/     # catálogo declarativo (um YAML por runtime/variante)
│   ├── distroless/     # base comum
│   └── melange/        # pacote de CAs, chave Wolfi e pin
├── scripts/            # domínios Python: catalog, artifacts, runtime, release, operations, governance
├── policies/           # health, quarentena, signing-identities, origem de workflows
├── tests/              # unit / integration / runtime (contratos)
├── docs/               # arquitetura, ADRs, contratos, runbooks
└── .github/workflows/  # CI, build, trust, promote, recover, health, terraform-plan/apply
```

O que o monorepo **não** muda:

```text
repository boundary != security/ownership boundary
```

- **Infra job → Infra role.** Terraform plan/apply continua com apply
  human-approved, `terraform-apply.yml` separado de `terraform-pr.yml`, e a
  role Infra sem `ecr:DeleteRepository`/`DeleteLifecyclePolicy` permanentes.
- **Build/publish job → Containers role.** O publicador continua
  `PREPROVISIONED_ONLY`, sem `CreateRepository`, `PutImageTagMutability`,
  `PutLifecyclePolicy` ou `SetRepositoryPolicy` no código.
- Cada job assume **somente** a role da sua responsabilidade; um único
  repositório não justifica uma única role.
- `CODEOWNERS` por caminho (`infra/**` vs `factory/**`) preserva a revisão por
  competência dentro do mesmo repositório.

```text
Infra provides the destination.
Containers provides the trusted artifact.
```

Adaptações concretas que o monorepo exige (pequenas e localizadas, mas
`CODE_CHANGE_REQUIRED`): a policy de origem dos workflows compartilhados e o
resolvedor (`policies/governance/reusable-workflows.json`,
`scripts/pipeline/governance/workflow_dependencies.py`) hoje exigem uma
origem externa por SHA — com os executores vendorizados como workflows locais
(`uses: ./.github/workflows/...`), essa policy passa a apontar para a origem
local e o lint precisa aceitá-la; os seis adaptadores em `.github/scripts/`
permanecem até o executor consumir o pacote canônico diretamente.

## Portabilidade para ambiente sem clone externo

O ambiente corporativo pode não permitir `git clone` de repositórios externos
à organização. Isso não impede o port: **a arquitetura não depende do
histórico Git do LAB**. Tudo o que executa está em arquivos de configuração,
código Python, workflows e testes que podem ser transportados como conteúdo
revisado.

Transportar prioritariamente:

- `frameworks/`, `distroless/`, `melange/` (receita de CAs, chave pública Wolfi e pin — não a private key, que não é versionada);
- `scripts/` (todos os domínios) e `.github/scripts/` (adaptadores);
- `tests/` inteiro (unit, integration, runtime com os projetos mínimos);
- workflows relevantes de `.github/workflows/` e os dois executores compartilhados;
- `policies/` genéricas (health, quarentena, lote, origem de workflows, propostas IAM corporate-like);
- Terraform do registry (`main.tf`, `locals.tf`, módulo ECR pinado, bootstrap IAM, `drift-remediation/`);
- documentação essencial: RFC-013, ADRs, contratos (consumer, IAM, operacional), arquitetura, este documento.

**Não** transportar:

- `.git`, histórico de commits, branches, tags de LAB;
- credenciais, chaves privadas, tokens, `.tfvars`, `*.tfbackend`;
- `terraform.tfstate*`, `tfplan*`, `.terraform/`;
- artifacts gerados: `reports/`, `sbom-*.spdx.json`, `melange/packages/`, layouts OCI, `.reusable-workflows/`;
- identidades IAM do LAB (trust, roles, policies com ARNs reais);
- configuração específica do sandbox (`health.json` owners/escalation, `signing-identities.json` com IDs do LAB, `CODEOWNERS` com slugs do LAB);
- evidências datadas de runs do LAB como se fossem aceites corporativos.

Cada arquivo copiado passa por revisão corporativa antes de entrar na `main`
de destino, e a `main` importada não pode disparar signing/push antes que as
decisões e os recursos existam (kill switches, Environments protegidos e
`execution_scope` são os mecanismos já existentes para isso).

## Sequência recomendada no corporativo

Cada stage termina com evidence registrada; nenhum stage seguinte começa por
inferência.

### Stage 0 — Repository / bootstrap

- criar o monorepo (ou os repositórios) corporativos;
- `CODEOWNERS` com slugs reais, branch protection com revisão de code owner
  e `enforce_admins` conforme política corporativa;
- workflow permissions mínimas, Actions permitidas, forks/eventos autorizados;
- secrets/variables/Environments (`STABLE_PROMOTION_AUTHORIZED` ausente ou
  `false` até o Stage 4);
- runners com Docker privilegiado e QEMU, egress aprovado.

### Stage 1 — Engine (sem publicar)

Portar Apko, Melange, Wolfi (chave + pin + preflight), modelo de frameworks,
contratos funcionais e Trivy. Nada de AWS ainda.

Golden target: `go1-26` + `go1-26-dev`.

Esperado: build multiarch PASS, Trivy PASS nas duas arquiteturas, contrato
funcional PASS. Corresponde aos estágios C–D do
[pacote de adoção](corporate-adoption.md#4-ordem-de-execução-posterior).

### Stage 2 — Infrastructure

Terraform: ECR (`IMMUTABLE_WITH_EXCLUSION` + `stable`, lifecycle 7d,
scan-on-push), IAM (role Infra e role Containers corporate-like), OIDC trust
com IDs corporativos, resource policies, backend com versioning/locking.
Plan e apply pelo workflow controlado; `terraform plan` → `No changes.`
antes de qualquer publicação.

### Stage 3 — Candidate publication

Preflight `PREPROVISIONED_ONLY` PASS → publicação por digest → read-back
remoto → Cosign → SPDX SBOM → provenance → evidence. Corresponde ao Estágio E
/ [P0-04](../specs/2026-09-15-first-corporate-e2e/spec.md).

### Stage 4 — Release

Soak → `stable` → read-back → verificação como consumidor externo → recovery
para digest anterior → quarentena → `terraform plan` sem drift. Corresponde ao
Estágio F.

### Stage 5 — Catalog expansion

Somente depois de o golden path corporativo passar inteiro. Ampliar o
`execution_scope` por decisão registrada, um grupo de cada vez, com o mesmo
gate por framework. Não ligar as 16 definições de uma vez.

## Corporate Go 1.26 Golden Path

Gate principal antes de qualquer expansão do catálogo. Todos os itens devem
ter evidence própria no ambiente corporativo, não herdada do LAB:

```text
[ ] build PASS
[ ] amd64 PASS
[ ] arm64 PASS
[ ] Trivy PASS (duas arquiteturas, gate não alterado)
[ ] functional contract PASS (runtime + -dev, duas arquiteturas)
[ ] ECR preflight PASS (PREPROVISIONED_ONLY, IMMUTABLE_WITH_EXCLUSION + stable)
[ ] candidate publication PASS (digest preservado)
[ ] remote digest read-back PASS
[ ] Cosign PASS (identidade corporativa do workflow assinante)
[ ] SPDX SBOM PASS (índice + duas plataformas atestados)
[ ] provenance PASS
[ ] consumer verification PASS (verify-image.sh sem checkout, identidade corporativa)
[ ] soak PASS
[ ] stable promotion PASS (read-back observed == candidate, promoted=true)
[ ] stable verification PASS (assinatura/SBOM/provenance sobre stable)
[ ] recovery PASS (digest anterior, sem rebuild, quarentena aplicada)
[ ] Terraform no drift (antes e depois)
```

Este é o mesmo checklist que o LAB fechou para o par Go em
[v1-reference-closure](v1-reference-closure-2026-09-16.md) e na
[evidence ADR-0005](../specs/2026-09-16-stable-lifecycle-rfc013/evidence.md);
a diferença é o ambiente, não o critério.

## Itens que só podem ser validados no ambiente corporativo

Não são defects da solução. São **ENVIRONMENT INTEGRATION GATES**: o LAB não
tem como prová-los, e nenhuma evidence de LAB os substitui.

| Gate | O que precisa ser provado no destino |
| --- | --- |
| Corporate CA / PKI | Manifesto de âncoras real (sem MOCK), stores dos cinco runtimes, TLS positivo e negativo com CA corporativa |
| Rede interna / proxy / egress | Acesso a Wolfi, cgr.dev, quay.io, GitHub, Sigstore, Trivy DB, ECR; trust TLS do host separada da CA na imagem |
| Runner | Docker privilegiado, QEMU, portas locais dos contratos; `amd64` nativo e `arm64` emulado identificados |
| Reachability externa | Se exigido mirror/proxy controlado, política de egress e isolamento Wolfi |
| Trivy DB | Origem/mirror aprovados, DB atual e utilizável; verdict registrado com contexto da DB |
| Sigstore / Rekor / Fulcio | Reachability e decisão do ADR-0002 (metadados públicos, alternativa, raízes) |
| OIDC claims reais | `sub`/`aud`/`iss` emitidos pelo destino, por rota (dispatch direto e reusável) |
| IAM real | Trust e identity policies efetivas, session policy/boundary/SCP; negativos reais por rota e recurso |
| AWS account boundaries | Conta única vs cross-account; o que muda na avaliação de policy |
| ECR resource policies | Org IDs corporativos, principals consumidores, negativo fora do escopo |
| Registry connectivity | Login, push, pull, `describe-images`, lifecycle preview |
| Repositórios de artifacts internos | Se as ferramentas/pins precisarem vir de origem interna |
| Terraform backend | Bucket, versioning, locking, permissões da role Infra |
| Branch / Environment protection | Revisão de code owner exigida, `enforce_admins`, apply human-approved |
| Permissões das contas consumidoras | Pull no escopo permitido, acesso a attestations no GitHub |

## Não reabrir POCs encerrados

O port corporativo **não** começa reabrindo:

- Alpine / multi-source como package source — tecnicamente provado, adoção
  recusada ([ADR-0007](adr/0007-multi-source-alpine-recusado.md));
- `dotnet8` — removido do catálogo por fim de suporte ([ADR-0001](adr/0001-dotnet8-fora-do-lote-padrao.md), adendo);
- pacote `zlib` próprio — desnecessário, resolvido upstream ([ADR-0006](adr/0006-java21-zlib-blocker-remediation-options.md), addendum);
- mudanças de scanner, severidade ou `--ignore-unfixed`;
- redesign da fábrica (build once, preprovisioned-only, `stable` por soak).

Essas investigações já tiveram conclusão registrada. O modelo ativo é o
estado atual de `main`. Se surgir uma necessidade corporativa real, abre-se
uma decisão separada (ADR), com owner e critério — não se reabre a anterior.

## Migração não é cópia 1:1

| | Papel |
| --- | --- |
| **LAB** | Reference implementation. Prova que a arquitetura funciona de ponta a ponta contra infraestrutura real |
| **CORPORATE** | Port + configuration + integration + validation. Os mesmos contratos e mecanismos, executados contra as dependências reais, com os aceites registrados por quem tem competência |

Linguagem correta: **"portar contratos e mecanismos"**. Não: "copiar e rodar".

## Conclusão

A hardened-image factory está pronta para ser levada ao ambiente corporativo
**como implementação de referência comprovada**. Não é necessário reiniciar
arquitetura, refazer POC ou reavaliar a stack.

O trabalho corporativo é:

1. portar (conteúdo revisado, sem histórico nem valores de LAB);
2. adaptar configuração (identidades, PKI, rede, runners, backend);
3. integrar (IAM/OIDC, ECR, Sigstore/scanner conforme decisões);
4. executar o golden path Go 1.26 inteiro;
5. validar os controles no ambiente real e registrar os aceites CA-xx;
6. expandir o catálogo progressivamente.

O que **não** se afirma aqui: que a produção corporativa já está validada. A
validação do destino ainda precisa acontecer no ambiente corporativo, pelas
mãos dos owners corporativos, com evidence própria.

## Status

```text
REFERENCE_ARCHITECTURE            = READY
IMAGE_FACTORY_ENGINE              = READY
SECURITY_MODEL                    = READY
SUPPLY_CHAIN_MODEL                = READY
RELEASE_MODEL                     = READY

ACTIVE_CATALOG                    = 16
REGISTRY_CATALOG                  = 16
AWS_ECR_COUNT                     = 16
ACTIVE_PACKAGE_SOURCE             = WOLFI
MULTI_SOURCE_ACTIVE               = NO
LAB_GOLDEN_PATH_GO_1_26           = CLOSED
UPSTREAM_BLOCKERS_OPEN            = 0

CORPORATE_PORT                    = NOT_STARTED
CORPORATE_ENVIRONMENT_VALIDATION  = PENDING
CORPORATE_GOLDEN_PATH             = PENDING
CORPORATE_EXTERNAL_DECISIONS      = PENDING (Sigstore, scanner, CA, IAM/OIDC, alert destination, SLA)

NEXT_STEP =
PORT TO CORPORATE MONOREPO AND PROVE GO 1.26 GOLDEN PATH
```
