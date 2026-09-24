Wolfi no Artifactory — Mirror/Proxy corporativo para pacotes APK
Objetivo
Disponibilizar os pacotes Wolfi internamente para a Factory Distroless, reduzindo a dependência direta dos runners ARC/EKS em relação ao upstream público:
https://packages.wolfi.dev/os
A recomendação principal é:
Criar um Remote Repository do tipo Alpine/APK no Artifactory e consumi-lo através de um Virtual Repository.
Quando o Artifactory oferece suporte nativo a Alpine, não usar Generic como primeira opção.
1. Arquitetura recomendada
packages.wolfi.dev/os
        │
        ▼
Artifactory Remote
Package Type: Alpine
Repository Key: wolfi-remote
        │
        ▼
Artifactory Virtual
Package Type: Alpine
Repository Key: wolfi-virtual
        │
        ▼
ARC / EKS
   ├── Apko
   └── Melange
A Factory deve consumir o Virtual Repository, não o remote diretamente.
2. Por que Alpine e não Generic?
Wolfi distribui pacotes no formato APK.
Generic
Um Remote Repository do tipo Generic atua essencialmente como proxy/cache de arquivos.
Pode funcionar para alguns cenários HTTP, mas perde semântica e recursos específicos do ecossistema APK/Alpine.
Alpine
Quando disponível, é a opção preferida:
Repository Type: Remote
Package Type: Alpine
Benefícios esperados:
entendimento nativo do formato APK;
tratamento adequado de metadata/index;
Virtual Repositories do mesmo package type;
melhor integração com clientes APK;
governança e observabilidade;
integração com políticas/Xray quando disponível;
possibilidade de gerenciamento de trust/chaves conforme o desenho corporativo.
3. Remote Repository sugerido
Criar:
Repository Type: Remote
Package Type: Alpine
Repository Key: wolfi-remote
Remote URL:
https://packages.wolfi.dev/os
Recomendações:
manter validação TLS;
não utilizar --insecure;
não desabilitar verificação de certificado;
não versionar credenciais;
habilitar cache conforme padrão corporativo;
restringir acesso ao repositório aos consumidores necessários;
habilitar Xray se estiver disponível e fizer parte da política interna.
4. Virtual Repository sugerido
Criar:
Repository Type: Virtual
Package Type: Alpine
Repository Key: wolfi-virtual
Inicialmente:
Members:
- wolfi-remote
Futuramente, se necessário:
wolfi-virtual
├── wolfi-remote
└── corporate-apk-local
A vantagem é manter uma única URL estável para a Factory.
5. Fluxo de resolução
flowchart LR
    A[Apko / Melange] --> B[wolfi-virtual]
    B --> C[wolfi-remote]
    C --> D[packages.wolfi.dev/os]
    C --> E[Cache Artifactory]
    E --> B
Primeira resolução:
Apko/Melange
→ Artifactory
→ Wolfi upstream
→ cache
→ runner
Resoluções posteriores:
Apko/Melange
→ Artifactory
→ cache interno
6. Arquiteturas que precisam ser validadas
A Factory trabalha com:
linux/amd64
linux/arm64
No ecossistema APK isso normalmente corresponde a:
x86_64
aarch64
Antes de alterar a Factory, confirmar que o mirror entrega metadata e pacotes para ambas.
Exemplo conceitual:
https://<artifactory>/artifactory/wolfi-virtual/x86_64/APKINDEX.tar.gz
https://<artifactory>/artifactory/wolfi-virtual/aarch64/APKINDEX.tar.gz
O caminho exato deve ser validado na instância corporativa do Artifactory.
7. POC recomendada antes da migração
Testar primeiro sem alterar os workflows principais.
Etapa 1 — índice
Validar:
INDEX_X86_64 = PASS
INDEX_AARCH64 = PASS
Etapa 2 — pacotes simples
Testar download de pacotes como:
busybox
ca-certificates
Esperado:
APK_DOWNLOAD = PASS
CACHE = PASS
TLS = PASS
Etapa 3 — Apko mínimo
Criar uma configuração mínima:
contents:
  repositories:
    - https://<artifactory>/artifactory/wolfi-virtual
  packages:
    - busybox
    - ca-certificates

archs:
  - x86_64
  - aarch64
Esperado:
APKO_AMD64 = PASS
APKO_ARM64 = PASS
Etapa 4 — Melange
Executar um build real do pacote utilizado pela Factory apontando para o mirror.
Esperado:
MELANGE_AMD64 = PASS
MELANGE_ARM64 = PASS
8. Integração com a Factory
Evitar hardcode de URL quando possível.
Recomendação:
WOLFI_REPOSITORY_URL
ou configuração governada equivalente.
Exemplo conceitual:
LAB:
https://packages.wolfi.dev/os

CORPORATIVO:
https://<artifactory>/artifactory/wolfi-virtual
A mesma fonte deve ser usada de forma consistente por:
Apko
Melange
Evitar:
Apko → Artifactory
Melange → Internet direta
9. Credenciais do Artifactory
Não colocar credenciais diretamente no YAML:
repositories:
  - https://usuario:senha@artifactory/...
