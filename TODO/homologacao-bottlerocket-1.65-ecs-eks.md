# Homologação do Bottlerocket 1.65 em ECS e EKS

## Visão geral

O **Bottlerocket é o sistema operacional do worker node/host EC2**. Ele não é o sistema operacional do Pod ou da Task.

Portanto, a homologação do Bottlerocket é necessária apenas nos cenários em que existe uma **instância EC2 sob gestão da plataforma utilizando uma AMI Bottlerocket**.

---

## Onde o Bottlerocket é utilizado

| Cenário | Bottlerocket? | Motivo |
|---|---:|---|
| ECS + EC2 | ✅ Sim | Bottlerocket pode ser a AMI das Container Instances |
| ECS + Capacity Provider baseado em ASG/EC2 | ✅ Sim | Continua existindo uma EC2 como host |
| ECS + Fargate | ❌ Não | O host é gerenciado pela AWS |
| EKS Managed Node Group + Bottlerocket | ✅ Sim | O worker node é uma EC2 utilizando Bottlerocket |
| EKS Karpenter + Bottlerocket | ✅ Sim | O Karpenter cria EC2 utilizando a AMI Bottlerocket |
| EKS Self-Managed Nodes + Bottlerocket | ✅ Sim | O worker node é administrado pelo cliente |
| EKS Fargate Profile | ❌ Não | A infraestrutura do host é gerenciada pela AWS |
| EKS Control Plane | ❌ Não | O control plane é gerenciado pela AWS |

### Modelo mental

```text
EKS
│
├── Managed Node Group
│      └── EC2
│           └── Bottlerocket 1.65   ← HOMOLOGAR
│
├── Karpenter
│      └── NodeClaim
│           └── EC2
│                └── Bottlerocket 1.65   ← HOMOLOGAR
│
└── Fargate Profile
       └── Pod
            └── Host gerenciado pela AWS   ← FORA DA HOMOLOGAÇÃO
```

O mesmo raciocínio vale para ECS:

```text
ECS
│
├── Capacity Provider / ASG
│      └── EC2
│           └── Bottlerocket 1.65   ← HOMOLOGAR
│
└── Fargate
       └── Task
            └── Host gerenciado pela AWS   ← FORA DA HOMOLOGAÇÃO
```

---

# Objetivo da homologação

A homologação não deve validar apenas se:

> "A EC2 subiu e o Pod ficou Running."

Uma atualização de Bottlerocket pode afetar componentes como:

- kernel;
- container runtime;
- kubelet;
- ECS Agent;
- SSM Agent;
- networking;
- storage;
- observabilidade;
- bootstrap;
- ciclo de vida dos nodes;
- drivers e integrações com o host.

O objetivo deve ser provar que a nova versão pode substituir a anterior **sem regressões funcionais ou operacionais nos produtos suportados pela plataforma**.

---

# Matriz de homologação

| Área | EKS MNG | EKS Karpenter | ECS EC2 | O que validar |
|---|:---:|:---:|:---:|---|
| Boot EC2 | ✅ | ✅ | ✅ | Instância inicializa normalmente |
| Bootstrap | ✅ | ✅ | ✅ | User Data/settings aplicados |
| Registro no cluster | ✅ | ✅ | ✅ | Node `Ready` / ECS Instance `ACTIVE` |
| Runtime | ✅ | ✅ | ✅ | containerd/Docker funcionando |
| Pull ECR | ✅ | ✅ | ✅ | Pull privado e credenciais |
| Networking | ✅ | ✅ | ✅ | ENI, DNS, egress, Service/LB |
| Storage | ✅ | ✅ | ✅ | EBS/EFS/ephemeral |
| IAM | ✅ | ✅ | ✅ | IRSA/Pod Identity/Task Role |
| Observabilidade | ✅ | ✅ | ✅ | Datadog/CloudWatch/OTel/logs |
| SSM | ✅ | ✅ | ✅ | Session Manager/control container |
| Scale-out | — | ✅ | ✅ | Criação automática de capacidade |
| Scale-in/drain | ✅ | ✅ | ✅ | Workloads removidos sem indisponibilidade |
| Rolling update | ✅ | — | ✅ | Troca segura da AMI |
| Consolidation | — | ✅ | — | Disruption/consolidation do Karpenter |
| Spot | — | ✅ | ✅ | Interrupção e reposição |
| Rollback | ✅ | ✅ | ✅ | Retorno para a imagem anterior |

