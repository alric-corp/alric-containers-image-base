# EVIDENCE — P1-04

## Baseline

Raiz do checkout do repositório alric-containers-image-base. Árvore inicial
limpa em docs/operational-readiness-slo, HEAD
`9ef5e7d56905ae6ab6867ff6427abfcefc5b22ff`.
PR #59 consultado via gh: MERGED em `2026-09-13T23:37:46Z`, base main,
merge `dd037cc9a8dc2b3585d9941666ba508ecca87c9a`. Fetch autorizado e avanço
fast-forward da main; HEAD == origin/main == merge, ancestralidade confirmada.
Origin fetch/push: `https://github.com/alric-corp/alric-containers-image-base.git`.
Sem replicação manual, descarte ou alteração não relacionada.

Biblioteca canônica: `https://github.com/alric-corp/alric-containers-reusable-workflows.git`
em fetch/push, main local limpa `b574bd487e7c598c12ab6c6e584a523e03caaa45`.
Contrato consumido pelo produto: checkout `.reusable-workflows` no SHA
`7a9b055a462eeb8552d3404c26538b44e8ccd83f`; não confundir com main irmã.

## Autorização e método

LOCAL-EXECUTE para artefatos propostos/testes; pesquisa oficial e GitHub GET.
Nenhuma chamada autenticada AWS nesta sessão, nenhuma alteração IAM/ECR.
Lidos AGENTS/CLAUDE, Constitution/Capability Matrix/PROJECT/WORKFLOW, RFC,
ADRs 0002/0003, contratos de consumo/operação/reuso, policies e fontes de
release. O roadmap consolidado de 11/09 é histórico conceitual: sua hipótese
de split de roles não substitui a análise atual de PutImage. plan/ não virou backlog.

Pesquisa auxiliar de código/ECR/OIDC somente leitura; não é revisão
independente. Não havia spec P1-04 equivalente. O escopo foi registrado
em spec/acceptance antes de criar os templates e o utilitário local.

## Inventário e conclusões rastreáveis

[Contrato canônico](../../docs/iam-permission-contract.md) e
[inventário JSON](../../policies/aws/proposals/factory-permissions/inventory.json):
18 operações, seis Sids, 12 actions ECR explícitas nas identity policies,
mais AssumeRoleWithWebIdentity exclusivamente na trust. Cada operação contém
workflow/job/step, comando, APIs, actions, recurso, condição, justificativa
quando necessária e fontes locais/oficiais. Classificações não se confundem:

| Origem | O que foi obtido |
| --- | --- |
| OBSERVED_CODE | AWS CLI e ferramentas nos workflows/helpers da baseline, callers/pins e executores consumidos |
| OFFICIAL_DOCUMENTATION | API → IAM, recursos/condições, claims extras, comportamento OCI de ferramentas; fontes abaixo e no inventário |
| OBSERVED_IN_EVIDENCE | Trust read-back histórico de 10/09; publicação/assinatura/provenance/SBOM e promoção nos runs já registrados em P1-05/P1-09. Não são teste dos novos JSON |
| NOT VERIFIED | Trace de APIs de cada cliente sob a proposta, policy efetiva atual, claims extras emitidas/autorizadas em cada rota e restrições corporativas |

Publicador inclui DescribeRepositories, CreateRepository condicional e
PutImageTagMutability incondicional. scanOnPush é parâmetro do create,
não outra chamada StartImageScan/PutImageScanningConfiguration. Templates
execution/provisioning devem ser considerados juntos para o código atual.
Pré-provisionar sozinho não elimina o request de mutabilidade.

PutImage permite escrever tags no mesmo ARN; nenhuma condition key IAM por
image tag é oferecida na referência ECR consultada. Separar nomes de roles
não reserva stable. O grant PutImageTagMutability também não restringe os
valores de configuração aos que o workflow envia. Riscos preservados na
proposta; não há negativo fictício de publisher incapaz de mover stable.

ListImageReferrers é API autorizada por ecr:BatchGetImage. GetAuthorizationToken
é a única exceção identity Resource estrela; demais ações têm ARNs exatos e
aws:RequestedRegion. Não há grants por precaução de delete, IAM, PassRole,
KMS, S3, Signer, CloudWatch, lifecycle ou repository-policy management.
Aquisição S3 opcional de certificados é um alvo manual não usado pelos jobs;
URL S3 pré-assinada de layer ECR não cria essa necessidade IAM.

Trust ativa não foi alterada. Proposta mantém aud/sub exatos e acrescenta
repository, repository_id, repository_owner_id e ref. AWS documenta suporte
a essas claims na trust, sem disponibilidade das extras na sessão ECR.
job_workflow_ref é suportada, mas não presumida em dispatch direto. Recovery
não tem if main no job: a trust é a fronteira de ref nesse caminho.
Policy efetivamente anexada, boundaries/SCP/RCP/endpoint e identidade
corporativa permanecem desconhecidos; não foram inferidos de execuções antigas.

