# Distroless SBOM Analytics — migração da estrutura histórica

Este procedimento substitui a estrutura histórica, criada durante a prova de conceito, pela implantação ativa descrita em [operação](sbom-analytics-operations.md). O owner autorizou a substituição em 2026-10-11 e a remoção integral da estrutura histórica em 2026-10-12, no deployment AWS pessoal (conta `712107929769`, região `us-east-1`).

> **Estado:** todos os passos abaixo são **futuros** até serem executados e registrados. Nesta revisão, os recursos históricos continuam existindo. As descrições e os nomes novos ainda não foram aplicados na AWS.

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
| `tests/fixtures/sbom-analytics/historical-poc-round/`, `lab-frozen-plan.*` e os journals e fixtures Athena | Replays byte a byte do histórico |
| `infra/s3-legacy` e `module.sbom` com seus seis endereços | Endereços reais no state, só durante a migração. O Terraform precisa deles para destruir exatamente o bucket antigo. |
| Repositório `alric-corp/alric-containers-image-base`, tag `Source` e guards dos workflows | Identidade real do deployment e da proveniência. O núcleo recebe o repositório como entrada. |
| Environment `lab-image-base-infra` | Identidade OIDC de implantação já existente (subject da trust) |
| Role `itau-github-repo-factory-distroless-v1` e policy `factory-distroless-v1` | As mesmas entidades. Só os statements de analytics mudam. |
| Backend e state, workspace, `.tflock` e ECR | Fora da migração. O plano exige no-op. |
| Root legado `infra/iam` | A role `alric-github-repo-1360616627-infra-apply` ainda tem `ExactSbomAnalyticsBucket` sobre o ARN do bucket antigo (lido em 2026-10-12). Pendência explícita, fora do root `infra/ecr`. Não é alterada nesta migração. |

## Dados

O batch não muda: `2da32bfa…`, com 19 objetos e 630308 bytes (seis SPDX e dois Parquet). O `snapshot_id` depende do destino e foi recalculado para o bucket definitivo: `8439add73fe20e08d45292dddc62b360b6ccaa372395818aa0a5cf8a910eb507`. O manifesto e os VersionIds vêm da publicação real.

## Passos

1. **Revisão de transição** (esta revisão):
   - o bucket novo é criado com proteção total;
   - no bucket antigo, só `force_destroy` muda para `true`;
   - `verify_plan.py` só aceita essa forma, na fase `transition`;
   - a policy inline transitória concede os recursos novos e a remoção restrita ao bucket antigo: `ListBucketVersions`, `DeleteBucketPolicy`, `DeleteBucket` e `DeleteObjectVersion`.
2. **Policy inline transitória**, aplicada pelo administrador com comparação antes e read-back depois.
3. **`Infra - Apply`**, com aprovação no environment `lab-image-base-infra`. O preflight confirma que o nome está livre, e o plano pós-apply precisa vir sem mudanças.
4. **Publicação do snapshot** em `sbom-analytics-s3.yml`, com read-back e recuperação.
5. **Workgroup e database `sbom_analytics`**, criados pelo administrador a partir de [`docs/examples/sbom-analytics/`](examples/sbom-analytics/).
6. **Revisão de remoção**:
   - remove o bloco `module.sbom` e `infra/s3-legacy`;
   - adiciona `policies/analytics/athena.json` com o manifesto e o VersionId lidos de volta;
   - o plano, na fase `removal`, apaga exatamente os seis endereços antigos, com todas as versões.
7. **`Infra - Apply`** da remoção, com aprovação. O plano pós-apply precisa vir sem mudanças.
8. **Remoção dos objetos Glue e Athena históricos** pelo administrador, via API e sem SQL.
9. **Revisão final**:
   - retira as constantes `LEGACY_*`, a fase de remoção e os statements transitórios;
   - o administrador aplica a policy final, que não tem nenhum grant sobre o bucket antigo.
10. **Rodada SQL** `sbom-analytics-v1-r1`: plano, autorização pelo hash e execução com `fresh_round=true`, já sob a policy final.
11. **Drift zero**: `Infra - Apply` sem mudanças sobre a revisão final.

## Rollback

- **Até o passo 7:** o bucket antigo continua intacto, e basta reverter o código.
- **Depois do passo 7:** a reconstrução usa os bytes preservados (plano congelado e evidências privadas). Não há recuperação do bucket apagado.
