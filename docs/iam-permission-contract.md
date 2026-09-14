# P1-04 — Contrato de permissões IAM da fábrica e proposta corporativa

**PROPOSED / NOT APPLIED.** Baseline main
`dd037cc9a8dc2b3585d9941666ba508ecca87c9a`, que incorpora PR #59.
Este contrato entrega inventário, templates e aceite futuro para Cloud/IAM.
Não descreve a identity policy efetivamente anexada ao sandbox: ela não está
disponível neste levantamento. Sucesso histórico de comandos não permite
reconstituir todos os grants/denies da sessão.

Autoria e sustentação seguem o [ADR-0003](adr/0003-controles-seguranca-workflows-federados.md).
Containers Products opera workflows próprios; isso não concede administração
AWS nem dispensa decisões de Segurança. IAM corporativo é EXTERNAL_PENDING.
Não há novo ADR: esta proposta preserva o desenho e explicita seus limites.

## Atual versus proposto

| Camada | Estado conhecido | Proposta / limite |
| --- | --- | --- |
| Trust policy | [Arquivo ativo versionado](../policies/aws/github-actions-image-base-trust.json); read-back histórico em [10/09](evidence/repository-rename-2026-09-10.json) | Preservado; template separado acrescenta repository/IDs/ref documentados pela AWS; autenticação com ele NOT RUN |
| Identity policy | Conteúdo anexado/inline, versão default e permissões efetivas não inventariados | Execution + provisioning com 12 actions ECR explícitas, para uma identidade de execução nos três caminhos atuais |
| ECR repository policy | [RFC](../RFC-013-Image-Base-Completa-com-Mermaid.md) descreve aplicação histórica de pull por organizações; policy real não integra este pacote | Não substituída nem copiada; Cloud fornece acessos/denies por recurso e aprova eventual acesso entre contas |
| Session policy / boundary / SCP / RCP / endpoint policy | Não fornecidas nem consultadas nesta sessão | EXTERNAL_PENDING; Cloud apresenta restrições aplicáveis. Não pressupor ausência |
| Token GitHub | Permissões declaradas nos workflows | Outro sistema; não traduzir `attestations: write` ou `artifact-metadata: write` em actions IAM |

