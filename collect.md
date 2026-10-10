Factory Distroless — coleta corporativa para preparar o porte
Objetivo e limites
Coletar, no ambiente corporativo já autorizado, os contratos de execução que faltam para preparar e testar o porte no laboratório. Não implementar o porte nesta sessão.
A entrega deve permitir responder como os arquivos versionados, os GitHub Environments, os workflows reutilizáveis e a role AWS se conectam na execução REAL. O resultado é um dossiê de referência, não uma declaração de que o porte já está pronto.
Trabalhar somente em leitura. Não alterar código, arquivos de configuração, IAM, Environments, secrets, variáveis, buckets, policies, state ou referências de branches. Não fazer commit, push, PR, merge, workflow_dispatch, Terraform plan/apply/refresh/import ou instalação global de dependências. Não remover caches ou executar git clean/reset/stash.
Usar somente os acessos já autorizados. Se uma leitura for negada, registrar NOT_OBSERVED; não contornar o bloqueio. O download de logs corporativos é bloqueado: priorizar artifacts JSON já disponíveis, conforme o contrato do projeto.
Antes de qualquer transferência para fora do ambiente corporativo, respeitar a política da empresa. Manter os materiais completos dentro do ambiente autorizado. Preparar para compartilhamento apenas um relatório saneado e os trechos/fixtures cuja divulgação seja permitida. Sanitização não substitui autorização de compartilhamento.
Não copiar repositórios inteiros, secrets, tokens, OIDC JWTs, credenciais AWS/STS, private keys, arquivos .env, .aws/, .git-credentials, kubeconfig, Docker auth, tfstate, planos Terraform binários/integrais, .terraform/ ou dumps indiscriminados de ambiente. O valor de REUSABLE_READ_TOKEN não é necessário.
Decisões já dadas pelo owner
- O fluxo corporativo é preservado; a capacidade da Factory é portável.
- Uma role operacional da Factory e uma inline policy, provisionadas EXTERNAMENTE pela equipe IAM/chamado. A Factory apenas referencia a identidade.
- Nome indicado: itau-github-repo-factory-distroless-v1. Confirmar o uso efetivo; não criar nada.
- .iupipes.yml é o contrato de execução de Infra.
- Root Terraform: ./infra/ecr. S3 deve integrar o root existente; não criar root/state independente.
- Backend e provider são preparados dinamicamente pela pipeline corporativa.
- Não sobrescrever a policy do bucket de state compartilhado.
- O documento registra um fork de setup-backend sem o fluxo SSM/tagging removido e sem put-bucket-policy; conferir a implementação atual.
- Configuração operacional: policies/operations/pipeline-config.json.
- GitHub Variables podem permanecer como fallback/compatibilidade; a precedência EFETIVA depende do carregador e de cada caller.
- Ausência de variables/secrets no Environment não remove sua função de contexto de execução, proteção ou OIDC.
- Ambientes vistos: dev e hom, em minúsculas. Não trocar automaticamente pelos nomes DEV/HOM do LAB.
- Conta, região e identidade devem ser selecionadas por ambiente, sem copiar identificadores LAB.
- A captura de .iupipes.yml mostra sa-east-1, Terraform 1.16.3 e role-duration-seconds: "3600". Conferir esses valores no arquivo atual.
- A captura mostra factory.enabled-environments: [dev, hom]. A presença de configuração de prod não demonstra habilitação de produção.
- Backend, providers, UP2, ARC, mirrors, certificados, regras de promoção e contratos corporativos FROZEN não serão substituídos pelo modelo do LAB.
Prioridade de coleta
Se o tempo for limitado, concluir nesta ordem:
1. Configuração e resolução de precedência.
2. Cadeia completa de Infra e autenticação.
3. Role/policy/trust e configurações reais dos Environments.
4. Baselines, base-sync e uma amostra autorizada dos artifacts SBOM.
5. Dependências e requisitos corporativos de S3/Athena ainda pendentes.
Não repetir investigação que já esteja bem documentada e atual. Registrar apenas confirmação ou delta, com fonte e revisão.
1. Fixar a baseline dos dois repositórios
Repositórios corporativos indicados:
- itau-xj7-container-image-base
- itau-xj7-reusable-workflows-containers-products
Confirmar nomes/owner reais no ambiente. Para cada um, registrar:
- Branch e HEAD local.
- Ref remota correspondente, se consultável sem alterar o checkout.
- Arquivos locais alterados ou não rastreados pertinentes, sem coletar seu conteúdo indiscriminadamente.
- SHA completo do reusable realmente chamado pelo produto. HEAD do reusable não é necessariamente o pin executado.
- Versão/estado do documento de particularidades e do manifesto base-sync.
Não fazer git pull ou checkout para tornar a árvore artificialmente limpa. Preservar o trabalho em andamento. Separar COMMITTED, LOCAL_ONLY e REMOTE_ONLY.
2. Configuração: obter texto completo e rastrear consumidores
Inspecionar, sem modificar:
- .iupipes.yml
- policies/operations/pipeline-config.json
- scripts/pipeline/operations/load_pipeline_config.py
- scripts/pipeline/operations/validate_pipeline_config.py
- scripts/pipeline/release/aws_target.py
- Schema e testes existentes desses componentes.
- docs/m10-pipeline-configuration.md, se presente.
- Steps de resolução chamados pelos workflows, especialmente o step resolve do Skopeo.
Buscar referências a:
- SKOPEO_IMAGE e SKOPEO_IMAGE_FALLBACK
- WOLFI_REPOSITORY_URL
- PROMOTION_MINIMUM_SOAK_HOURS
- STABLE_PROMOTION_AUTHORIZED
- STABLE_PROMOTION_AUTHORIZED_HOM
- custom-role e role-duration-seconds
- pipeline-config.json e load_pipeline_config
Para cada campo, produzir uma matriz:
CAMPO | CONFIG VERSIONADA | VAR/INPUT CANDIDATO | PRECEDÊNCIA REAL | CONSUMIDOR | ARQUIVO:LINHA | EVIDÊNCIA
As telas indicam PROMOTION_MINIMUM_SOAK_HOURS=0 nas Repository Variables, enquanto o JSON declara dev=5 e hom=1. Não escolher nem corrigir valores: demonstrar qual vence em CADA fluxo, inclusive eventual condição if que roda antes do carregador.
Diferenciar:
- Valor ausente.
- String vazia.
- null.
- Booleano false.
- Número 0.
Não tratar false ou 0 como ausência automaticamente. Não inferir precedência pelo nome FALLBACK ou pelo comentário single source of truth.
Se já existirem testes locais puros, usar mocks para verificar conflitos entre JSON e variável. Não executar um script que inicialize SDK, obtenha credenciais ou faça efeitos externos. Se não houver prova segura, documentar análise estática e marcar EFFECTIVE_VALUE_NOT_PROVEN.
Registrar também a origem dos labels de runner: vars.RUNNER_EKS_OD_* ainda aparece no workflow mostrado. Separar variables de runner/plataforma de variables de ferramentas e promoção.
3. Cadeia completa da infraestrutura
Partir de .github/workflows/infra-registry.yml no produto e seguir TODAS as chamadas transitivas relevantes pelos SHAs utilizados.
Nomes indicados no documento, a confirmar:
- registry.yml
- _core-infra-terraform.yml
- _source-control.yml
- promote-environment.yml
- actions/setup-backend/action.yaml
Não inventar arquivos ausentes. Registrar o nome real e seguir seus imports/uses.
Coletar trechos completos de inputs, outputs, needs, if, environment, permissions e steps envolvidos em:
- Parsing de .iupipes.yml.
- Seleção de conta/região/environment.
- Resolução de custom-role e fallback de role.
- Autenticação AWS do plan e do apply.
- Preparação dinâmica de backend/provider.
- Configuração do mirror Terraform.
- Variáveis fornecidas ao root, sem valores confidenciais.
- Comandos init/validate/plan/apply e verificação do plano.
- Plano salvo, checksum, vínculo de commit e passagem entre jobs.
- Read-back e diagnóstico de falhas.
Responder explicitamente:
1. Plan e apply usam a mesma custom-role, ou algum trecho ainda usa a role dinâmica anterior?
2. Em qual job INTERNO do reusable environment é declarado?
3. Onde são escritos backend e provider, e qual root os recebe?
4. Como bucket, key, workspace e lock são determinados por ambiente?
5. A configuração dinâmica preserva ignore_tags para c7n?
6. Quais testes/verificadores atualmente pressupõem um grafo ECR-only?
7. Existe algum gate de count, allowlist ou tipo de recurso que precisará aceitar o módulo S3?
8. O state continua compartilhado dentro de cada execução ambiente/região/repositório, sem confundir states de contas distintas?
9. Como a pipeline captura artifacts antes de falhar?
Não baixar o state nem executar novo plan para responder. Usar código, metadata e evidências existentes autorizadas.
4. Role, trust, Environments e duração
Coletar somente informações de configuração/metadata, com os identificadores saneados na saída compartilhável:
- Nome da role por conta/ambiente, ARN estruturado e MaxSessionDuration.
- Trust policy aplicada, se leitura autorizada.
- Nome e documento da inline policy aplicada, se leitura autorizada.
- Inventário de managed policies/boundary, sem pressupor ausência.
- Fonte das restrições organizacionais relevantes, se conhecida; se não consultável, NOT_OBSERVED.
- Nome exato dos GitHub Environments.
- Deployment branch/tag rules, required reviewers, self-review, bypass e regras adicionais.
- Contexto do token OIDC esperado em cada job.
- Mecanismo real: AssumeRoleWithWebIdentity direto, AssumeRole/chaining ou integração UP2 intermediária.
- Duração solicitada na infraestrutura, publicação, promoção e certificação.
Não coletar JWT OIDC nem credenciais STS. Se houver evidência já disponível de identidade de sessão, extrair somente Account/Arn/UserId, com mapeamento de placeholders na cópia compartilhável.
Não interpretar Environment sem secrets/vars como Environment sem regras ou sem utilização.
Não interpretar uma role de mesmo nome em dev/hom como um único objeto IAM ou um único ARN entre contas. Documentar o mapeamento sem mudar o desenho desejado de uma identidade operacional por conta.
Conferir a diferença entre os 3600 segundos da configuração corporativa e os 10800 do LAB. O comentário YAML não substitui leitura de MaxSessionDuration. Se houver chaining, registrar a cadeia, sem aumentar duração nem alterar trust.
O documento antigo pode mencionar roles separadas. Registrar o delta para a decisão atual de role única, sem apagar o histórico nem afirmar que toda rota já migrou.
5. Fluxos da Factory e pacote mínimo de referência
Inspecionar os workflows existentes que constroem, validam, publicam, promovem e recuperam imagens:
- workflow.yml
- build-base-images.yml
- validate-base-images.yml
- test-runtime-images.yml
- image-trust.yml
- app-certification.yml
- promote-stable.yml / promote-hom.yml
- recover-stable.yml / recover-hom.yml
- pipeline-health.yml
- validate-pipeline-config.yml
Seguir as chamadas relevantes para validate-apko-images.yml, test-runtime-images.yml e scripts no reusable. Coletar somente o que ajuda a mapear interfaces e diferenças; não exportar todo o source sem autorização.
Preservar na documentação:
- Inputs/outputs e artifact names/paths.
- Pins de ferramentas/reusables.
- Correspondência framework/runtime/dev/plataforma.
- Origem do subject OCI e digest esperado fora do próprio SPDX.
- Momento de publicação, geração de SBOM/attestation e registro de resultado.
- Ponto possível de integração analítica depois dos gates, sem modificar os gates.
- Diferenças de nomes entre LAB e corporativo: um nome igual de workflow não garante função igual.
Obter, se autorizado, um conjunto representativo de artifacts já produzidos por uma execução corporativa bem-sucedida. Priorizar o par runtime/dev do golden path disponível: índice e duas plataformas de cada um.
Se não for permitido compartilhar os artifacts, manter os originais no corporativo e gerar uma descrição estrutural ou fixture sintética claramente identificada. Não apresentar documento redigido como byte-idêntico ao original.
Registrar run/attempt/source SHA/reusable SHA, nomes dos artifacts, tamanhos, hashes e contagens separadamente. Não presumir que o corpus corporativo tem as mesmas contagens do LAB.
Sem download de logs bloqueados. Não executar rebuild ou novos workflows apenas para a coleta.
6. Terraform e contrato S3/Athena corporativo
Inspecionar o root infra/ecr, seus módulos locais/externos, variables, outputs, lockfile, políticas relevantes e testes/verificadores. Não copiar .terraform/, tfstate, tfvars de ambiente ou arquivos de credenciais.
Registrar o menor ponto de extensão para adicionar infra/s3 como módulo filho ao root vigente, se compatível com a governança corporativa. Não implementar agora.
Coletar as decisões já existentes sobre:
- Nome/padrão do bucket SBOM e conta/região alvo.
- Tags/classificação obrigatórias e tratamento de tags c7n.
- SSE-S3 versus KMS exigido; se KMS, contrato de uso sem material de chave.
- Versionamento e retenção aprovados para SBOMs e resultados de consultas.
- Acesso por endpoints/VPC/proxy que afete runner, S3 ou Athena.
- Permissões de objeto: PUT, GET, GetObjectVersion e listagem do prefixo.
- Mecanismo de ampliação da inline policy pelo chamado IAM.
- Database/catálogo/workgroup Athena já autorizados ou ainda pendentes.
- Destino de query-results e governança Glue/Lake Formation, se houver.
Não inferir que aws-s3-data-retention: 0 do .iupipes.yml define a retenção do bucket SBOM. Rastrear o consumidor do campo.
Não inferir que aws-statefile-acl: private determina ACLs do bucket SBOM.
A permissão para criar um bucket não demonstra permissão para gravar snapshots ou executar Athena.
Marcar decisões ausentes como PENDING_DECISION, sem inventar defaults corporativos.
7. Runner e dependências do normalizador/executor
Registrar por configuração e, quando permitido, comandos locais de versão sem instalação:
- Labels/sizing ARC dos jobs relevantes e origem das vars.
- Sistema operacional e arquitetura do runner, se disponíveis em evidência existente.
- Python e canal aprovado de distribuição de dependências.
- Disponibilidade das versões requeridas de PyArrow, PyYAML, Boto3/Botocore e AWS CLI.
- Terraform e provider AWS realmente selecionados.
- Docker/Buildx e limitações de acesso a registry.
- Fonte de CA e forma de montar/copiar o certificado para containers.
Não exportar certificados internos ou chaves; descrever caminhos e interfaces basta para o primeiro porte.
Não assumir que a instalação bem-sucedida no LAB garante disponibilidade no mirror corporativo. Registrar pacote/versão/arquitetura que ainda requer validação.
8. Fronteira base-sync e estado do porte
Ler, se presentes:
- base-sync/manifest.json
- base-sync/SKILL.md
- base-sync/port-report.md
- docs/corporate-file-manifest.md
Executar apenas operações comprovadamente de leitura; não executar pull/sync/port que escrevam arquivos.
Registrar:
- Baseline corporativa atual dos dois repositórios.
- Baseline LAB já portada e delta conhecido.
- Arquivos SYNC/adaptação/FROZEN conforme os nomes reais do manifesto.
- Novos caminhos analytics/SQL/schema/tests que ainda não têm classificação.
- Pendências e divergências existentes ANTES desta coleta.
Não chamar todo código analytics de Zona A automaticamente. Ele precisa de classificação própria e revisão das dependências do modelo de release do LAB.
9. Formato do dossiê
Gerar no diretório corporativo autorizado:
1. RELATORIO-COLETA-CORPORATIVA.md — leitura humana, primeiro um resumo de pendências.
2. manifesto-coleta.json — origem, revisão, arquivo e trecho, permissão de compartilhamento e status.
3. trechos-autorizados/ — apenas conteúdo cuja saída foi autorizada e saneada.
4. fixtures-sinteticas/ — se necessárias para testes offline, sempre identificadas como sintéticas.
Na versão compartilhável, usar placeholders CONSISTENTES para contas, bucket names, hostnames internos, Organization IDs, repo/owner IDs, handles e ARNs. Conservar nomes de campos, relações, condições, tipos e estrutura.
Se precisar correlacionar hashes, distinguir source_sha256 e sanitized_sha256; não atribuir o hash original a bytes saneados. O mapa que reverte placeholders para dados reais permanece apenas no ambiente corporativo.
Para cada conclusão, indicar:
- CONFIRMED_FROM_CODE
- CONFIRMED_FROM_EXISTING_RUN
- USER_DECISION
- HISTORICAL_DOCUMENT_ONLY
- INFERENCE
- NOT_OBSERVED / PENDING_DECISION
O resumo final deve responder:
CONFIG_PRECEDENCE:
INFRA_CALL_CHAIN:
PLAN_ROLE_RESOLUTION:
APPLY_ROLE_RESOLUTION:
BACKEND_PROVIDER_GENERATION:
STATE_BOUNDARIES:
ENVIRONMENT_BINDING:
OIDC_AND_SESSION_DURATION:
INLINE_POLICY_CAPABILITIES:
RUNNER_DEPENDENCIES:
SBOM_ARTIFACT_CONTRACT:
S3_REQUIREMENTS:
ATHENA_REQUIREMENTS:
BASE_SYNC_CLASSIFICATION:
MONDAY_BLOCKERS:
SHAREABLE_MATERIALS:
Informar as cinco pendências mais importantes antes de encerrar. Não exigir resolver tudo agora.
Critério de conclusão
O dossiê está pronto quando podemos preparar no LAB uma adaptação com interfaces explícitas, sem inventar a precedência da configuração, o provider/backend corporativo, a role/trust ou o formato de artifacts.
O dossiê não prova uma execução no corporativo, não autoriza apply e não substitui os gates de integração da segunda-feira.
AWS_MUTATIONS: NONE
GITHUB_SETTINGS_CHANGED: NO
SOURCE_FILES_CHANGED: NO
WORKFLOWS_DISPATCHED: NONE
TERRAFORM_STATE_ACCESSED_OR_COPIED: NO
CORPORATE_EXPORT: ONLY_IF_AUTHORIZED
NEXT: TESTAR_ADAPTACAO_NO_LAB_COM_CONTRATOS_SANEADOS