Não versionar:
token;
API key;
password;
access token.
Se o mirror exigir autenticação, utilizar o mecanismo corporativo aprovado, por exemplo:
identidade do runner;
secret do GitHub Environment;
token de curta duração;
configuração externa de cliente;
mecanismo corporativo de federation/auth.
10. Assinatura e trust do APKINDEX
Este ponto precisa de decisão explícita.
Opção A — preservar trust do Wolfi
Wolfi
→ assinatura Wolfi
→ Artifactory proxy/cache
→ Factory continua confiando na Wolfi signing key
É o modelo recomendado para a primeira POC por exigir menos mudanças.
Opção B — trust corporativo
Wolfi
→ Artifactory
→ metadata/index governado
→ assinatura corporativa
→ Factory usa chave corporativa
Se o Artifactory regenerar/reassinar índices, o keyring da Factory precisa ser adaptado.
Não misturar os dois modelos de forma implícita.
11. Mirror não substitui version pinning
Artifactory Remote é:
proxy + cache
Ele não transforma automaticamente um repositório rolling-release em snapshot imutável.
Portanto:
MIRROR != VERSION PINNING
Continuam importantes:
apko.lock.json;
digests;
SBOM;
provenance;
evidência dos inputs de build.
12. Separar APK de OCI
Há duas necessidades diferentes.
Pacotes Wolfi
Origem:
packages.wolfi.dev/os
Formato:
APK
Recomendação:
Artifactory Alpine Remote + Virtual
Imagens de ferramenta
Exemplos:
cgr.dev/chainguard/apko
cgr.dev/chainguard/melange
Formato:
OCI
Podem ser tratadas por:
ECR Pull Through Cache
ou:
Artifactory Docker Remote
Não confundir os dois problemas.
13. Arquitetura corporativa sugerida
flowchart TD
    W[packages.wolfi.dev/os] --> R[Artifactory wolfi-remote]
    R --> V[Artifactory wolfi-virtual]

    V --> ARC[ARC / EKS Runner]
    ARC --> A[Apko]
    ARC --> M[Melange]

    C[cgr.dev/chainguard/*] --> O[OCI mirror / Pull Through Cache]
    O --> ARC
14. Benefícios
Disponibilidade
Reduz dependência direta do runner em relação ao Wolfi público.
Performance
Pacotes já resolvidos ficam em cache próximo ao ambiente corporativo.
Governança
Permite observar:
downloads;
consumidores;
origem;
retenção;
política de acesso.
Segurança
Possibilita limitar egress direto dos runners para upstreams públicos.
Estabilidade operacional
Pacotes já cacheados podem permanecer disponíveis mesmo durante indisponibilidade temporária do upstream, conforme a política configurada.
15. Riscos e cuidados
Não resolver conectividade com:
--no-check-certificate
TLS verification disabled
unsigned repository
Preservar:
TLS
+
APK trust/signature verification
Também validar:
política de retenção/cache;
comportamento quando upstream muda;
tratamento de metadata;
expiração de cache;
disponibilidade para amd64 e arm64;
autenticação no Artifactory;
Xray/políticas internas.
16. Checklist de implantação
[ ] Confirmar suporte a Package Type Alpine no Artifactory

[ ] Criar wolfi-remote
    Type = Remote
    Package Type = Alpine
    URL = https://packages.wolfi.dev/os

[ ] Criar wolfi-virtual
    Type = Virtual
    Package Type = Alpine
    Member = wolfi-remote

[ ] Validar APKINDEX x86_64

[ ] Validar APKINDEX aarch64

[ ] Testar download de busybox

[ ] Testar download de ca-certificates

[ ] Confirmar cache

[ ] Confirmar TLS

[ ] Confirmar modelo de signing/keyring

[ ] Executar Apko amd64

[ ] Executar Apko arm64

[ ] Executar Melange real no ARC

[ ] Confirmar que Apko usa o mirror

[ ] Confirmar que Melange usa o mirror

[ ] Evitar credenciais versionadas

[ ] Definir owner operacional do mirror

[ ] Definir política de retenção/cache

[ ] Validar Xray, se aplicável

[ ] Migrar a Factory somente depois da POC
17. Resultado esperado
WOLFI_UPSTREAM =
https://packages.wolfi.dev/os

CORPORATE_ENTRYPOINT =
Artifactory wolfi-virtual

PACKAGE_TYPE =
Alpine / APK

DIRECT_WOLFI_ACCESS_FROM_FACTORY =
NO

AMD64 =
PASS

ARM64 =
PASS

APKO =
PASS

MELANGE =
PASS

TLS =
PASS

APK_TRUST =
PASS
18. Recomendação final
Usar Artifactory Remote do tipo Alpine, preferencialmente exposto por um Virtual Repository, como boundary corporativo de resolução e cache de pacotes Wolfi.
Para a primeira POC:
preservar trust Wolfi
+
validar amd64/arm64
+
testar Apko/Melange
+
não alterar ainda a política de assinatura
Depois que o mirror estiver comprovado, migrar a Factory para consumir exclusivamente o endpoint corporativo.