Trust decide quem assume; identity e repository policies participam da
autorização sobre ECR; as demais camadas podem restringir a sessão. Explicit
deny prevalece; grants adicionais podem ampliar o que este JSON isolado parece
permitir. Mesma conta e acesso entre contas têm regras diferentes. Conferir
o conjunto efetivo, inclusive principal role versus session, conforme
[avaliação IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html)
e [repository policies ECR](https://docs.aws.amazon.com/AmazonECR/latest/userguide/repository-policies.html).
Um login bem-sucedido não prova autorização de push/pull. O token ECR tem o
escopo do principal e sua obtenção exige identity permission específica.

## Inventário por operação

O [inventário JSON](../policies/aws/proposals/factory-permissions/inventory.json)
é a relação testada entre `Sid`, actions, operações, comandos, recursos,
condições e fontes locais/oficiais. A tabela abaixo facilita sua leitura.
`OBSERVED_CODE` significa chamada presente; `OFFICIAL_DOCUMENTATION` confirma
o mapeamento/API. Isso **não** é trace observado de cada request das ferramentas.
Execução com as policies propostas é NOT RUN em todas as linhas.

| ID / workflow, job e step | Ferramenta / operação | Actions IAM relacionadas |
| --- | --- | --- |
| O01 — publish `build-push`, promoção `promote`, recovery `recover`: Configure AWS credentials | configure-aws-credentials → STS WebIdentity; identidade da sessão | `sts:AssumeRoleWithWebIdentity` na trust; GetCallerIdentity não exige grant explícito |
| O02 — mesmos jobs: Login to Amazon ECR; publicação OCI | amazon-ecr-login; AWS CLI get-login-password; Docker/Skopeo login | `ecr:GetAuthorizationToken` |
| O03 — publicador: Ensure ECR repository exists | AWS CLI describe-repositories | `ecr:DescribeRepositories` |
| O04 — mesmo step, somente RepositoryNotFoundException | create-repository, incluindo scanOnPush e mutabilidade iniciais | `ecr:CreateRepository` |
| O05 — mesmo step, toda publicação | put-image-tag-mutability | `ecr:PutImageTagMutability` |
| O06 — publicador: Publish validated OCI artifact | Skopeo copy --all --preserve-digests; consulta blobs/manifests, uploads e publicação de índice/plataformas | `ecr:BatchCheckLayerAvailability`, `ecr:BatchGetImage`, `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`, `ecr:PutImage` |
| O07 — mesmo step, read-back | Skopeo inspect --raw pela build tag; verify_publication compara localmente | `ecr:BatchGetImage` |
| O08 — publicador: Sign published image | Cosign sign, bundle/referrer OCI adicional | Leitura/check e escrita de O06; discovery ListImageReferrers usa `ecr:BatchGetImage` |
| O09 — publicador: Attest original SPDX SBOMs | publish_sboms → Cosign attest para índice/amd64/arm64, blobs/manifests adicionais | Mesmo conjunto de O08; não é actions/attest-sbom |
| O10 — publicador: Attest build provenance | attest-build-provenance → attest, push-to-registry | Conjunto OCI de O06; API GitHub/serviços Sigstore separados |
| O11 — promoção: List images in repository | describe-images; seletor usa JSON/quarentena locais | `ecr:DescribeImages` |
| O12 — promoção/recovery: Verify platforms, signature and provenance | Buildx inspect; Cosign verify/referrers/bundle; gh attestation verify oci:// | `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer`; provenance também usa API GitHub |
| O13 — promoção/recovery: Re-scan; Report CVEs without an available fix | Trivy remoto lê manifests/configs/layers por arquitetura | `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer` |
| O14 — promoção: Promote to stable | Buildx imagetools create no mesmo repositório/índice | `ecr:BatchGetImage`, `ecr:PutImage` |
| O15 — promoção: Confirm stable via independent ECR read-back | verify_stable → describe-images pela tag stable | `ecr:DescribeImages` |
| O16 — recovery: Confirm target digest; Capture current stable | describe-images por digest/tag | `ecr:DescribeImages` |
| O17 — recovery: Restore stable | Buildx retag do índice existente no mesmo repositório | `ecr:BatchGetImage`, `ecr:PutImage` |
| O18 — recovery: Confirm stable via independent read-back | describe-images pela tag, comparação explícita | `ecr:DescribeImages` |

Fontes executáveis: [publicador](../.github/workflows/build-base-images.yml),
[promoção](../.github/workflows/promote-stable.yml),
[recovery](../.github/workflows/recover-stable.yml),
[verificador](../scripts/pipeline/release/verify_promotion.py),
[SBOM](../scripts/pipeline/release/publish_sboms.py) e
[read-back](../scripts/pipeline/release/verify_stable.py).
APIs do proxy registry e AWS CLI não são nomes intercambiáveis de actions.
Em particular, [ListImageReferrers exige BatchGetImage](https://docs.aws.amazon.com/AmazonECR/latest/APIReference/API_ListImageReferrers.html).
O número e a ordem de requests dependem da versão/deduplicação/cache; o
[conjunto documentado de push](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-push-iam.html)
e os fontes Cosign/attest sustentam a proposta, não uma afirmação de mínimo
empiricamente comprovado para cada cliente.

### Recursos e condições

- Todas as actions ECR propostas, exceto GetAuthorizationToken, usam a lista
  explícita de ARNs `arn:aws:ecr:REGION:ACCOUNT:repository/NAME` fornecida por Cloud.
  Nenhum ARN usa wildcard de conta, região ou repositório.
- `EcrAuthorizationToken` é o único statement identity com `Resource: "*"`:
  a [referência ECR](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ecr.html)
  não oferece recurso específico para essa action. Não concede acesso a todos
  os repositórios; os requests seguintes continuam sujeitos à autorização.
- `aws:RequestedRegion` delimita o endpoint ECR em todos os statements identity.
  É uma condição global sobre a região solicitada, não sobre tags de imagem;
  ver [semântica AWS](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html#condition-keys-requestedregion).
- Tags AWS de recurso/request referem-se a metadata do repositório. Nenhum
  `ResourceTag`/`RequestTag` está sendo usado para representar a tag Docker stable.

### Fora das permissões da fábrica

Health, pins e resumos usam GitHub/HTTP, sem sessão AWS: não recebem nova role.
Validação Apko/Melange e contratos reusáveis permanecem sem AWS/OIDC.
O composite setup-trivy compartilhado roda dentro do job autenticado de
promoção/recovery; isso não cria outra identidade nem isola as credenciais
desse job. Diferenciar composite de executor reusable sem credenciais.

CreateRepository configura scanOnPush no request inicial; isso não requer
adicionar StartImageScan, DescribeImageScanFindings ou PutImageScanningConfiguration
à execução descrita. Não há necessidade demonstrada de ListImages, delete,
SetRepositoryPolicy, lifecycle, TagResource ou pull-through cache nos jobs.
Lifecycle/policy de pull foram operações administrativas históricas, não
justificativa para conceder gestão delas à role recorrente.

Cosign keyless não usa AWS KMS/Signer. Downloads ECR de layers recebem
[URLs pré-assinadas](https://docs.aws.amazon.com/AmazonECR/latest/APIReference/API_GetDownloadUrlForLayer.html),
sem justificar s3:GetObject à role. O alvo manual `make certificates` tem
suporte de aquisição S3, mas não é chamado pelos workflows atuais, que usam
anchors locais revisadas. Sua ativação exigiria outra necessidade autorizada.
Também não se acrescentam Secrets Manager, CloudWatch, CloudTrail, IAM ou PassRole.

## Proposta compatível e separação de provisionamento

Os [templates](../policies/aws/proposals/factory-permissions/README.md) propõem
**uma identidade de execução**, como no desenho atual. Não criam roles.

| Template / Sid | Finalidade | Uso proposto |
| --- | --- | --- |
| execution / EcrAuthorizationToken | Autenticação | Todos os jobs AWS |
| execution / ReadImagesAndEvidence | Manifests, layers, metadados e referrers | Leitura/publicação/verificação/promoção/recovery |
| execution / WriteImagesAndEvidence | Blobs, manifests de imagens e evidence; retag | Publicação e movimentação de stable |
| provisioning / InspectRepositoryConfiguration | Verificar existência/configuração | Publicador atual |
| provisioning / EnsureRepositoryConfiguration | Criar ausente e reaplicar mutabilidade | Publicador atual, inclusive quando repo já existe |
| trust / GitHubMainWithRepositoryIds | Assunção inicial por origem/ref/IDs | Proposta condicionada a claims reais e revisão Cloud |

**Compatibilidade proposta = execution + provisioning**, recursos completos
para o lote desejado e trust aceita nas rotas atuais. Só execution falha no
publicador atual. Mesmo pré-criando os ECRs, PutImageTagMutability continua
incondicional. Não apresentar retirada dessas actions como troca transparente.
Descrição de compatibilidade significa cobertura do código/documentação;
teste real com o conjunto reduzido continua pendente.

Cloud pode preferir pré-provisionar recursos e reter a administração. Essa
alternativa requer futura alteração explícita do step de ensure para verificar
propriedades sem reaplicá-las, migração/negativos e revisão; nada disso é
implementado aqui. Somente então execution e a leitura de DescribeRepositories
podem compor o perfil recorrente sem create/mutability. Repository policy,
lifecycle, criptografia, tags AWS obrigatórias e serviço de scanning são
decisões Cloud; não se inventam grants adicionais para acomodá-las agora.

## Limitação publisher / promoter / stable

**Com essas actions e recursos, o publicador ainda conseguiria retaguear o
mesmo repositório para stable? Sim**, na ausência de outra restrição efetiva.
[Retag ECR](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-retag.html)
usa BatchGetImage + PutImage. A [API PutImage](https://docs.aws.amazon.com/AmazonECR/latest/APIReference/API_PutImage.html)
aceita imageTag, mas esse parâmetro não é uma condition key IAM documentada.

O fluxo atual grava build tags e reserva stable por convenção de código/gates.
A exceção `IMMUTABLE_WITH_EXCLUSION` para stable permite sobrescrita dessa
tag, não autoriza um principal específico. Uma role chamada publisher com
PutImage e outra chamada promoter com PutImage sobre o mesmo ARN não mudam
isso. `ecr:ResourceTag`/`aws:ResourceTag` não distinguem stable de build tags.
Não existe teste local fingindo avaliar uma condição `ecr:ImageTag`.

O perfil compatível também concede PutImageTagMutability: uma sessão abusada
pode mudar a configuração, além dos valores enviados pelo workflow revisado.
Não há restrição de parâmetro de mutabilidade usada na proposta. Retirar
provisioning futuramente reduz esse poder, mas não impede retag de stable por
PutImage. Mesmo papéis distintos no mesmo recurso não criam separação por tag.

Soak, scan, assinatura/provenance, concorrência e read-back continuam gates
da aplicação; não são condições IAM. Possíveis fronteiras por recursos
distintos ou mediação da escrita seriam outro desenho e exigiriam decisões
e implementação próprias. Não são propostas para execução nesta fatia.
Também não há promessa de isolamento por framework de uma sessão autorizada
para todo o catálogo: a granularidade efetiva é a lista de ARNs dessa sessão.

## OIDC atual e proposta corporativa

Trust versionada do sandbox: provider `token.actions.githubusercontent.com`,
issuer `https://token.actions.githubusercontent.com`, audience AWS
`sts.amazonaws.com`, subject exato:

```text
repo:alric-corp@178685987/alric-containers-image-base@1360616627:ref:refs/heads/main
```

Owner ID `178685987`, repository ID `1360616627`, role `github-actions-image-base`.
Aplicação/read-back históricos na [migração](repository-rename.md); nenhuma
releitura IAM atual nesta sessão. Não registrar JWTs, tokens ECR ou credenciais.
A audience Sigstore é outra solicitação OIDC, não a sessão AWS.

| Caminho | Caller / executor AWS | Ref/guard e claim relevante |
| --- | --- | --- |
| Push main; cron diário 03:00; dispatch de workflow.yml | workflow.yml → build-base-images.yml/build-push | Guards main/event nos dois; job_workflow_ref do publicador esperado pelo mecanismo reusable |
| Cron horário :17 | workflow.yml → promote-stable.yml/promote | Main/schedule; job_workflow_ref do reusable de promoção esperado |
| Dispatch direto de promoção | promote-stable.yml/promote | Guard main; não assumir job_workflow_ref presente |
| Dispatch recovery | recover-stable.yml/recover | **Não tem guard main no job**; a trust exata rejeita outra ref na assunção, além da validação local de inputs |
| PR interno/fork | workflow.yml → validate-base-images.yml → executor shared | Somente validação/leitura, sem AWS/OIDC; não adicionar credenciais para teste |
| Reusables de validação/runtime | Biblioteca consumida por SHA | Sem configure-aws ou grants AWS; scripts/checkout pertencem ao caller |

Em reusable, `repository`, IDs, `ref` e `workflow` descrevem o caller;
`job_workflow_ref` identifica o reusable chamado. Esperados nesta main:
`alric-corp/alric-containers-image-base/.github/workflows/build-base-images.yml@refs/heads/main`
e o caminho equivalente de `promote-stable.yml`. São valores derivados do
código/documentação, **não claims novas observadas em execução**.

### Claims suportadas versus claims presentes

| Claims GitHub / prefixo token.actions.githubusercontent.com: | IAM documentado | Available in session | Uso nesta proposta |
| --- | --- | --- | --- |
| aud, sub | Sim | Sim | Exatos, preservando formato de subject efetivamente emitido |
| repository, repository_id, repository_owner_id, ref | Sim | Não | StringEquals na trust proposta; confirmar valores reais em cada rota |
| job_workflow_ref | Sim | Não | Não exigida globalmente; presença em dispatch direto não comprovada |
| workflow | Sim | Não | Nome do workflow, não caminho/SHA; não usada como isolamento de arquivo |
| actor, actor_id, environment, enterprise_id | Sim | Não | Sem necessidade/valor confirmado para impor nesta proposta |
| workflow_ref, workflow_sha, job_workflow_sha, event_name, runner_environment, repository_visibility, ref_protected | Sem condition key direta GitHub documentada na referência consultada | Não presumir | Não usadas; não confundir linhas GitLab da mesma página com GitHub |

A [referência IAM, seção GitHub](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_iam-condition-keys.html#condition-keys-wif)
e o [anúncio AWS](https://aws.amazon.com/about-aws/whats-new/2026/01/aws-sts-supports-validation-identity-provider-claims/)
documentam claims adicionais, apesar do aviso antigo ainda presente no guia
GitHub de AWS. Para suporte IAM, prevalece a referência AWS atual. A presença
e semântica vêm dos [tokens GitHub](https://docs.github.com/en/actions/reference/security/oidc)
e do [reuso](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-with-reusable-workflows).
As extras marcadas Não não são usadas em conditions identity das chamadas ECR.

A condição `token.actions.githubusercontent.com:repository`, comparada por
`StringEquals`, vincula esta proposta ao nome exato do repositório. Em uma
renomeação, essa condição precisa ser atualizada; IDs preservados não tornam
a trust inteira independente do nome. A autenticação falha enquanto o nome
configurado não corresponder à identidade apresentada. Consulte o
[procedimento de renomeação do repositório](repository-rename.md), que também
abrange outras referências e condições.

O template mantém sub/aud e adiciona repository/IDs/ref sem IfExists. Não
restringe caminho de workflow nem atesta sua aprovação humana. Exigir
job_workflow_ref para todas as rotas quebraria as diretas se a claim faltar;
IfExists daria uma saída permissiva. Qualquer endurecimento por caminho deve
tratar explicitamente as rotas diretas e os callers, com nova validação.
Não se muda customização de sub, Environments ou settings organizacionais.

### Permissões GitHub separadas

Publicador: `contents: read`, `actions: read`, `id-token: write`,
`attestations: write`, `artifact-metadata: write`. Promoção: leituras contents,
actions/attestations e id-token write; recovery não declara actions read.
Executores de validação/runtime e health têm apenas suas leituras declaradas.
Artifacts de CI usam API GitHub, não S3 da role. Provenance é criada pela
action GitHub e também anexada ao ECR; SPDX usa Cosign. O
[ADR-0002](adr/0002-sigstore-trust-model.md) e o
[contrato de consumo](consumer-verification-contract.md) preservam trust roots,
identidades, limites de evidence e decisão Sigstore externa.

## Parâmetros e renderização local

Templates são JSON sintaticamente válido com marcadores, **não documentos
prontos para anexar**. O [renderizador local](../tools/render_iam_proposal.py)
substitui valores JSON inteiros, inclusive lista de ARNs, sem AWS, shell
interpolation, avaliação de permissões ou escrita dentro do checkout.
Falha com parâmetros desconhecidos, ausentes, duplicados/incoerentes,
wildcards, placeholder desconhecido ou destino existente. Não sobrescreve arquivos.

| Parâmetro fornecido por Cloud/IAM | Regra / decisão |
| --- | --- |
| AWS_ACCOUNT_ID | Conta-alvo, 12 dígitos; não copiar sandbox ou fixture como conta corporativa |
| AWS_REGION | Uma região comercial aprovada; proposta limita-se à partição aws, não GovCloud/China |
| ECR_REPOSITORIES | Lista explícita, sem wildcard, de nomes image-base-<framework>; deve cobrir exatamente o lote autorizado |
| GITHUB_REPOSITORY | Owner/repo corporativo concreto; nomes do sandbox não são aprovação corporativa |
| GITHUB_REPOSITORY_ID / GITHUB_OWNER_ID | IDs numéricos confirmados pela administração GitHub |
| GITHUB_SUB | Subject main exato confirmado, com IDs imutáveis ou formato padrão emitido; customizações diferentes exigem revisão do contrato, sem inferir valor |

OIDC_PROVIDER_ARN e ECR_REPOSITORY_ARNS são derivados de conta/região/nomes,
não inputs arbitrários. Issuer/audience/ref são os fixos descritos acima.
Existência da região, conta, provider, repos ou claims **não** é verificada
pelo renderizador. Cloud também fornece role name/ARN, duração de sessão,
políticas adicionais, limites de tamanho e permissões de aprovação/aplicação;
esses parâmetros administrativos não são criados pelo utilitário.

A [fixture](../policies/aws/proposals/factory-permissions/parameters.fixture.json)
usa conta de exemplo `111122223333`, identidade GitHub sintética e apenas
Go runtime/-dev. Não cobre os 17 itens do catálogo. Para proposta de lote
completo, Cloud fornece os 17 ARNs/names autorizados (16 automáticos e dotnet8
somente se execução manual for autorizada); conferir contra frameworks/ e
inputs reais. Excluir um repo da proposta deve limitar o lote explicitamente,
nunca converter sua falta de permissão em PASS.

Exemplo **somente local**, com destino novo fora do checkout:

```bash
python3 -B tools/render_iam_proposal.py \
  --parameters policies/aws/proposals/factory-permissions/parameters.fixture.json \
  --output /tmp/p104-iam-proposal-example
python3 -B -m unittest tests.unit.pipeline.governance.test_iam_proposal -v
```

O comando gera execution.identity.json, provisioning.identity.json e trust.json.
Não há apply, attach, create-role ou configure-aws no utilitário. Os jobs
AWS não consomem os exemplos como permissões; testes offline os leem no CI.
Testes de estrutura e tamanho com todo catálogo não comprovam IAM; quotas
usadas seguem a [referência IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_iam-quotas.html).

## Validação e plano sandbox posterior — NÃO EXECUTADO

| Estado | Alcance desta fatia |
| --- | --- |
| LOCAL_STRUCTURE_VALIDATED | JSON, parâmetros, escopo/ações/refs e negativos offline; resultado na spec |
| AWS_VALIDATOR_CHECKED | NOT RUN |
| AWS_SIMULATION_CHECKED | NOT RUN |
| SANDBOX_EXECUTION_VERIFIED | NOT RUN para estas policies |
| CORPORATE_ACCEPTED | EXTERNAL_PENDING / NOT VERIFIED |

[Access Analyzer ValidatePolicy](https://docs.aws.amazon.com/IAM/latest/UserGuide/access-analyzer-policy-validation.html)
e [IAM Policy Simulator](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_testing-policies.html)
são etapas oficiais futuras. Preparar JSON renderizado, policyType identity
para execution/provisioning e `RESOURCE_POLICY` para trust, com
`--validate-policy-resource-type AWS::IAM::AssumeRolePolicyDocument`, conforme
[CLI oficial](https://docs.aws.amazon.com/cli/latest/reference/accessanalyzer/validate-policy.html);
guardar findings, versões e limitações.
Não se acrescenta acesso ao validador à role da fábrica. Simulação de actions
no ARN permitido/outro ARN/região é útil, mas não prova trust OIDC emitida,
repository policies efetivas ou suporte de claim inventada no contexto.

### Pré-requisitos e alvos a autorizar

1. Após revisão, responsável autoriza por escrito conta sandbox, região,
   janela, operador provisionador, role **nova e isolada** `p104-iam-lab`,
   GitHub repo de teste controlado e seus IDs/ref. Esses nomes são proposta
   de teste, não recursos existentes. Não usar role github-actions-image-base
   nem os ECRs correntes da fábrica.
2. Na conta autorizada, reservar `image-base-p104-lab` e
   `image-base-p104-lab-dev` como permitidos e `image-base-p104-denied` como
   recurso de negativo, todos descartáveis e sem consumidores. O operador
   usa a lista explícita correspondente; não conceder wildcard por prefixo.
3. Operador Cloud separado fornece provider/trust/identity/repository policy,
   verifica boundary/SCP/RCP/session/endpoint e captura baseline sanitizada.
   Nenhuma permissão administrativa de teste integra a role da fábrica.
4. Para cadeia completa sem tocar a atual, o repo GitHub de teste precisa
   conter cópia revisada dos executores/gates e parâmetros/identidade de
   assinatura ajustados explicitamente em etapa autorizada. Mapear os nomes
   de catálogo aos ECRs isolados; não fingir que o workflow atual aceita um
   prefixo de laboratório livre. Exercer primeiro calls isoladas, depois a
   integração do mesmo OCI aprovado; não publicar conteúdo não validado.
5. Autorizar coleta por observador separado de logs/request IDs/CloudTrail
   disponíveis. O observador não exige grants na role executora. Mascarar
   tokens/credenciais e preservar somente claims/metadados necessários.

### Casos a executar na sessão futura

| Caso | Resultado esperado / cuidado |
| --- | --- |
| Validador oficial dos três documentos | Findings registrados/resolvidos sob revisão; sem confundir com execução |
| Main caller autorizado: publicação reusable, promoção reusable, promoção direta e recovery direto | Assunção com IDs/aud/sub/ref previstos; guardar metadados sanitizados por rota, incluindo presença/ausência de job_workflow_ref |
| Ref/repo/owner não autorizado | Assunção negada; usar job de diagnóstico isolado explícito, nunca acrescentar OIDC às rotas PR/fork da fábrica ou expor tokens de código não confiável |
| PR/fork do código normal | Nenhum configure-aws/id-token nos executores de validação; separado do negativo STS acima |
| Criação/configuração dos repos permitidos | CreateRepository inicial, scanOnPush e mutabilidade; repetir repo existente e confirmar chamada PutImageTagMutability |
| Leitura e cópia do OCI validado nos repos permitidos | Digest índice/plataformas preservados; capturar APIs reais das ferramentas e read-back |
| Imagem, assinatura, provenance, SPDX | Cosign/gh verificam a identidade de laboratório e subjects corretos; bundles/referrers acessíveis sem concessões extras não revisadas |
| Retag para stable de laboratório e recovery | Verificar assinatura/provenance e re-scan; write/read-back exato e evidence stored, sem stable da fábrica |
| Mesma credencial de publicação tentando stable de laboratório | **Pode ser permitido**; registrar risco residual, não anunciar negativo publisher-isolated |
| Outro repo/conta/região, incluindo image-base-p104-denied | Leitura/escrita/configuração negadas no contexto efetivo; sucesso de GetAuthorizationToken não invalida esse negativo |
| DeleteRepository/BatchDeleteImage/SetRepositoryPolicy/lifecycle | Esperada negação pela ausência de grants no perfil isolado. Usar recurso vazio/sentinela descartável expressamente autorizado; nunca release real |
| Perfil sem provisioning, opcional | No código atual, falha esperada em describe/configuração. Não é alternativa transparente; retirada futura exige mudança/revisão do publicador |

Ausência de grant neste JSON não prova negação real se outra policy conceder.
Uma negação só conta com recurso/principal corretos e erro AccessDenied,
não por recurso inexistente, sintaxe, rede ou token expirado. Qualquer permissão
faltante deve ser ligada ao request/fonte e revisada; não ampliar com ecr:*.
Falha de scan upstream é bloqueio do gate, não prova de erro IAM nem autorização
para baixar severidade. Não executar esses testes nesta fatia.

### Evidence e reversão futuras

Guardar hashes/versões das policies efetivamente anexadas, ARN de sessão
sanitizado, repo/ref/workflows, run/attempt, versões de ferramentas,
matriz de resultado por action/recurso, IDs de requests, digest e artifacts
de publicação/signing/provenance/SBOM/promoção/read-back. Registrar condições
externas que impedirem completar qualquer caso.

Se o teste falhar, suspender uso da role de laboratório e preservar evidence.
Operador autorizado restaura configurações de teste pela baseline registrada,
remove anexos/role/recursos somente no escopo descartável aprovado e após
retenção da evidence. Não apagar provider compartilhado nem alterar a role
ou stable da fábrica. A sessão atual não precisa rollback AWS: nada aplicado.

## Pedido técnico para Cloud/IAM

Avaliar os três JSON renderizados com este inventário para os workflows
federados. Containers Products mantém código, testes e o mapeamento; Cloud/IAM
decide conta/recursos/trust/grants, provisionamento, restrições efetivas e
validação; Segurança avalia o risco de escrita/configuração e Sigstore;
GitHub admins confirmam IDs/ref/provider/claims e proteções. Observabilidade
e SLA seguem o [P1-08](m11-m04-operational-health.md), sem novas promessas.

Decisões a devolver com owner e referência autorizada:

- Parâmetros concretos, catálogo permitido e políticas adicionais aplicáveis.
- Compatibilidade com provisioning no job versus mudança futura para
  pré-provisionamento, incluindo scanning/criptografia/tags AWS exigidas.
- Aceitação ou exigência adicional diante do risco PutImage/stable e do poder
  de PutImageTagMutability; não homologar isolamento que não é imposto.
- Aceitação da trust por repo/IDs/main, claims extras reais em todas as rotas
  e necessidade corporativa de limitar o caminho do workflow.
- Quem autoriza/provisiona/observa o laboratório e onde guardar evidence;
  depois, critérios IAM para o primeiro aceite corporativo.

Este handoff alimenta somente IAM do P0-03. Não inicia o checklist corporativo
inteiro. P1-01 PASS limitado, P1-02/P1-03 PENDING e os gaps operacionais do
P1-08 permanecem. Testes/resultados desta fatia na
[spec P1-04](../specs/2026-09-13-iam-permission-contract/evidence.md).