---

# 1. Boot e registro do worker

Este é um teste **P0**.

## EKS

Criar um worker utilizando Bottlerocket 1.65 e validar:

```bash
kubectl get nodes -o wide
```

Verificar detalhes do sistema:

```bash
kubectl get nodes \
  -o custom-columns='NAME:.metadata.name,OS:.status.nodeInfo.osImage,KERNEL:.status.nodeInfo.kernelVersion,RUNTIME:.status.nodeInfo.containerRuntimeVersion,KUBELET:.status.nodeInfo.kubeletVersion'
```

Depois:

```bash
kubectl describe node <NODE_NAME>
```

O esperado é:

```text
Ready=True
MemoryPressure=False
DiskPressure=False
PIDPressure=False
NetworkUnavailable=False
```

### Critério de falha

Se a EC2 inicializa, mas o node não entra em `Ready`, a versão deve ser considerada **reprovada** até investigação.

---

## ECS

Validar o fluxo:

```text
EC2
 ↓
Bottlerocket
 ↓
ECS Agent
 ↓
RegisterContainerInstance
 ↓
ACTIVE
```

Consultar:

```bash
aws ecs describe-container-instances \
  --cluster <CLUSTER> \
  --container-instances <CONTAINER_INSTANCE>
```

A Container Instance deve aparecer conectada e `ACTIVE`.

---

# 2. DaemonSets e agentes da plataforma

Um dos pontos mais importantes da homologação é validar componentes que interagem diretamente com o host.

Exemplos:

- AWS VPC CNI (`aws-node`);
- `kube-proxy`;
- EBS CSI Node;
- EFS CSI Node;
- Datadog Agent;
- CloudWatch Agent;
- OpenTelemetry Collector;
- agentes de segurança;
- agentes corporativos;
- componentes de service mesh;
- outros DaemonSets que utilizem `hostPath`, `hostNetwork`, `/proc`, `/sys`, cgroups etc.

Verificar os Pods executando especificamente no node Bottlerocket 1.65:

```bash
kubectl get pods -A -o wide | grep <NODE_NAME>
```

Não devem existir estados como:

```text
CrashLoopBackOff
ImagePullBackOff
CreateContainerError
ContainerCreating
```

por tempo anormal.

---

# 3. Networking

Uma atualização de kernel/runtime pode afetar diretamente componentes de rede.

Validar:

```text
Pod → Pod no mesmo node
Pod → Pod em outro node
Pod → ClusterIP
Pod → CoreDNS
Pod → Internet/NAT
Pod → Endpoint AWS
Pod → ALB/NLB
ALB/NLB → Pod
```

## DNS

```bash
kubectl exec <POD> -- nslookup kubernetes.default.svc.cluster.local
```

## Comunicação com Service

```bash
kubectl exec <POD> -- curl http://<SERVICE>
```

## Teste de densidade

Além de um único Pod, criar múltiplos workloads, por exemplo:

```text
1 Pod
10 Pods
20 Pods
50 Pods
```

Validar:

- alocação de IPs;
- criação de ENIs;
- comunicação;
- CoreDNS;
- ausência de erro no VPC CNI.

---

# 4. ECR e Container Runtime

Este é um teste **P0**.

Validar o fluxo:

```text
ECR
 ↓
Pull
 ↓
containerd / Docker
 ↓
Create container
 ↓
Start container
 ↓
Running
```

Utilizar diferentes tipos de imagem:

- imagem pequena;
- imagem grande;
- imagem privada no ECR;
- imagem corporativa real;
- imagem multi-arch, caso ARM64 seja suportado.

No EKS, provocar vários ciclos de criação e remoção:

```bash
kubectl rollout restart deployment/<DEPLOYMENT>
```

Validar operações como:

```text
PullImage
CreateContainer
StartContainer
StopContainer
DeleteContainer
```

---

# 5. Storage

## EKS

Validar, conforme suportado pela plataforma:

- `emptyDir`;
- ephemeral storage;
- EBS CSI;
- EFS CSI.

### Teste EBS

Fluxo esperado:

```text
PVC
 ↓
PV
 ↓
EBS
 ↓
Attach
 ↓
Mount
 ↓
Pod escreve arquivo
 ↓
Pod reinicia
 ↓
Arquivo continua existindo
```

Depois testar remanejamento entre nodes:

