# Distroless SBOM Analytics — operação

O Distroless SBOM Analytics guarda os SBOMs SPDX dos builds da Factory em snapshots fechados no S3 e os consulta no Athena. Toda execução é manual (`workflow_dispatch` em `develop`). Não existe ingestão automática a partir do build, e nenhum resultado concede autoridade de publicação ou promoção.

A substituição da estrutura histórica está em [migração](sbom-analytics-migration.md). Os recursos da coluna "Ativo" abaixo existem na AWS desde 2026-10-12. A remoção da estrutura histórica só acontece depois da prova Athena.

## Implantação atual (AWS pessoal)

Os identificadores abaixo pertencem ao deployment pessoal, na conta `712107929769` e região `us-east-1`. Não valem como contrato para outra conta.

| Componente | Ativo |
| --- | --- |
| Bucket S3 | `distroless-sbom-analytics`: nome exato em `policies/pipeline/config.json` (`analytics.bucket`), sem conta, região ou organização |
| Prefixo de dados | `sbom-analytics/v1/` (snapshots em `sbom-analytics/v1/snapshots/<snapshot_id>/`) |
| Prefixo de resultados | `query-results/sbom-analytics-v1/` |
| Athena Workgroup | `sbom_analytics` (engine 3, saída imposta, SSE-S3, corte de 100 MiB por consulta) |
| Glue Database | `sbom_analytics` |
| Tabelas e views por snapshot | `sbom_snapshot_<snapshot_id>_<nome>_v1` (2 tabelas e 3 views) |
| Identidade | role `itau-github-repo-factory-distroless-v1` e sua única inline policy `factory-distroless-v1` |
| Environment dos workflows de dados | `DEV` |
| Environment do Terraform | `lab-image-base-infra`: environment de implantação já existente, com revisor obrigatório. O nome identifica o deployment, não o produto. |

A infraestrutura S3 é o filho `module.sbom_analytics` (`infra/s3`) do root `infra/ecr`, no mesmo backend e state, com `prevent_destroy = true` e `force_destroy = false`. O nome do bucket entra como `sbom_bucket_name`; outra instalação define o seu próprio nome na configuração, sem alterar código. Conta e região continuam configuradas separadamente. O workgroup e o database são criados fora do Terraform pelo administrador, a partir de [`docs/examples/sbom-analytics/`](examples/sbom-analytics/). Permissões e procedimento: [operador externo](sbom-analytics-athena-iam-runbook.md).

## Componentes no repositório

| Parte | Caminho |
| --- | --- |
| Workflow de snapshot | `.github/workflows/sbom-analytics-s3.yml` (`Distroless SBOM Analytics - S3 Snapshot`) |
| Workflow de consultas | `.github/workflows/sbom-analytics-athena.yml` (`Distroless SBOM Analytics - Athena`) |
| Concorrência | `distroless-sbom-analytics`, a mesma nos dois workflows, sem cancelamento |
| Configuração S3 | `policies/analytics/s3.json` (destino, role, batch, snapshot e contagens esperadas) |
| Configuração Athena | `policies/analytics/athena.json` (nomes exatos, limites e manifesto de referência do snapshot) |
| Plano congelado | `tests/fixtures/sbom-analytics/frozen-plan-v1.zip` e `.json` |
| Executores | `scripts/pipeline/analytics/s3_run.py` (snapshot), `athena_run.py` (consultas) e `athena_restore.py` (retomada) |
| Catálogo e SQL | `scripts/pipeline/analytics/catalog.py` e `sql/sbom-analytics/` |
| Dependências | `requirements-sbom-analytics.txt` |

`policies/analytics/athena.json` só recebe valores depois de uma publicação real com read-back integral: o SHA-256 e o VersionId do `ingestion-manifest.json`. Os valores nunca são inferidos. Os valores atuais vêm da publicação do run `38207794810` e foram conferidos por leitura independente do bucket.

## Operar

### 1. Publicar o snapshot

```sh
gh workflow run sbom-analytics-s3.yml --ref develop
```

O job `publish` executa nesta ordem:
1. confere o plano congelado antes de obter credenciais;
2. assume a role por OIDC com uma session policy restrita a `sbom-analytics/v1/snapshots/`;
3. lê a configuração do bucket;
4. grava a sonda condicional;
5. publica com `If-None-Match: *`;
6. faz o read-back;
7. repete a publicação, que precisa voltar `SNAPSHOT_ALREADY_PRESENT_IDENTICAL` sem nenhum PUT.

O job `recover` recupera o snapshot só pelo S3, sem os insumos originais, e confere as contagens.

### 2. Planejar e executar a rodada SQL

Primeiro o plano, sem executar SQL:

```sh
gh workflow run sbom-analytics-athena.yml --ref develop -f mode=plan -f round_id=sbom-analytics-v1-r1
```

O artifact `sbom-athena-<run>-<attempt>` traz `sql-plan.json` e o hash dele: 18 instruções (5 DDL, 11 SELECT e 2 DESCRIBE). A execução exige uma autorização do owner para esse hash.

- **Primeira execução de uma rodada nova**:
  `-f mode=execute -f fresh_round=true -f authorized_plan_sha256=<hash> -f authorization_reference=<ref>`.
  É recusada se houver journal ou se qualquer um dos cinco nomes já existir no catálogo.
- **Retomada**: `-f mode=execute -f resume_source=<json>`.
  Restaura e verifica o journal do run anterior antes do OIDC. Nunca usa `fresh_round`.

A rodada histórica `lab-sbom-athena-v1` é recusada pelo workflow.

### 3. Resultado esperado para o corpus conhecido

| Medida | Esperado |
| --- | --- |
| Observações SPDX | 6 |
| Registros de pacote SPDX | 300 |
| go1-26 por arquitetura | 22 |
| go1-26-dev por arquitetura | 123 |

Registros SPDX não são APKs instalados. As consultas `01`–`05` estão em `sql/sbom-analytics/`, e `05_trace_original` leva cada observação ao SPDX original no snapshot.

## Garantias e limites

- **Snapshots:**
  - são fechados por `If-None-Match: *`, com SSE-S3, versionamento e bloqueio público;
  - a recuperação confere hash e VersionId.
- **Consultas:**
  - o journal é gravado antes de cada `StartQueryExecution`;
  - os tokens são idempotentes por rodada;
  - as páginas de resultado ficam no journal antes da validação;
  - nunca há rerun cego, e falha ou resultado incerto se reconcilia por leitura.
- **Credenciais:** só a role central por OIDC. Não há fallback administrativo para SQL.
- **Evidências** de cada execução ficam fora do Git, em diretório privado.