Execute o prompt anexado:
Prompt_segunda_coleta_corporativa_Factory_Distroless.md

Esta é uma coleta complementar à primeira, não uma nova investigação
completa nem uma sessão de implementação.

Priorize:
1. Recuperar o RELATORIO-COLETA-CORPORATIVA.md original.
2. Fixar a baseline do produto, do reusable e das actions realmente consumidas.
3. Identificar o contrato do executor Terraform e o ponto de integração
   do verificador de plano.
4. Coletar evidências disponíveis das dependências do runner e uma amostra
   mínima de SBOM, pelos canais autorizados.

Trabalhe somente em leitura sobre código, GitHub e AWS.
Grave os relatórios localmente, em diretório privado fora dos checkouts.

Não execute Terraform, workflow dispatch, instalação de dependências,
alterações IAM, publicação, promoção ou ingestão S3.

Se uma informação exigir um novo job ou uma permissão indisponível,
registre a limitação e continue as demais frentes. Não contorne bloqueios.

Diferencie claramente:
- Código inspecionado na revisão identificada.
- Comportamento observado em execução.
- Informação apenas relatada na primeira coleta.
- Informação não observada ou dependente de decisão.

Preserve os materiais corporativos no ambiente autorizado.
Uma versão compartilhável deve conter somente conteúdo cuja transferência
seja permitida, com saneamento quando necessário.

Entregue RELATORIO-COLETA-CORPORATIVA-02.md e os índices de evidência
previstos no prompt.

Ao terminar, informe o que já permite preparar a adaptação no LAB
e quais pendências podem ficar para a validação corporativa posterior.
Não implemente correções durante a coleta.