```text
Pod A → Node A
Delete Pod
Pod B → Node B
```

Validar:

- detach;
- attach;
- mount;
- persistência do conteúdo;
- ausência de timeout no CSI.

---

# 6. IAM

## EKS

Validar os mecanismos utilizados pela plataforma:

- IAM Roles for Service Accounts (IRSA);
- EKS Pod Identity;
- credenciais via IMDS quando aplicável.

Exemplo:

```bash
aws sts get-caller-identity
```

Também pode ser utilizada alguma operação controlada em:

- S3;
- SQS;
- DynamoDB;
- Secrets Manager;
- SSM.

---

## ECS

Validar:

- EC2 Instance Role;
- Task Execution Role;
- Task Role;
- acesso ao ECR;
- acesso ao Secrets Manager/SSM;
- CloudWatch Logs.

---

# 7. Observabilidade

Não basta validar que o agente aparece como `Running`.

É necessário confirmar a chegada efetiva de telemetria.

Validar:

- métricas do node;
- CPU;
- memória;
- disco;
- rede;
- métricas de container;
- métricas de Pods;
- logs;
- eventos;
- kubelet metrics;
- traces, quando aplicável.

Comparar preferencialmente:

```text
Bottlerocket versão anterior
vs.
Bottlerocket 1.65
```

Um agente pode permanecer `Running` e, ainda assim, perder acesso a:

```text
/proc
/sys
cgroups
kubelet
sockets do runtime
```

---

# 8. Managed Node Group

Managed Node Group precisa de uma homologação própria porque o principal risco não é apenas o boot da AMI, mas o **rolling replacement**.

Fluxo de teste:

```text
MNG com versão anterior
      ↓
Workloads rodando
      ↓
Atualizar MNG para BR 1.65
      ↓
Novo node BR 1.65
      ↓
Cordon/drain do node antigo
      ↓
Pods migram
      ↓
Node antigo é removido
```

Monitorar:

```bash
kubectl get nodes -w
```

e:

```bash
kubectl get pods -A -o wide -w
```

Validar principalmente:

- PodDisruptionBudget;
- `terminationGracePeriodSeconds`;
- readiness probes;
- liveness probes;
- graceful shutdown;
- DaemonSets;
- StatefulSets;
- tempo de drenagem;
- indisponibilidade das aplicações.

### Pergunta que o teste deve responder

> É possível atualizar os Managed Nodes para Bottlerocket 1.65 sem indisponibilidade relevante das aplicações?

---

# 9. Karpenter

O Karpenter precisa de uma homologação separada porque seu ciclo de vida é diferente do Managed Node Group.

Durante a homologação, é recomendável **fixar explicitamente a AMI/versão testada**.

Fluxo de provisionamento:

```text
0 capacidade
      ↓
Workload fica Pending
      ↓
Karpenter cria NodeClaim
      ↓
EC2 Bottlerocket 1.65 sobe
      ↓
Node fica Ready
      ↓
Pod fica Running
```

Depois validar scale-in:

```text
Remover workload
      ↓
Node fica vazio
      ↓
Consolidation / Disruption
      ↓
NodeClaim removido
      ↓
EC2 terminada
```

## Cenários importantes

Quando suportados:

- On-Demand;
- Spot;
- amd64;
- arm64;
- múltiplas AZs;
- diferentes famílias de instância.

Exemplo:

```text
m7i → Intel
m7a → AMD
m7g → Graviton
```

Não é necessário testar dezenas de instance types. O mais importante é cobrir **classes de hardware distintas suportadas pelo produto**.

---

# 10. ECS + EC2

Para ECS, validar:

- registro da Container Instance;
- ECS Agent;
- pull do ECR;
- `awsvpc`;
- Task Role;
- Execution Role;
- Secrets Manager/SSM;
- CloudWatch Logs;
- Target Registration no ALB/NLB;
- Health Check;
- EFS, quando utilizado;
- ECS Exec, quando utilizado;
- Datadog/FireLens, quando utilizados.

Fluxo:

```text
Task Definition
      ↓
ECS Service
      ↓
Placement na EC2 Bottlerocket 1.65
      ↓
Pull da imagem
      ↓
Container Running
      ↓
Target registrado no LB
      ↓
Health Check OK
```

---

# 11. Scale-out e Scale-in

Não é necessário executar um load test gigantesco.

## Karpenter

Exemplo:

