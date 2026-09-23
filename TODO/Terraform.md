Terraform PLAN, APPLY e BUILD — Contrato esperado no DEV
Objetivo
Este documento descreve como esperamos que funcionem os três estágios principais da ativação DEV do itau-xj7-container-image-base:
Terraform PLAN — calcular e revisar mudanças de infraestrutura;
Terraform APPLY — aplicar somente a mudança autorizada e comprovar o estado final;
BUILD — produzir, validar e publicar o primeiro candidate da Factory Distroless usando a infraestrutura já provisionada.
A ordem esperada é:
PLAN
  ↓
REVISÃO / APROVAÇÃO
  ↓
APPLY
  ↓
READ-BACK DA INFRA
  ↓
BUILD DO CANDIDATE
  ↓
VERIFICAÇÃO REMOTA
  ↓
SOAK
  ↓
PROMOTE STABLE
BUILD não cria nem corrige infraestrutura. Infra é responsabilidade do Terraform; a Factory apenas valida e consome recursos previamente provisionados.
1. Separação de responsabilidades
Terraform
├── backend/state
├── ECR
├── lifecycle
├── repository policies
├── tag mutability / stable exclusion
└── recursos IAM pertencentes ao modelo aprovado

Factory Distroless
├── build da imagem
├── validação
├── scan
├── contratos funcionais
├── publicação
├── assinatura
├── SBOM
├── provenance
└── promoção de stable
No modelo corporativo atual:
branch = develop
environment = DEV
A conta, região, roles, GitHub Environment e runners devem vir de configuração corporativa autorizada, sem hardcode de valores ambientais no produto.
2. Terraform Model 2
O modelo esperado é:
infra/ecr/
→ recursos do produto

pipeline corporativo / UP2
→ backend
→ provider
→ autenticação
→ parâmetros ambientais
Portanto, infra/ecr/ permanece resources-only quando esse for o contrato vigente.
Não reintroduzir do LAB:
backend hardcoded;
provider ambiental hardcoded;
lab.tfvars;
state local versionado;
account/region fixos.
3. Terraform PLAN
3.1 Pergunta que o PLAN responde
Se aplicarmos a configuração versionada neste commit ao DEV atual, o que exatamente mudará?
O PLAN é uma etapa de inspeção/revisão. Ele não deve mutar infraestrutura.
3.2 Pré-condições
Antes do PLAN:
branch/ref esperada = develop
ambiente = DEV
runner = ARC/EKS aprovado
autenticação = OIDC/federação corporativa
backend = backend DEV correto
state = state DEV correto
conta/região = resolvidas pela configuração corporativa
Se ambiente, state, conta ou região não forem comprovados:
FAIL CLOSED
3.3 Fluxo esperado
flowchart TD
    A[develop] --> B[Runner ARC/EKS]
    B --> C[Autenticação corporativa]
    C --> D[Resolver backend/state DEV]
    D --> E[Terraform init]
    E --> F[Terraform validate]
    F --> G[Terraform plan]
    G --> H[Preservar plano e resumo]
    H --> I[Revisão / aprovação]
3.4 terraform plan -detailed-exitcode
Semântica esperada:
0
→ plano calculado com sucesso
→ nenhuma mudança necessária

1
→ erro ao calcular o plano
→ BLOQUEAR

2
→ plano calculado com sucesso
→ existem mudanças
→ REVISAR
Exit code 2 não é falha.
Ele significa que existe uma mudança concreta que precisa ser compreendida e, quando aplicável, aprovada.
3.5 O que revisar no plano
Para ECR, revisar principalmente:
quantidade de repositórios;
nomes esperados;
criação/alteração/remoção;
force_delete;
criptografia;
scanning configurado;
tag mutability;
exclusão específica de stable;
lifecycle;
repository policies;
qualquer replacement inesperado.
Não aprovar automaticamente:
destroy
replace
recreate
sem entender a causa.
3.6 O PLAN nunca deve
criar recursos;
mover stable;
publicar imagens;
alterar state manualmente;
corrigir drift automaticamente;
executar terraform apply;
criar permissões adicionais fora do modelo aprovado.
3.7 Evidência esperada
Registrar, quando permitido:
commit SHA
branch
environment
Terraform version
backend/state lógico
resultado do validate
exit code do plan
resumo create/change/destroy
artifact do plano
run ID / run attempt
Nunca persistir secrets.
4. Revisão entre PLAN e APPLY
Antes do APPLY:
PLAN = revisado
commit = o mesmo aprovado
ambiente = DEV
state/backend = os mesmos
escopo = esperado
destruições = compreendidas
replacements = compreendidos
aprovação = presente quando exigida
O contrato preferencial é:
PLAN APROVADO
        ↓
EXACT PLAN
        ↓
