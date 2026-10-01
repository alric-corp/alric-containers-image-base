# Configuração da Factory

[`config.json`](config.json) é a fonte da verdade para a configuração não secreta
do pipeline. Workflows, promoção/recovery e bootstrap DEV/HOM leem esse arquivo
da revisão em execução. Repository Variables e Environment Variables do GitHub
não participam da resolução desses valores.

| Campo | Uso |
| --- | --- |
| `repository`, `branch`, `subject_prefix` | Repositório, branch de código e identidade OIDC imutável |
| `DEV`, `HOM` | Conta, região, nome da role e bucket de releases de cada ambiente |
| `minimum_soak_hours` | Tempo mínimo após aprovação DEV; pelo menos seis horas |
| `promotion_authorized` | Habilitação de promoção automática e manual para HOM |
| `infra.plan_enabled` | Habilitação do plano AWS em PRs internos para `develop` |
| `infra.plan_role_name`, `infra.apply_role_name` | Roles de infraestrutura, separadas da publicação |
| `infra.backend` | Bucket, região e chave do state Terraform ECR |

Os ARNs são derivados da conta e do nome da role. Não manter uma segunda lista
de ARNs em outro arquivo. Os GitHub Environments `DEV`, `HOM` e
`lab-image-base-infra` continuam impondo os limites de execução, revisão e OIDC.
Credenciais e tokens são obtidos por OIDC ou secrets; nunca armazená-los no JSON.

O carregador `scripts.pipeline.governance.configuration` valida o documento
inteiro antes de emitir outputs/env para o job. Arquivo ausente, chave duplicada,
campo desconhecido, booleano textual, conta inválida ou campos com quebras de
linha interrompem a execução antes da autenticação AWS. Não há fallback para
variáveis do GitHub, valores do shell ou para o arquivo antigo em `policies/release`.

```sh
python3 -B -m scripts.pipeline.governance.configuration --scope DEV
python3 -B -m scripts.pipeline.governance.configuration --scope HOM
python3 -B -m scripts.pipeline.governance.configuration --scope INFRA_PLAN
```

## Habilitar a promoção

Altere `promotion_authorized` para o booleano `true` por PR. Após o merge em
`develop`, o schedule ou dispatch usa a configuração daquela revisão. Essa é
uma mudança de configuração da Factory; a promoção de cada release continua
automática, sem PR e sem rebuild. Recovery continua disponível por dispatch.
Runs históricos conservam a configuração da revisão original; para bloquear
também reexecuções históricas em uma emergência, use o controle IAM da role.

O valor inicial permanece `false`. `infra.plan_enabled` também inicia como
`false`, preservando a desativação indicada pela ausência da antiga variável
`INFRA_PLAN_ROLE_ARN`. Sua habilitação exige concluir a retirada dos caminhos
históricos de Infra PR descrita no runbook; o arquivo não altera trust IAM.

## Migração das variáveis existentes

Primeiro integre os workflows deste PR em `develop`. Até isso ocorrer, a versão
publicada ainda depende das variáveis antigas. Depois do merge, elas podem ser
removidas de Settings → Secrets and variables → Actions e dos Environments:

- Repositório: `AWS_ACCOUNT_ID`, `AWS_REGION`, `AWS_ROLE_ARN`, `DEV_ACCOUNT_ID`,
  `DEV_REGION`, `DEV_ROLE_ARN`, `HOM_ACCOUNT_ID`, `HOM_REGION`, `HOM_ROLE_ARN`,
  `INFRA_PLAN_ROLE_ARN`, `INFRA_APPLY_ROLE_ARN`, `INFRA_BACKEND_REGION`,
  `INFRA_TF_STATE_BUCKET`, `STABLE_PROMOTION_AUTHORIZED`.
- Environments DEV/HOM: `AWS_ACCOUNT_ID`, `AWS_REGION`, `AWS_ROLE_ARN`,
  `RELEASE_BUCKET`.

`infra/lifecycle/configure_github.py` configura as proteções dos Environments e
da branch, sem recriar essas variáveis. Alterar o JSON não provisiona recursos
AWS automaticamente; uma mudança de conta, role ou backend também exige o
correspondente provisionamento e validação.