## Fontes oficiais e versões

Consultas externas somente leitura em 13/09/2026, horário local São Paulo,
até 14/09/2026 UTC nesta sessão. Nenhuma consulta operacional nova de runs,
artifacts ou AWS; GitHub consultado para PR #59 e fetch da base.

- [Service Authorization Reference ECR](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ecr.html), [PutImage](https://docs.aws.amazon.com/AmazonECR/latest/APIReference/API_PutImage.html), [retag](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-retag.html), [mutabilidade](https://docs.aws.amazon.com/AmazonECR/latest/APIReference/API_PutImageTagMutability.html): escopo repository e ausência de condição por tag de imagem. A API atual confirma exclusões, apesar de frase antiga contraditória no início do guia de mutabilidade.
- [Push IAM](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-push-iam.html), [ListImageReferrers](https://docs.aws.amazon.com/AmazonECR/latest/APIReference/API_ListImageReferrers.html), [GetDownloadUrlForLayer](https://docs.aws.amazon.com/AmazonECR/latest/APIReference/API_GetDownloadUrlForLayer.html): operação composta de registry e mapeamento de referrers. APIs individuais de upload/create estão no inventário.
- [IAM OIDC condition keys](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_iam-condition-keys.html#condition-keys-wif) e [anúncio AWS de claims extras](https://aws.amazon.com/about-aws/whats-new/2026/01/aws-sts-supports-validation-identity-provider-claims/): suporte GitHub além de aud/sub e tabela Available in session. O guia GitHub AWS ainda contém aviso antigo de custom claims; para suporte IAM prevaleceu a referência AWS, sem extrapolar para claims arbitrárias.
- [Claims GitHub](https://docs.github.com/en/actions/reference/security/oidc), [reusables](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-with-reusable-workflows): caller versus job_workflow_ref, formato immutable subject; nenhum token foi solicitado ou exposto.
- [Avaliação de policies](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html), [repository policies](https://docs.aws.amazon.com/AmazonECR/latest/userguide/repository-policies.html), [RequestedRegion](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html#condition-keys-requestedregion), [GetCallerIdentity](https://docs.aws.amazon.com/STS/latest/APIReference/API_GetCallerIdentity.html): separação das camadas, token e identidade da sessão.
- [ValidatePolicy CLI](https://docs.aws.amazon.com/cli/latest/reference/accessanalyzer/validate-policy.html), [simulador](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_testing-policies.html), [quotas](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_iam-quotas.html): plano oficial e limites; nenhum desses serviços foi executado.

| Componente | Versão/fonte examinada e limite |
| --- | --- |
| configure-aws-credentials | SHA cbe3b392738ccf3f987d68400dafcf4b0624a56c, comentário v6; fontes oficiais assumeRole.ts/CredentialsClient.ts confirmam WebIdentity/GetCallerIdentity, sem grant adicional para este último |
| amazon-ecr-login | SHA 03f1aad4c6c7ffd436567f42f9384779290529bd, comentário v2; index.js oficial usa SDK GetAuthorizationToken privado |
| Skopeo | 1.22.2, imagem v1.22.2-immutable por digest 4a16d57b37617a04b3d643079a477a2848efe892dffcdf0ce56df4262b65f810; copy/inspect vistos no workflow |
| Cosign | Installer 6f9f17788090df1f26f669e9d70d6ae9567deba6 instala v3.0.6; [WriteReferrer](https://github.com/sigstore/cosign/blob/v3.0.6/pkg/oci/remote/write.go) publica bundle/config/manifests OCI. Não inferir fallback .sig de comentário antigo |
| Provenance | attest-build-provenance 4d101475d8b20a2381f78447822ac1eab6504dd8 delega attest 508db95dd578ae2727ebd6217d5ba78e4fbda05d v4.2.1; fonte oficial src/attest.ts usa attachArtifactToImage, GitHub API distinta de ECR |
| Shared / Trivy | Executores 7a9b055a462eeb8552d3404c26538b44e8ccd83f; action Trivy eea2d2f4c4102ded74204e4131c1417f444ae3fc, versão 0.72.0 no objeto Git fixado |
| Docker/Buildx, AWS CLI, gh | Vêm do runner ubuntu-latest, sem novo pin; versão efetiva futura deve ser coletada. gh 2.100.0 é observação histórica P1-05, não nova execução desta entrega |

Históricos lidos: [renomeação](../../docs/evidence/repository-rename-2026-09-10.json),
[lifecycle](../../docs/evidence/ecr-lifecycle-2026-09-10.json),
[Sigstore](../2026-09-13-sigstore-trust-model-adr/evidence.md),
[reconciliação](../2026-09-13-consumer-contract-rfc-refresh/evidence.md) e
[operação](../2026-09-13-operational-readiness-slo/evidence.md). Não reescritos
nem tratados como prova de autorização IAM com a proposta atual.

## Artefatos concretos e validação local

Templates JSON execution/provisioning/trust, fixture sintética e inventário
em [proposals](../../policies/aws/proposals/factory-permissions/README.md).
Renderizador local gera somente três documentos fora do checkout, sem
AWS/apply. A fixture tem dois ECRs, conta 111122223333 e repo GitHub sintético;
Cloud deve fornecer parâmetros reais e lista aprovada, não adotar a fixture.
Com o catálogo inteiro e conta sintética, tamanho compacto: execution 3018,
provisioning 2751 e trust 729 caracteres. Não são policies anexadas; quotas
e grants agregados da role real precisam ser conferidos por Cloud.

Checks executados em 13/09/2026 São Paulo (14/09/2026 UTC, após 00:01),
macOS arm64; equivalentes aos alvos de make check. Logs locais fora do repo
`/private/tmp/p104-local-*.log`; nenhum resultado copiado da entrega P1-08.

| Comando | Resultado obtido |
| --- | --- |
| python3 -B -m unittest tests.unit.pipeline.governance.test_iam_proposal -v | PASS, exit 0; 23 testes em 0,315s |
| python3 -B -m unittest tests.unit.pipeline.governance.test_consumer_documentation -v | PASS, exit 0; 6 testes em 0,122s |
| make test-unit | PASS, exit 0; 323 testes em 5,743s |
| make test-integration | PASS, exit 0; 24 testes em 11,844s |
| make lint-local | PASS, exit 0; 52 pins/49 arquivos, catálogo 17 com uma exclusão |
| make lint-shared | PASS, exit 0; contrato shared e retenção/cron em 11 workflows |
| make lint-workflows | PASS, exit 0; actionlint local/shared |
| python3 -B tools/check_ai_context.py | PASS, exit 0 |
| git diff --check | PASS, exit 0 |
| render_iam_proposal.py com parameters.fixture.json | PASS, exit 0; três JSON em /private/tmp/p104-reviewed-fixture-output, sem chamada AWS |

Os 23 específicos e seis documentais já estão incluídos nos 323 unitários;
não somá-los novamente. O módulo novo inclui links do contrato/spec,
comandos Bash por sintaxe, rastreabilidade e tamanho/escopo dos templates.

Negativos executados em cópias/fixtures temporárias: account/region inválidos,
wildcards, repo fora do padrão ou duplicado, nomes/IDs/ref/sub divergentes,
PR/environment como subject não suportado por esta proposta, campo ausente
ou desconhecido, JSON malformado/duplicado e placeholder desconhecido/embutido.
CLI rejeita saída dentro do checkout, inclusive via symlink, e não sobrescreve
destino existente. Invariantes conferem actions/Sids explícitos, fases
disjuntas, estrela só no token e ausência de conditions fictícias.
Isso verifica forma/conteúdo versionado, **não decide Allow/Deny na AWS**.

## Estados remotos e limitações

| Estado | Resultado |
| --- | --- |
| LOCAL_STRUCTURE_VALIDATED | PASS |
| AWS_VALIDATOR_CHECKED | NOT RUN |
| AWS_SIMULATION_CHECKED | NOT RUN |
| SANDBOX_EXECUTION_VERIFIED | NOT RUN para a proposta |
| CORPORATE_ACCEPTED | EXTERNAL_PENDING / NOT VERIFIED |

Não houve tentativa de obter grants extras, consulta IAM autenticada,
simulação ou aplicação. Permissões de acesso ao validador não foram sondadas;
não se afirma uma falha do ambiente. Validação/execução futuras estão no
contrato, com conta/role/repos isolados a autorizar e operador separado.
JSON/local tests não comprovam política efetiva, suporte de claims emitidas
em todos os caminhos ou isolamento por tag. O renderizador verifica formato,
não existência de recursos, código de região real nem schema IAM completo.

## Arquivos e escopo

19 arquivos: README, RFC, docs/README, policies/README; novo contrato IAM;
README/inventário/fixture/três templates no diretório proposals; seis docs
desta spec; tools/render_iam_proposal.py; test_iam_proposal.py.
Trust ativa, release policies, workflows, scripts/pipeline, shared, ADRs e
outras specs preservados. A mudança de README remove duas recomendações
genéricas ecr:* em favor do contrato concreto, sem mudar autorização ativa.
Sem staging/commit/push/PR, IAM/ECR/infra, dispatch/rerun ou notificações.
P1-01 hosted PASS limitado; P1-02/P1-03 PENDING; P1-08 aceite integral pendente.
Revisão independente posterior pelo Claude Code; nenhuma auto-aprovação.
