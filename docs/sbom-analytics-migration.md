# Distroless SBOM Analytics — migração da estrutura histórica

Este procedimento substitui a estrutura histórica, criada durante a prova de conceito, pela implantação ativa descrita em [operação](sbom-analytics-operations.md). O owner autorizou a substituição em 2026-10-11, no deployment AWS pessoal (conta `712107929769`, região `us-east-1`).

> **Estado:** todos os passos abaixo são **futuros** até serem executados e registrados. Nesta revisão, os recursos históricos continuam existindo. As descrições e os nomes novos ainda não foram aplicados na AWS.

## Nomes: antigo → novo

| Tipo | Antigo | Novo |
| --- | --- | --- |
| Bucket S3 | `alric-distroless-sbom-712107929769-us-east-1` | `alric-distroless-sbom-analytics-712107929769-us-east-1` |
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

## Identificadores que não mudam

| Identificador | Motivo |
| --- | --- |
| Rodada `lab-sbom-athena-v1`, runs `38031426478` e `38117928589`, 18/18 instruções, saldo zero | Prova histórica real. É recusada como rodada nova. |
| `tests/fixtures/sbom-analytics/historical-poc-round/`, `lab-frozen-plan.*` e os journals e fixtures Athena | Replays byte a byte do histórico |
| `infra/s3-legacy` e `module.sbom` com seus seis endereços | Endereços reais no state. O Terraform precisa deles para destruir exatamente o bucket antigo. |
| Environment `lab-image-base-infra` | Identidade OIDC de implantação já existente (subject da trust) |
| Role `itau-github-repo-factory-distroless-v1` e policy `factory-distroless-v1` | As mesmas entidades. Só os Sids de analytics mudam. |
| Backend e state, workspace, `.tflock` e ECR | Fora da migração. O plano exige no-op. |
| Root legado `infra/iam` | Ainda cita o ARN do bucket antigo. Pendência explícita, sem aplicação. |

## Dados

O batch não muda: `2da32bfa…`, com 19 objetos e 630308 bytes (seis SPDX e dois Parquet). O `snapshot_id` depende do destino, por isso foi regerado: `0b0c4ed7014746c8facdd779debd435e6a3fb160c5619f7d60751dabf5e4ec0b`. O manifesto e os VersionIds vêm da publicação real.

## Passos

1. **Revisão de transição**, nesta revisão:
   - o bucket novo é criado com proteção total;
   - no bucket antigo, só `force_destroy` muda para `true`;
   - `verify_plan.py` só aceita essa forma, na fase `transition`;
   - a policy inline transitória concede os recursos novos e a remoção restrita ao bucket antigo: `ListBucketVersions`, `DeleteBucketPolicy`, `DeleteBucket` e `DeleteObjectVersion`.
2. **Policy inline transitória**, aplicada pelo administrador com comparação antes e read-back depois.
3. **`Infra - Apply`**, com aprovação no environment `lab-image-base-infra`. O plano pós-apply precisa vir sem mudanças.
4. **Publicação do snapshot** em `sbom-analytics-s3.yml`, com read-back e recuperação.
5. **`policies/analytics/athena.json`**, com o manifesto e o VersionId lidos de volta.
6. **Workgroup e database `sbom_analytics`**, criados pelo administrador.
7. **Plano SQL** da rodada `sbom-analytics-v1-r1`, autorização pelo hash e execução com `fresh_round=true`.
8. **Revisão final**:
   - remove `module.sbom` e `infra/s3-legacy`;
   - o plano, na fase `removal`, apaga exatamente os seis endereços antigos, com todas as versões;
   - a policy final deixa de ter qualquer grant sobre o bucket antigo.
9. **Remoção dos objetos Glue e Athena históricos** pelo administrador, via API e sem SQL, seguida de um novo apply com drift zero.

## Rollback

- **Até o passo 8:** o bucket antigo continua intacto, e basta reverter o código.
- **Depois do passo 8:** a reconstrução usa os bytes preservados (plano congelado e evidências privadas). Não há recuperação do bucket apagado.