APPLY
Quando a plataforma permitir, preferir aplicar o plano binário previamente revisado em vez de recalcular silenciosamente um plano diferente.
5. Terraform APPLY
5.1 Pergunta que o APPLY responde
A infraestrutura DEV ficou exatamente no estado autorizado?
5.2 Fluxo esperado
flowchart TD
    A[Plano aprovado] --> B[Runner ARC/EKS]
    B --> C[Autenticação corporativa]
    C --> D[Backend/state DEV]
    D --> E[Terraform apply]
    E --> F{Apply terminou?}
    F -->|Sim| G[Read-back AWS]
    F -->|Não| H[Preservar erro]
    H --> I[Re-plan / reconciliação]
    G --> J[Comparar estado real com contrato]
    J --> K[Infra DEV READY]
5.3 Mesmo contexto do PLAN
O APPLY deve estar vinculado ao mesmo:
repositório
commit/revisão
ambiente
conta
região
backend
state
configuração Terraform
Mudanças que alterem o resultado esperado exigem novo PLAN e nova revisão.
5.4 APPLY parcial
Terraform não oferece rollback transacional completo.
Pode ocorrer:
resource A = criado
resource B = criado
resource C = falhou
Então:
APPLY = FAILED
não significa:
NADA MUDOU
Procedimento esperado:
1. preservar logs/evidência;
2. não fazer retry cego;
3. consultar state;
4. consultar recursos reais;
5. executar novo PLAN;
6. entender o delta remanescente;
7. corrigir a causa;
8. somente então executar novo APPLY autorizado.
6. Read-back pós-APPLY
terraform apply com sucesso não é a única evidência.
Depois do APPLY, fazer leitura independente do ambiente.
Para ECR:
repositórios esperados existem
nomes corretos
região correta
mutabilidade correta
exclusão de stable correta
lifecycle correto
policies corretas
criptografia correta
nenhum recurso inesperado
Contrato:
Terraform diz que aplicou
        +
AWS confirma o estado
        =
INFRA READY
7. Critério dos marcos de Infra
M05 — PLAN
Pode ser concluído quando houver evidência de:
backend/state corretos
autenticação correta
plan calculado
mudanças compreendidas
nenhuma surpresa não explicada
aprovação registrada quando necessária
M06 — APPLY
Pode ser concluído quando:
apply autorizado executado
+
read-back AWS aprovado
+
novo plan converge ao estado esperado
Quando a convergência esperada for total:
terraform plan -detailed-exitcode
→ 0
após o APPLY.
8. BUILD — pré-condições
O BUILD só começa quando a infraestrutura necessária estiver pronta.
Pré-condições:
ECR DEV provisionado
configuração ECR verificada
OIDC/publication role funcionando
GitHub Environment DEV configurado
runners ARC/EKS corretos
reusable workflows pinados por SHA imutável
certificados/trust prontos
branch/ref correta
Se o ECR necessário não existir ou estiver incorreto:
BUILD/PUBLISH = FAIL CLOSED
O publisher não deve criar ou reparar o repositório.
9. BUILD — objetivo
O BUILD produz um candidate imutável.
Não produz stable.
Fluxo:
source/config
   ↓
Melange
   ↓
Apko
   ↓
OCI multiarch
   ↓
Trivy
   ↓
Image Trust
   ↓
Runtime Contract
   ↓
Publication Gate
   ↓
ECR candidate
   ↓
read-back
   ↓
Cosign
   ↓
SPDX SBOM
   ↓
Provenance
10. BUILD ONCE
Propriedade central:
BUILD ONCE
Nunca:
build
→ scan
→ rebuild
→ publish
Esperado:
build OCI
→ validar OCI
→ escanear OCI
→ testar OCI
→ publicar o MESMO OCI
Assim:
digest validado
==
digest publicado
11. Melange
Melange produz os pacotes customizados necessários à composição da imagem, inclusive o fluxo de certificados quando aplicável.
No ARC, precisamos comprovar o build real:
Melange version = PASS
keygen = PASS
Build CA package amd64 = PASS
Build CA package arm64 = PASS
melange version e keygen sozinhos não comprovam que o build completo funciona.
Se o build exige execução privilegiada, a capacidade privileged do scale-set precisa ser autorizada/provada pela plataforma.
Não contornar controles do cluster para obter PASS.
12. Apko
Apko compõe o OCI:
framework definition
+
distroless definition
+
Wolfi packages
+
Melange repository/package
        ↓
OCI Image Index
├── linux/amd64
└── linux/arm64
13. Multiarch
O BUILD precisa produzir e validar:
linux/amd64
linux/arm64
Não basta confirmar que o manifest ARM64 existe.
Os contratos aplicáveis devem realmente executar as plataformas, nativamente ou por emulação.
Registrar:
native
ou
emulated
Nunca chamar QEMU de execução nativa.
14. Trivy
O candidate deve ser escaneado antes da publicação.
Falha bloqueante:
framework afetado
→ não publica
A política de severidade e tratamento de CVEs deve permanecer versionada.
15. Image Trust
Trust/certificados precisam ser testados antes da publicação.
O gate deve provar comportamento real do runtime, não apenas presença de arquivos.
16. Runtime Contract
Para compilados:
-dev candidate
→ compila projeto mínimo
→ runtime candidate
→ executa aplicação
Para interpretados:
runtime candidate
→ executa probe real
O contrato deve provar conforme o framework:
versão;
UID/GID;
filesystem read-only;
áreas graváveis explícitas;
CA bundle;
TLS positivo;
TLS negativo;
toolchain na -dev;
amd64;
arm64.
17. Publication Gate
Antes da publicação, exigir evidência coerente.
Para pares compilados:
runtime A + dev A
→ permitido

