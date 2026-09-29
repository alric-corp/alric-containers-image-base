Factory Distroless — Fluxo de DEV → HOM com promoção automática
Objetivo
Definir um fluxo de entrega das imagens base corporativas com baixo toil, sem utilizar branches Git para representar ambientes.
A proposta mantém:
develop como branch default e fonte oficial do código da Factory;
uma conta AWS DEV para build, validação interna e stable do time de Containers Products;
uma conta AWS HOM para disponibilização das imagens aos consumidores;
stable nas duas contas;
promoção automatizada entre DEV e HOM;
promoção do mesmo artifact, sem rebuild;
Pull Requests apenas para mudanças de código/configuração da Factory.
1. Princípio principal
Branch Git, ambiente AWS e estado de uma imagem são conceitos diferentes.
Git branch
→ controla o código da Factory

GitHub Environment
→ controla boundary de execução, secrets e OIDC

AWS Account
→ representa o ambiente de infraestrutura

Candidate / stable
→ representam estados do artifact
Portanto, não é necessário manter:
develop → DEV
staging → HOM
main → PROD
como um acoplamento obrigatório entre branches e ambientes.
A recomendação é manter:
develop
como branch default e usar os workflows do GitHub Actions para controlar o lifecycle das imagens.
2. Arquitetura proposta
flowchart TD
    GIT["GitHub<br/>develop (default)"] --> BUILD["Build da Factory"]
    BUILD --> DEV_CAND["AWS DEV<br/>Candidate imutável"]
    DEV_CAND --> VALID["Validações<br/>Trivy / Trust / Runtime / Multiarch<br/>SBOM / Provenance / Consumer tests"]
    VALID --> DEV_STABLE["AWS DEV<br/>:stable"]
    DEV_STABLE --> SOAK["Soak / elegibilidade"]
    SOAK --> PROMOTE["Promotion Workflow<br/>mesmo artifact<br/>sem rebuild"]
    PROMOTE --> HOM_COPY["AWS HOM<br/>Artifact promovido"]
    HOM_COPY --> VERIFY["Read-back / Digest equality / Trust"]
    VERIFY --> HOM_STABLE["AWS HOM<br/>:stable"]
    HOM_STABLE --> USERS["Squads consumidoras"]
