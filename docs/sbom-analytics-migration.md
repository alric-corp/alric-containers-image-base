# Distroless SBOM Analytics — migração da estrutura histórica

Este procedimento substitui a estrutura histórica, criada durante a prova de conceito, pela implantação ativa descrita em [operação](sbom-analytics-operations.md). O owner autorizou a substituição em 2026-10-11 e a remoção integral da estrutura histórica em 2026-10-12, no deployment AWS pessoal (conta `712107929769`, região `us-east-1`).

> **Estado em 2026-10-13:** os passos 1 a 9 foram executados. O passo 10 aguarda autorização do owner.
>
> - Policy transitória aplicada, com read-back.
> - `Infra - Apply`, run `38207106116`: 6 criados, 1 alterado (`force_destroy`), plano pós-apply sem mudanças.
> - `S3_HOSTED_PROOF=PASS`: publicação e recuperação independente, run `38207794810`. Manifesto `5ff03abfbe76e016a7782851b32c9dedfc377e656e397979e544329feebcb829`, VersionId `7nr06MlNa4COnXXN1TCunE_lx3p5yEj2`.
> - Workgroup e database `sbom_analytics` criados e relidos.
> - `policies/analytics/athena.json` integrado (PR #132).
> - `ATHENA_HOSTED_PROOF=PASS`: rodada `sbom-analytics-v1-r1`.
>   - Plano no run `38280876391`, SHA-256 `e9fb82327a8542486da0153229c79ec07fd17f790052375da84b985deefb354e`, autorizado pelo owner (`owner-20261012-sbom-analytics-v1-r1-e9fb8232`).
>   - Execução no run `38283191994`, com `fresh_round=true`: 18/18 instruções verificadas, 454387 bytes examinados, contagens iguais às esperadas e snapshot inalterado. Saldo da rodada: zero.
> - **Remoção do bucket histórico:** `Infra - Apply`, run `38319342150`, revisão `f4935db`.
>   - O owner revisou o `plan.json` e aprovou o apply: 6 recursos `module.sbom.*` excluídos.
>   - O plano pós-apply veio sem mudanças (fase `steady`, 54 `no-op`).
>   - A ausência foi confirmada pela AWS: `HeadBucket` 404 e `NoSuchBucket` nas leituras de versões.
> - **Reconciliação IAM** (passo 9), aplicada em 2026-10-13 com autorização do owner:
>   - role central: um único `PutRolePolicy` do documento versionado; o read-back tem 14 statements e 6193 caracteres;
>   - root `infra/iam`: apply do plano salvo, com uma única alteração em `aws_iam_role_policy.infra["apply"]`, seguido de um apply `-refresh-only`. O state local reconciliado é o serial 8; o serial 5 ficou como backup, fora do Git;
>   - `plan -detailed-exitcode` retornou 0, o Access Analyzer deu `PASS` nos três documentos e nenhuma policy da conta cita o ARN do bucket excluído.
> - **Passo 10:** o workgroup e o database `poc_distroless_sbom` (duas tabelas e três views no Glue) continuam existindo e aguardam autorização de remoção. Não têm uso operacional: nenhuma role tem grant sobre eles, e o CloudTrail registra somente leituras administrativas desde 2026-10-11.
> - **Passo 11:** esta revisão retira o código de transição, independente do passo 10: os recursos Glue e Athena não são gerenciados por Terraform.
> - O passo 12 vem depois dos passos 10 e 11.

## Nomes: antigo → novo

| Tipo | Antigo | Novo |
| --- | --- | --- |
| Bucket S3 | `alric-distroless-sbom-712107929769-us-east-1` | `distroless-sbom-analytics` (nome exato, configurado; sem conta, região ou organização) |
| Prefixo de dados | `sbom-analytics/poc-v1/` | `sbom-analytics/v1/` |
| Prefixo de resultados | `query-results/poc-v1/` | `query-results/sbom-analytics-v1/` |
| Workgroup e database | `poc_distroless_sbom` | `sbom_analytics` |
| Prefixo de tabelas/views | `poc_snapshot` | `sbom_snapshot` |
| Endereços Terraform | `module.sbom.*` (6) | `module.sbom_analytics.*` (6) |
| Workflows | `sbom-analytics-lab-poc.yml` e `sbom-analytics-athena-lab-poc.yml` | `sbom-analytics-s3.yml` e `sbom-analytics-athena.yml` |
| Concorrência | `sbom-analytics-lab-poc` e `sbom-analytics-athena-lab-poc` | `distroless-sbom-analytics` |
| Configurações | `policies/analytics/lab-poc.json` e `athena-lab-poc.json` | `policies/analytics/s3.json` e `athena.json` |
| Executores | `poc.py` e `athena_poc.py` | `s3_run.py` e `athena_run.py` |
| Dependências | `requirements-sbom-poc.txt` | `requirements-sbom-analytics.txt` |
| Exemplos AWS | `docs/examples/sbom-lab/` | `docs/examples/sbom-analytics/` |

O nome do bucket vem de `policies/pipeline/config.json` (`analytics.bucket`) e entra no Terraform como `sbom_bucket_name`. O nome é global no S3: o preflight de `readback.py` confirma a ausência com `ExpectedBucketOwner` antes do apply. Se o nome pertencer a outra conta, a execução para e nenhum nome alternativo é escolhido automaticamente.

## Identificadores que não mudam

| Identificador | Motivo |
| --- | --- |
| Rodada `lab-sbom-athena-v1`, runs `38031426478` e `38117928589`, 18/18 instruções, saldo zero | Prova histórica real. É recusada como rodada nova. |
| Rodada `sbom-analytics-v1-r1`, runs `38280876391` (plano) e `38283191994` (execução), 18/18 instruções, saldo zero | Prova hospedada do bucket definitivo. Encerrada: um novo `fresh_round` com ela é recusado porque os cinco nomes já existem no catálogo. |
| `tests/fixtures/sbom-analytics/historical-poc-round/`, `lab-frozen-plan.*` e os journals e fixtures Athena | Replays byte a byte do histórico |
| Endereços `module.sbom.*` | Saíram do state no apply de remoção (run `38319342150`, serial 6). A revisão final retirou `infra/s3-legacy`, as constantes `LEGACY_*` e as fases `transition` e `removal` do verificador; o módulo, os endereços e o nome do bucket substituído continuam recusados. |
| Repositório `alric-corp/alric-containers-image-base`, tag `Source` e guards dos workflows | Identidade real do deployment e da proveniência. O núcleo recebe o repositório como entrada. |
| Environment `lab-image-base-infra` | Identidade OIDC de implantação já existente (subject da trust) |
| Role `itau-github-repo-factory-distroless-v1` e policy `factory-distroless-v1` | As mesmas entidades. Só os statements de analytics mudam. |
| Backend e state, workspace, `.tflock` e ECR | Fora da migração. O plano exige no-op. |
| Root `infra/iam` (state local) e suas duas roles | As roles, as trusts e os nomes das inline policies não mudam. Só sai o statement `ExactSbomAnalyticsBucket`; ver [reconciliação IAM](#reconciliação-iam). |

## Dados

O batch não muda: `2da32bfa…`, com 19 objetos e 630308 bytes (seis SPDX e dois Parquet). O `snapshot_id` depende do destino e foi recalculado para o bucket definitivo: `8439add73fe20e08d45292dddc62b360b6ccaa372395818aa0a5cf8a910eb507`. O manifesto e os VersionIds vêm da publicação real.

## Passos

A nova prova hospedada (S3 e Athena) passa **antes** de qualquer destruição dos recursos históricos.

1. **Revisão de transição** (PR #131):
   - o bucket novo é criado com proteção total;
   - no bucket antigo, só `force_destroy` muda para `true`;
   - `verify_plan.py` só aceita essa forma, na fase `transition`;
   - a policy inline transitória concede os recursos novos e a remoção restrita ao bucket antigo: `ListBucketVersions`, `DeleteBucketPolicy`, `DeleteBucket` e `DeleteObjectVersion`.
2. **Policy inline transitória**, aplicada pelo administrador com comparação antes e read-back depois.
3. **`Infra - Apply`**, com aprovação no environment `lab-image-base-infra`. O preflight confirma que o nome está livre, e o plano pós-apply precisa vir sem mudanças.
4. **Publicação do snapshot** em `sbom-analytics-s3.yml`, com read-back e recuperação independente (`S3_HOSTED_PROOF`).
5. **Workgroup e database `sbom_analytics`**, criados pelo administrador a partir de [`docs/examples/sbom-analytics/`](examples/sbom-analytics/) e relidos.
6. **`policies/analytics/athena.json`**, em PR próprio, com o SHA-256 e o VersionId do manifesto lidos de volta. Esse PR não remove `module.sbom`.
7. **Rodada SQL** `sbom-analytics-v1-r1`:
   - plano;
   - autorização pelo hash do plano;
   - execução com `fresh_round=true` (`ATHENA_HOSTED_PROOF`).
8. **Revisão de remoção**, só depois de `S3_HOSTED_PROOF=PASS` e `ATHENA_HOSTED_PROOF=PASS`:
   - remove o bloco `module "sbom"`;
   - `verify_plan.py` deriva a fase `removal` da configuração e do state anterior e só aceita:
     - `delete` nos seis endereços antigos, com a identidade, a policy e o `force_destroy=true` gravados no state;
     - `no-op` em todo o resto, inclusive em `module.sbom_analytics`, que precisa já estar no state;
     - nenhuma criação, atualização, `forget`, `moved` ou import;
   - o owner revisa o `plan.json` do job de plano do `Infra - Apply` e só então aprova o job de apply;
   - o plano pós-apply precisa vir sem mudanças (fase `steady`).
9. **Reconciliação IAM:** nenhum grant sobre o bucket excluído, em nenhuma origem. Os documentos e a aplicação estão em [reconciliação IAM](#reconciliação-iam).
10. **Remoção dos objetos Glue e Athena históricos** pelo administrador, via API e sem SQL.
11. **Revisão final:** retira `infra/s3-legacy`, as constantes `LEGACY_*`, a fase de remoção e os caminhos operacionais obsoletos.
12. **Drift zero:** `Infra - Apply` sem mudanças sobre a revisão final. Também confirma a ausência dos recursos históricos e a preservação das provas hospedadas.

## Reconciliação IAM

Depois da exclusão do bucket, a leitura de 2026-10-12 de todas as roles, usuários, grupos e policies gerenciadas da conta encontrou o ARN antigo em duas inline policies. A terceira linha da tabela é a outra role do root `infra/iam`, que compartilha o mesmo state:

| Origem | Ownership | Na AWS | Documento final | Aplicação |
| --- | --- | --- | --- | --- |
| Role `itau-github-repo-factory-distroless-v1`, inline `factory-distroless-v1` | Operador, fora do Terraform | 16 statements: o ARN antigo em `ExactSbomAnalyticsBucket` e os dois `TransitionalLegacy*` | [`factory-distroless-v1.inline-policy.json`](../policies/aws/factory-distroless-v1.inline-policy.json): 14 statements, só o bucket definitivo | `PutRolePolicy` do documento versionado |
| Role `alric-github-repo-1360616627-infra-apply`, inline `image-base-infra-apply` | Root `infra/iam`, state local | 6 statements. O sexto, `ExactSbomAnalyticsBucket` sobre o ARN antigo, foi posto fora do state em 2026-10-09 | 5 statements, iguais ao state original | `terraform apply` de um plano salvo |
| Role `alric-github-repo-1360616627-infra-plan`, inline `image-base-infra-plan` | Root `infra/iam`, state local | 5 statements, sem grant SBOM | Inalterado | Nenhuma (`no-op`) |

**Resultado em 2026-10-13:** a central voltou com 14 statements e a `infra-apply` com 5, iguais aos
documentos finais; RoleIds, trusts, durações e a ausência de attachments não mudaram.

Nenhum workflow assume a role `infra-apply` desde a troca para a role central (o escopo `INFRA_APPLY` resolve para a central). O CloudTrail registra a última assunção em 2026-10-09T13:46Z. Os privilégios removidos **não** são transferidos ao bucket definitivo.

A revisão anterior de `infra/iam` declarava o statement para as duas roles. Aplicada como estava, ela **acrescentaria** o grant sobre o bucket excluído à role `plan`. Por isso o root só é aplicado a partir desta revisão.

### Antes de qualquer escrita

- **Sessão:** `Tomas-Instructor` na conta `712107929769`.
- **Revisão:** checkout limpo do commit integrado e aprovado.
- **Janela exclusiva:** nenhuma outra operação IAM, `Infra - Apply` ou workflow de dados em execução.
- **Leituras, em diretório privado fora do Git:** para cada role, `get-role`, `get-role-policy`, `list-role-policies` e `list-attached-role-policies`.
- **Identidade das roles inalterada:** RoleId, trust, `MaxSessionDuration`, path, boundary e attachments iguais aos do inventário.
  - Central: `AROA2LTHQWCU2N3H2OE3L`, 10800 s.
  - `infra-apply`: `AROA2LTHQWCUSXETEFJ5E`, 3600 s.
  - `infra-plan`: `AROA2LTHQWCUTNWKQQSOM`, 3600 s.
- **Documento em vigor igual à pré-imagem**, por comparação de JSON desserializado:
  - Central: o documento da revisão anterior, `git show f4935db:policies/aws/factory-distroless-v1.inline-policy.json`.
  - `infra-apply`: o state original mais `ExactSbomAnalyticsBucket`, igual ao `PutRolePolicy` de 2026-10-09 registrado no CloudTrail.
- **Access Analyzer**, com resultado `PASS` em cada documento final:
  - `validate-policy` sem findings;
  - `check-no-new-access` contra o documento em vigor;
  - `check-access-not-granted` para `arn:aws:s3:::alric-distroless-sbom-712107929769-us-east-1` e `/*`.

Qualquer divergência interrompe a operação. O estado é preservado e reportado, e nada é sobrescrito.

### Role central

```sh
aws iam put-role-policy --role-name itau-github-repo-factory-distroless-v1 \
  --policy-name factory-distroless-v1 \
  --policy-document file://policies/aws/factory-distroless-v1.inline-policy.json
```

É o mesmo nome de policy. Trust, duração e attachments não são tocados. Também não há chamadas para criar, apagar ou anexar policies.

### Root `infra/iam`

1. Preservar fora do Git uma cópia do state local original, `infra/iam/terraform.tfstate` do clone do operador:
   - serial 5;
   - lineage `0f5d02b5-f79a-2bcf-865c-1bd56d700ff6`;
   - Terraform 1.15.8.
   Sem esse state, ou com outro, a operação para. Não se usa import, `state rm` nem state novo.
2. Com o lockfile do bootstrap (`hashicorp/aws` 6.64.0):
   ```sh
   terraform -chdir=infra/iam init -input=false -lockfile=readonly
   terraform -chdir=infra/iam plan -input=false -var-file=lab.tfvars -out=reconcile.tfplan
   terraform -chdir=infra/iam show -json reconcile.tfplan > reconcile-plan.json
   ```
3. O plano só é aceito com estas ações:
   - `update` in-place em `aws_iam_role_policy.infra["apply"]`, removendo apenas `ExactSbomAnalyticsBucket`;
   - `no-op` nas duas `aws_iam_role.infra` e em `aws_iam_role_policy.infra["plan"]`;
   - nenhuma criação, exclusão, substituição, import ou `moved`.
   O refresh registra drift no atributo computado `inline_policy` das roles. Ele não está configurado e não gera ação. Qualquer outra forma, em especial recriação de role, interrompe a operação.
4. `terraform -chdir=infra/iam apply reconcile.tfplan`. Com Terraform 1.15.8 e backend local, o apply
   desse plano salvo, com uma alteração, gravou dois snapshots: o serial passou de 5 para 7, com o backup
   local. O plano seguinte mostrou drift só no atributo computado `inline_policy`; um apply de plano
   `-refresh-only` o absorveu e levou o state ao serial 8, promovido a canônico. Valide o resultado pelo
   conteúdo do state, não por um serial fixo.

### Read-back e drift

- **Documentos:**
  - a central volta igual ao documento versionado;
  - a `infra-apply` volta com os 5 statements do state original;
  - a `infra-plan` fica inalterada.
- **Roles:** as três mantêm RoleId, trust, duração, inventário de inline policies e ausência de attachments.
- **Terraform:** `terraform -chdir=infra/iam plan -detailed-exitcode` retorna 0.
- **Access Analyzer:** `check-access-not-granted` sobre o bucket excluído dá `PASS` nos três documentos lidos de volta.
- **Sem compare-and-swap:** `PutRolePolicy` não tem essa garantia, e a janela exclusiva e as leituras antes e depois não substituem uma trava.
- **Divergência no read-back:**
  - não há reaplicação automática;
  - o resultado é preservado e reconciliado por leitura;
  - nenhum grant sobre o bucket excluído é reintroduzido como rollback.

## Rollback

- **Até o passo 8:** o bucket antigo continua intacto, e basta reverter o código.
- **Depois do apply do passo 8:** a reconstrução usa os bytes preservados (plano congelado e evidências privadas). Não há recuperação do bucket apagado.
- **Passo 9:** não há rollback que reintroduza grants sobre o bucket excluído. Os documentos anteriores ficam no histórico e nas evidências privadas, sem reaplicação.