runtime A + dev B
→ bloqueado
Vincular a:
run ID
run attempt
source SHA
index digest
platform digests
functional evidence
trust evidence
18. Publicação no ECR
O publisher usa o ECR previamente provisionado pelo Terraform.
Fluxo:
validar ECR
→ autenticar
→ publicar OCI preservando digest
→ ler de volta
→ comparar
Invariante:
validated digest
==
copied digest
==
remote digest
19. Candidate
O BUILD publica tag imutável, por exemplo:
<timestamp>-r<run_id>-a<attempt>
A identidade exata é:
repository@sha256:<digest>
20. Supply chain
Após publicação:
Cosign
→ assinatura / identidade

SPDX
→ conteúdo do artifact

Provenance
→ origem/processo de build
Tudo deve estar vinculado ao digest publicado.
21. BUILD não cria stable
Após o BUILD:
candidate = existe
stable = não necessariamente
stable pertence ao fluxo de promoção.
22. Soak e promoção
candidate
→ soak
→ fresh verification
→ promotion authorization
→ stable
O BUILD não deve reduzir ou contornar soak.
23. Fluxo integrado
flowchart TD
    A[develop] --> B[Terraform PLAN]
    B --> C{Mudanças revisadas?}
    C -->|Não| X[STOP]
    C -->|Sim| D[Terraform APPLY autorizado]
    D --> E[Read-back AWS]
    E --> F{Infra DEV correta?}
    F -->|Não| Y[Reconciliação]
    F -->|Sim| G[BUILD candidate]
    G --> H[Melange + Apko]
    H --> I[amd64 + arm64]
    I --> J[Trivy]
    J --> K[Trust]
    K --> L[Runtime Contract]
    L --> M[Publication Gate]
    M --> N[ECR candidate]
    N --> O[Remote read-back]
    O --> P[Cosign + SBOM + Provenance]
    P --> Q[Candidate DEV aprovado]
    Q --> R[Soak]
    R --> S[Promote stable]
24. Matriz de mutação
Estágio
Infra AWS
ECR image
stable
PLAN
Não
Não
Não
APPLY
Sim
Não
Não
BUILD/Validate
Não
Não
Não
BUILD/Publish
Não cria infra
Sim, candidate
Não
Promote
Não
Retag/referência
Sim
Recovery
Não
Retag/referência existente
Sim
25. Falhas e resposta esperada
PLAN falha
não aplicar
→ corrigir causa
→ gerar novo plano
APPLY falha
não assumir rollback
→ read-back
→ state
→ novo PLAN
→ reconciliar
BUILD falha antes da publicação
nenhuma publicação daquele framework
Publicação/read-back diverge
FAIL CLOSED
Trust/Trivy/runtime falham
candidate não autorizado
26. Critério do primeiro candidate DEV
INFRA_READY = YES

ARC_BUILD_CAPABILITY = PASS
OIDC_PUBLISHER = PASS
CERTIFICATE_TRUST = PASS

MULTIARCH = PASS
TRIVY = PASS
IMAGE_TRUST = PASS
RUNTIME_CONTRACT = PASS
PUBLICATION_GATE = PASS

ECR_PUBLICATION = PASS
REMOTE_READBACK = PASS

COSIGN = PASS
SPDX = PASS
PROVENANCE = PASS

TERRAFORM_DRIFT_AFTER_BUILD = NONE
27. Critério do primeiro stable DEV
candidate válido
+
soak concluído
+
fresh verification
+
promotion authorization
+
stable write
+
stable read-back
=
STABLE DEV
28. Sequência de marcos
M05
→ revisar PLAN de infraestrutura DEV

M06
→ executar APPLY autorizado + read-back

M07
→ fechar certificados/trust corporativo

M08
→ publicar primeiro candidate Go DEV

M09
→ promover/verificar primeiro stable DEV

M10
→ operação agendada/health

M11
→ catálogo completo

M12
→ consumer apps amd64 + arm64

M13
→ recovery + aceite
29. Regra resumida
PLAN
= "o que mudaria?"

APPLY
= "aplique exatamente o que foi autorizado e prove o estado final"

BUILD
= "use a infra pronta, construa uma vez, valide o artifact real e publique o mesmo digest"

PROMOTE
= "mova stable para um candidate aprovado; nunca rebuild"
30. Invariantes
PLAN IS READ-ONLY

APPLY DOES NOT BUILD IMAGES

BUILD DOES NOT PROVISION INFRA

BUILD DOES NOT CREATE STABLE

VALIDATED DIGEST == PUBLISHED DIGEST

RUNTIME/DEV PAIRS STAY BOUND

STABLE MOVES WITHOUT REBUILD

RECOVERY USES EXISTING DIGESTS