3. Papel da branch develop
A branch:
develop
permanece como:
fonte oficial do código atual da Factory.
Ela não precisa significar "ambiente DEV".
Exemplo:
feature/*
    │
    ▼
Pull Request
    │
    ▼
develop
    │
    ▼
GitHub Actions
Mudanças que continuam exigindo Pull Request:
alteração de workflow;
alteração de Apko;
alteração de Melange;
alteração de Terraform;
mudança de política Trivy;
mudança de catálogo;
inclusão de framework;
inclusão de nova versão;
mudança de certificados;
mudança da lógica de promoção;
mudança da lógica de recovery.
4. O que não precisa de Pull Request
O lifecycle normal de uma imagem não deve depender de PR.
Novo build automático        → não
Novo candidate               → não
Candidate aprovado           → não
DEV :stable atualizado       → não
Promoção DEV → HOM           → não
HOM :stable atualizado       → não
Recovery de uma release      → não
Pull Request protege mudanças na Factory.
GitHub Actions controla mudanças de estado dos artifacts.
Essa separação reduz toil.
5. Estados da imagem
O fluxo pode ser modelado em quatro estados principais:
1. CANDIDATE
      ↓
2. DEV STABLE
      ↓
3. ELIGIBLE FOR HOM
      ↓
4. HOM STABLE
5.1 Candidate
Imagem recém-construída na conta DEV.
Características:
tag de build imutável;
digest conhecido;
ainda está em validação;
não representa release disponível aos consumidores.
5.2 DEV :stable
Imagem aprovada internamente pelo Containers Products.
Exemplo:
<AWS_ACCOUNT_DEV>.dkr.ecr.<REGION>.amazonaws.com/image-base-go1-26:stable
Essa referência é usada pelo próprio time para:
validação interna;
soak;
testes complementares;
evidência operacional;
preparação para promoção.
5.3 Eligible for HOM
A release já passou pelos gates necessários e está apta a ser promovida.
candidate
    ↓
validações
    ↓
DEV stable
    ↓
soak
    ↓
eligible
5.4 HOM :stable
Imagem liberada para consumo pelas squads.
Exemplo:
<AWS_ACCOUNT_HOM>.dkr.ecr.<REGION>.amazonaws.com/image-base-go1-26:stable
Para o consumidor final, esse é o contrato principal.
6. Duas tags stable
É esperado existir stable nas duas contas.
AWS DEV
└── image-base-go1-26:stable
    → release aprovada internamente

AWS HOM
└── image-base-go1-26:stable
    → release aprovada para consumo
Isso não gera conflito porque o registry/conta faz parte da referência completa.
Exemplo:
111111111111.dkr.ecr.sa-east-1.amazonaws.com/image-base-go1-26:stable
└──────────────────────── DEV ──────────────────────────┘

222222222222.dkr.ecr.sa-east-1.amazonaws.com/image-base-go1-26:stable
└──────────────────────── HOM ──────────────────────────┘
7. DEV e HOM podem apontar para releases diferentes
Isso é esperado.
Exemplo:
DEV :stable
→ sha256:BBB

HOM :stable
→ sha256:AAA
Interpretação:
DEV
→ já está validando a próxima release

HOM
→ continua servindo a última release aprovada aos consumidores
Portanto:
DEV:stable e HOM:stable não precisam apontar para o mesmo digest o tempo todo.
8. Promoção deve usar identidade explícita
A promoção não deve simplesmente consultar:
DEV :stable
no momento da execução.
Isso pode criar race condition.
Exemplo:
10:00 Candidate A passa nos testes
10:05 Candidate A entra em soak

11:00 Candidate B é construído
11:30 DEV :stable passa a apontar para B

16:05 Candidate A completa o soak
Se a promoção consultar apenas:
DEV :stable
ela pode promover B por engano.
9. Release Manifest
A promoção deve carregar a identidade exata da release desde o build.
Exemplo conceitual:
release:
  run_id: 123456
  attempt: 1
  source_sha: abcdef123456

images:
  go1-26:
    digest: sha256:AAAAAAAA

  go1-26-dev:
    digest: sha256:BBBBBBBB

  java21:
    digest: sha256:CCCCCCCC

  java21-dev:
    digest: sha256:DDDDDDDD
A promoção então usa:
release específica
+
digest específico
e não:
latest
ou:
o que estiver em DEV:stable
10. Build once, promote the same artifact
Essa deve continuar sendo uma regra central:
O artifact validado em DEV deve ser exatamente o artifact promovido para HOM.
Não fazer:
Build DEV
   ↓
Testes
   ↓
Rebuild HOM   ❌
Porque:
artifact testado
!=
artifact entregue
O correto:
Build
   ↓
Artifact A
sha256:ABC
   ↓
Validação DEV
   ↓
Promoção
   ↓
Artifact A em HOM
sha256:ABC
Gate esperado:
SOURCE_DIGEST == TARGET_DIGEST
11. Fluxo completo
flowchart TD
    START["Schedule / workflow_dispatch"] --> BUILD["Build"]
    BUILD --> CAND["DEV Candidate"]

    CAND --> SCAN["Trivy"]
    CAND --> MULTI["Multiarch"]
    CAND --> RUNTIME["Runtime Contract"]
    CAND --> TRUST["Image Trust"]
    CAND --> SBOM["SBOM"]
    CAND --> PROV["Provenance"]
    CAND --> APPTEST["Consumer Tests"]

    SCAN --> GATE["Global validation gate"]
    MULTI --> GATE
    RUNTIME --> GATE
    TRUST --> GATE
    SBOM --> GATE
    PROV --> GATE
    APPTEST --> GATE

    GATE --> DEVSTABLE["DEV :stable"]
    DEVSTABLE --> SOAK["Soak"]
    SOAK --> ELIGIBLE["Eligible for HOM"]
    ELIGIBLE --> PROMOTE["Cross-account promotion<br/>by exact digest"]
    PROMOTE --> HOMART["HOM artifact"]
    HOMART --> READBACK["Read-back"]
    READBACK --> EQUALITY["Digest equality"]
    EQUALITY --> HOMTRUST["Trust verification"]
    HOMTRUST --> HOMSTABLE["HOM :stable"]
    HOMSTABLE --> USER["Consumers"]
12. GitHub Environments
Mesmo com uma única branch principal, DEV e HOM devem continuar separados como GitHub Environments.
develop
   │
   ├── GitHub Environment: DEV
   │      └── OIDC → AWS DEV Role
   │
   └── GitHub Environment: HOM
          └── OIDC → AWS HOM Role
Exemplo conceitual:
jobs:
  build:
    environment: DEV

  promote:
    environment: HOM
Benefícios:
identities separadas;
secrets/variables separados;
policies separadas;
OIDC separado;
auditabilidade;
possibilidade de approval gates quando necessário.
13. Separação de responsabilidades dos workflows
Build workflow
Responsável por:
build
→ publish candidate DEV
→ scan
→ trust
→ runtime tests
→ multiarch
→ SBOM
→ provenance
→ consumer tests
DEV stable workflow
Responsável por:
candidate aprovado
→ pre-write checks
→ DEV :stable
→ read-back
Promotion workflow
Responsável por:
release elegível
→ assume role HOM
→ copia/promove artifact exato
→ read-back
→ digest equality
→ trust verification
→ HOM :stable
Recovery workflow
Responsável por:
release anterior
→ validar artifact/evidências
→ atualizar HOM :stable
Sem rebuild.
14. Atomicidade da promoção
Antes de atualizar stable, deve existir uma barreira de validação.
Resolve release
      ↓
Verifica artifacts
      ↓
Verifica evidências
      ↓
Verifica soak
      ↓
Verifica autorização
      ↓
Promove artifacts
      ↓
Read-back
      ↓
Trust / digest equality
      ↓
PASS?
  │
  ├── NO → não atualizar stable
  │
  └── YES
        ↓
      stable
A granularidade pode ser:
catálogo completo; ou
framework/pair.
Exemplo de pair:
go1-26-dev
+
go1-26
Se o contrato define os dois como uma unidade, ambos devem ser promovidos de forma coerente.
15. ECR
Nas duas contas, manter preferencialmente:
IMMUTABLE_WITH_EXCLUSION
com exceção apenas para:
stable
Modelo:
candidate tags
→ imutáveis

stable
→ mutável
Isso mantém:
rastreabilidade;
histórico;
segurança contra overwrite acidental;
recovery;
facilidade de consumo.
16. Recovery sem PR e sem rebuild
Exemplo:
HOM :stable
→ sha256:BBB
Uma falha é identificada.
Release anterior:
sha256:AAA
O recovery executa:
workflow_dispatch
      ↓
release anterior
      ↓
verifica artifact
      ↓
verifica trust
      ↓
verifica SBOM/provenance
      ↓
HOM :stable → sha256:AAA
Não é necessário:
git revert
Pull Request
merge
rebuild
Porque recovery altera o estado da release, não o código da Factory.
17. Experiência do consumidor
Toda a complexidade da Factory fica interna.
O consumidor recebe somente:
Conta AWS HOM
+
framework/version
+
:stable
Exemplo:
FROM <AWS_ACCOUNT_ID_HOM>.dkr.ecr.sa-east-1.amazonaws.com/image-base-java21:stable
Para uma linguagem que utiliza -dev:
FROM <AWS_ACCOUNT_ID_HOM>.dkr.ecr.sa-east-1.amazonaws.com/image-base-java21-dev:stable AS build

# build da aplicação

FROM <AWS_ACCOUNT_ID_HOM>.dkr.ecr.sa-east-1.amazonaws.com/image-base-java21:stable

# aplicação
O consumidor não precisa conhecer:
candidate;
run ID;
attempt;
source SHA;
digest interno da promoção;
branch de release;
mecanismo de soak;
lógica de promotion;
detalhes da Factory.
18. Atualização de stable
Mover stable não atualiza containers ou imagens de aplicação já construídas.
Nova correção / atualização
        ↓
Nova base
        ↓
DEV validation
        ↓
DEV stable
        ↓
Promotion
        ↓
HOM stable
        ↓
Novo build da aplicação
        ↓
Aplicação passa a consumir nova base
Portanto:
uma nova stable só é incorporada pela aplicação após um novo build consumidor.
19. Evolução futura para PROD
O modelo permite adicionar PROD sem mudar a arquitetura.
Hoje:
DEV
 ↓
HOM
Futuro:
DEV
 ↓
HOM
 ↓
PROD
Sempre promovendo o mesmo artifact:
Artifact A
sha256:ABC

DEV  → ABC
HOM  → ABC
PROD → ABC
Sem rebuild entre os ambientes.
20. Modelo final
flowchart LR
    DEVBR["GitHub<br/>develop"] --> FACTORY["Factory Workflows"]
    FACTORY --> DEV["AWS DEV"]
    DEV --> C["Candidates"]
    DEV --> DS["DEV :stable"]
    DS --> P["Promotion<br/>exact digest"]
    P --> HOM["AWS HOM"]
    HOM --> HS["HOM :stable"]
    HS --> CONSUMERS["Consumers"]
Resumo:
BRANCH
= código da Factory

DEV
= build + validação interna

DEV :stable
= release aprovada internamente

PROMOTION
= movimentação do mesmo artifact

HOM
= ambiente de consumo

HOM :stable
= release aprovada para os usuários
21. Decisão recomendada
Manter:
develop
como branch default.
Não utilizar:
staging
como mecanismo obrigatório de promoção para HOM.
Não criar:
stable
como branch.
Utilizar stable exclusivamente como tag/estado das imagens dentro de cada ambiente:
AWS DEV → :stable
AWS HOM → :stable
Com isso:
Pull Requests protegem mudanças na Factory; workflows governam o lifecycle e a promoção das imagens.
O resultado é um fluxo mais automatizado, auditável e com menor toil operacional.