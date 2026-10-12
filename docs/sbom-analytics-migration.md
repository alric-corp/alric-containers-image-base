# Distroless SBOM Analytics — migração da estrutura histórica

Este procedimento substitui a estrutura histórica, criada durante a prova de conceito, pela implantação ativa descrita em [operação](sbom-analytics-operations.md). O owner autorizou a substituição em 2026-10-11 e a remoção integral da estrutura histórica em 2026-10-12, no deployment AWS pessoal (conta `712107929769`, região `us-east-1`).

> **Estado em 2026-10-12:** os passos 1 a 7 foram executados. O passo 8 está em revisão.
>
> - Policy transitória aplicada, com read-back.
> - `Infra - Apply`, run `38207106116`: 6 criados, 1 alterado (`force_destroy`), plano pós-apply sem mudanças.
> - `S3_HOSTED_PROOF=PASS`: publicação e recuperação independente, run `38207794810`. Manifesto `5ff03abfbe76e016a7782851b32c9dedfc377e656e397979e544329feebcb829`, VersionId `7nr06MlNa4COnXXN1TCunE_lx3p5yEj2`.
> - Workgroup e database `sbom_analytics` criados e relidos.
> - `policies/analytics/athena.json` integrado (PR #132).
> - `ATHENA_HOSTED_PROOF=PASS`: rodada `sbom-analytics-v1-r1`.
>   - Plano no run `38280876391`, SHA-256 `e9fb82327a8542486da0153229c79ec07fd17f790052375da84b985deefb354e`, autorizado pelo owner (`owner-20261012-sbom-analytics-v1-r1-e9fb8232`).
>   - Execução no run `38283191994`, com `fresh_round=true`: 18/18 instruções verificadas, 454387 bytes examinados, contagens iguais às esperadas e snapshot inalterado. Saldo da rodada: zero.
> - **Revisão de remoção:** o bloco `module "sbom"` saiu do root `infra/ecr`. Nada foi destruído até o `Infra - Apply` aprovado.
>
> Os passos 9 em diante são **futuros**. Os recursos históricos continuam existindo.

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
| `infra/s3-legacy` e os seis endereços `module.sbom.*` | Na revisão de remoção, o root não declara mais `module "sbom"`, e os seis endereços continuam no state até o apply. É assim que o Terraform destrói exatamente o bucket antigo, com `force_destroy=true` vindo do state. `infra/s3-legacy`, as constantes `LEGACY_*` e a fase `removal` do verificador saem só na revisão final. |
| Repositório `alric-corp/alric-containers-image-base`, tag `Source` e guards dos workflows | Identidade real do deployment e da proveniência. O núcleo recebe o repositório como entrada. |
| Environment `lab-image-base-infra` | Identidade OIDC de implantação já existente (subject da trust) |
| Role `itau-github-repo-factory-distroless-v1` e policy `factory-distroless-v1` | As mesmas entidades. Só os statements de analytics mudam. |
| Backend e state, workspace, `.tflock` e ECR | Fora da migração. O plano exige no-op. |
| Root legado `infra/iam` | A role `alric-github-repo-1360616627-infra-apply` ainda tem `ExactSbomAnalyticsBucket` sobre o ARN do bucket antigo (lido em 2026-10-12). Pendência explícita, fora do root `infra/ecr`. Não é alterada nesta migração. |

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
9. **Remoção dos objetos Glue e Athena históricos** pelo administrador, via API e sem SQL.
10. **Revisão final:**
    - retira `infra/s3-legacy`, as constantes `LEGACY_*`, a fase de remoção, os statements transitórios e os caminhos operacionais obsoletos;
    - o administrador aplica a policy final, sem nenhum grant sobre o bucket antigo.
11. **Drift zero:** `Infra - Apply` sem mudanças sobre a revisão final. Também confirma a ausência dos recursos históricos e a preservação das provas hospedadas.

## Rollback

- **Até o passo 8:** o bucket antigo continua intacto, e basta reverter o código.
- **Depois do apply do passo 8:** a reconstrução usa os bytes preservados (plano congelado e evidências privadas). Não há recuperação do bucket apagado.