```text
1 Pod
 ↓
10 Pods
 ↓
50 Pods
 ↓
Karpenter cria capacidade adicional
 ↓
Pods ficam Running
 ↓
Reduz replicas
 ↓
Karpenter consolida/remove nodes
```

Validar:

- scheduling;
- NodeClaims;
- tempo para `Ready`;
- scale-out;
- scale-in;
- disruption;
- remoção de EC2.

---

## ECS Capacity Provider

Fluxo:

```text
Tasks Pending
 ↓
Capacity Provider solicita capacidade
 ↓
ASG cria EC2 Bottlerocket 1.65
 ↓
Container Instance registra
 ↓
Tasks iniciam
 ↓
Carga reduz
 ↓
Capacity Provider reduz capacidade
```

---

# 12. Drain e graceful termination

Este teste deve ser obrigatório em homologações de imagem de worker.

Exemplo:

```bash
kubectl drain <NODE> \
  --ignore-daemonsets \
  --delete-emptydir-data
```

Validar:

- Pods são reagendados;
- PDB funciona;
- conexões são drenadas;
- targets são removidos do Load Balancer;
- aplicação continua disponível;
- shutdown respeita o grace period.

Depois, encerrar o node.

---

# 13. Reboot

Validar explicitamente reboot da instância.

Cenário:

```text
Bottlerocket 1.65
+
Workloads reais
      ↓
Reboot da EC2
      ↓
Sistema operacional sobe
      ↓
Networking sobe
      ↓
Runtime sobe
      ↓
Node registra novamente
      ↓
DaemonSets sobem
      ↓
Workloads voltam
```

Validar:

- boot;
- runtime;
- network;
- kubelet/ECS Agent;
- SSM;
- observabilidade;
- reentrada no cluster.

---

# 14. SSM e suporte operacional

Mesmo que workloads estejam funcionando, é importante garantir que o time continue tendo capacidade de troubleshooting.

Validar:

```text
EC2
 ↓
SSM Managed Instance
 ↓
Session Manager
 ↓
Control/Admin Container
```

Itens:

- instância aparece no Systems Manager;
- Session Manager funciona;
- ferramentas necessárias ao suporte continuam disponíveis;
- logs podem ser coletados;
- diagnóstico pode ser realizado.

---

# 15. Spot e interrupção

Quando Spot fizer parte do catálogo:

## Karpenter

Validar:

```text
Spot Node
 ↓
Interruption Notice
 ↓
Karpenter identifica interrupção
 ↓
Cordon/Drain
 ↓
Workload migra
 ↓
Novo node é criado, se necessário
```

## ECS

Validar:

```text
Spot EC2
 ↓
Interruption Notice
 ↓
Container Instance entra em drain
 ↓
Tasks são realocadas
 ↓
Capacidade é substituída
```

---

# 16. Cenários especiais

Criar testes específicos somente para funcionalidades realmente suportadas pela plataforma.

Exemplos:

- NVIDIA GPU;
- AWS Neuron;
- EFA;
- FIPS;
- ARM64;
- privileged containers;
- `hostNetwork`;
- `hostPID`;
- `hostPath`;
- bootstrap containers;
- admin containers;
- superpowered host containers.

Esses cenários normalmente possuem maior dependência do kernel e do host.

---

# Estratégia de homologação

A homologação pode ser organizada em três trilhas:

```text
                    BOTTLEROCKET 1.65
                           │
           ┌───────────────┼─────────────────┐
           │               │                 │
          ECS             EKS               EKS
          EC2             MNG             Karpenter
           │               │                 │
           ▼               ▼                 ▼
       Bootstrap        Bootstrap         Provision
       ECS Agent        Node Ready        NodeClaim
       Runtime          containerd        Node Ready
       ECR              CNI               containerd
       Network          CSI               CNI
       IAM              IAM               CSI
       Logs             Datadog           Datadog
       ALB              Workload          Workload
       Scale            Drain             Consolidate
       Drain            Upgrade           Disrupt
           │               │                 │
           └───────────────┼─────────────────┘
                           ▼
                    HOMOLOGADO 1.65
```

**Fargate fica fora da homologação de Bottlerocket.**

---

# Critérios de aceite

A versão Bottlerocket 1.65 pode ser considerada homologada quando:

- [ ] EC2 Bottlerocket 1.65 inicializa normalmente.
- [ ] EKS node entra em `Ready`.
- [ ] ECS Container Instance entra em `ACTIVE`.
- [ ] Bootstrap é aplicado corretamente.
- [ ] DaemonSets essenciais ficam saudáveis.
- [ ] ECR pull funciona.
- [ ] Containers são criados, reiniciados e removidos normalmente.
- [ ] VPC CNI funciona.
- [ ] DNS funciona.
- [ ] Comunicação entre Pods funciona.
- [ ] ClusterIP funciona.
- [ ] ALB/NLB funciona.
- [ ] EBS CSI funciona.
- [ ] EFS CSI funciona, quando suportado.
- [ ] Ephemeral storage funciona.
- [ ] IRSA funciona.
- [ ] EKS Pod Identity funciona, quando utilizado.
- [ ] ECS Task Role funciona.
- [ ] ECS Execution Role funciona.
- [ ] Datadog continua coletando métricas e logs.
- [ ] CloudWatch/OTel continuam funcionando.
- [ ] SSM continua disponível.
- [ ] Managed Node Group realiza rolling replacement corretamente.
- [ ] Karpenter cria NodeClaims usando Bottlerocket 1.65.
- [ ] Karpenter realiza scale-out corretamente.
- [ ] Karpenter realiza consolidation/disruption corretamente.
- [ ] ECS Capacity Provider escala corretamente.
- [ ] Drain funciona sem indisponibilidade inesperada.
- [ ] Reboot funciona.
- [ ] Spot funciona, quando suportado.
- [ ] ARM64 funciona, quando suportado.
- [ ] Cenários especiais da plataforma foram testados.
- [ ] Existe rollback validado para a versão anterior.

---

# Priorização sugerida

## P0 — bloqueia promoção

- Boot EC2;
- Node `Ready` / ECS Instance `ACTIVE`;
- runtime;
- ECR;
- networking;
- DNS;
- CNI;
- IAM;
- principais DaemonSets;
- observabilidade básica;
- MNG rolling update;
- Karpenter provisioning;
- drain;
- rollback.

## P1 — necessário antes de produção ampla

- EBS/EFS;
- scale-out/scale-in;
- Spot;
- reboot;
- SSM;
- consolidation;
- ECS Capacity Provider;
- ALB/NLB;
- graceful termination.

## P2 — conforme catálogo

- ARM64;
- GPU;
- Neuron;
- EFA;
- FIPS;
- privileged;
- host containers;
- funcionalidades específicas de clientes.

---

# Variantes que devem ser homologadas

A homologação deve ocorrer por variante **realmente publicada e suportada pela plataforma**.

Exemplo:

```text
aws-k8s-1.33 x86_64
aws-k8s-1.34 x86_64
aws-k8s-1.35 x86_64
aws-k8s-1.36 x86_64

+ arm64, se suportado
+ nvidia, se suportado
+ fips, se suportado
```

Não há necessidade de homologar combinações que não fazem parte do catálogo.

---

# Managed Node Group x Karpenter

Mesmo utilizando a mesma versão do Bottlerocket, os dois cenários devem ser tratados separadamente.

## Managed Node Group

O foco principal é:

```text
AMI nova
 ↓
Rolling replacement
 ↓
Drain
 ↓
Reschedule
 ↓
Remoção segura do node antigo
```

## Karpenter

O foco principal é:

```text
Workload Pending
 ↓
NodeClaim
 ↓
EC2 criada
 ↓
Node Ready
 ↓
Scheduling
 ↓
Consolidation / Disruption
 ↓
EC2 removida
```

A diferença principal não está no Pod, mas em **quem cria, atualiza, drena, substitui e remove o worker node**.

---

# Resumo

## Bottlerocket precisa ser homologado quando existe EC2

```text
ECS EC2              → SIM
ECS Fargate          → NÃO

EKS Managed Nodes    → SIM
EKS Karpenter        → SIM
EKS Self Managed     → SIM
EKS Fargate          → NÃO
EKS Control Plane    → NÃO
```

Para Bottlerocket 1.65, a homologação deve cobrir principalmente:

```text
Boot
Bootstrap
Runtime
Networking
Storage
IAM
Observabilidade
SSM
Upgrade
Drain
Scale
Reboot
Rollback
```

O objetivo final é demonstrar não apenas que a imagem inicializa, mas que **todo o ciclo de vida do worker continua funcional e seguro utilizando Bottlerocket 1.65**.
