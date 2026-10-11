# Distroless SBOM Analytics — reset do LAB

Em 2026-10-11 o owner autorizou o reset do componente analítico do LAB pessoal, na conta `712107929769` e região `us-east-1`. O reset substitui a estrutura da POC pelos nomes definitivos do LAB e remove a estrutura antiga depois da nova prova.

Ficam como estão:
- ECR;
- o backend e o state compartilhados (`infra/ecr`, bucket de state em `us-east-2`, mesma key, workspace `default`);
- a role central `itau-github-repo-factory-distroless-v1` e o modelo de uma inline policy `factory-distroless-v1`;
- os gates do repositório.

As provas da POC (runs `38031426478` e `38117928589`) valem só como histórico. A rodada `lab-sbom-athena-v1` está encerrada e não é reaberta.

## Nomes

| Tipo | POC (removido) | Ativo |
| --- | --- | --- |
| Bucket S3 | `alric-distroless-sbom-712107929769-us-east-1` | `alric-distroless-sbom-analytics-712107929769-us-east-1` |
| Dados | `sbom-analytics/poc-v1/` | `sbom-analytics/v1/` |
| Resultados Athena | `query-results/poc-v1/` | `query-results/sbom-analytics-v1/` |
| Workgroup Athena | `poc_distroless_sbom` | `sbom_analytics` |
| Database Glue | `poc_distroless_sbom` | `sbom_analytics` |
| Prefixo de tabelas/views | `poc_snapshot` | `sbom_snapshot` |
| Workflow S3 | `sbom-analytics-lab-poc.yml` | `sbom-analytics-s3.yml` |
| Workflow Athena | `sbom-analytics-athena-lab-poc.yml` | `sbom-analytics-athena.yml` |
| Configuração S3 | `policies/analytics/lab-poc.json` | `policies/analytics/s3.json` |
| Configuração Athena | `policies/analytics/athena-lab-poc.json` | `policies/analytics/athena.json` |

Os nomes ativos são travas no código, não convenção:
- `catalog.NAMESPACE` e `athena_poc.config` aceitam só os nomes exatos;
- `infra/s3` fixa os prefixos e o contrato de plano;
- a policy versionada nomeia o bucket, o workgroup, o database e as cinco tabelas do snapshot.

As configurações da rodada encerrada ficam em `tests/fixtures/sbom-analytics/historical-poc-round/`, só para os testes de replay dos journals preservados.

## Dados

O batch é o mesmo: `2da32bfa…`, com 19 objetos e 630308 bytes (os seis SPDX e os dois Parquet). O `snapshot_id` depende do destino, então foi regerado para o bucket e prefixo novos: `0b0c4ed7014746c8facdd779debd435e6a3fb160c5619f7d60751dabf5e4ec0b`.

O plano congelado `tests/fixtures/sbom-analytics/frozen-plan-v1.zip` foi derivado de `lab-frozen-plan.zip` sem alterar bytes do batch. Os testes conferem isso membro a membro. O manifesto e os VersionIds vêm da publicação real e entram em `policies/analytics/athena.json` só depois do read-back.

## Fases

1. **Revisão de transição.** O bucket antigo continua em `module.sbom`, servido por `infra/s3-legacy`.
   - A única mudança permitida no bucket antigo é `force_destroy` virar `true`.
   - `module.sbom_analytics` cria o bucket novo com `prevent_destroy = true` e `force_destroy = false`.
   - A policy inline transitória concede:
     - o bucket novo e os prefixos novos;
     - o workgroup e o database novos;
     - as cinco tabelas do snapshot novo;
     - a remoção restrita ao bucket antigo: `ListBucketVersions`, `DeleteBucketPolicy`, `DeleteBucket` e `DeleteObjectVersion`.
2. **Infra Apply**, com o plano verificado na fase `transition`.
3. **Publicação S3** pelo workflow `sbom-analytics-s3.yml`, com read-back integral e retry idêntico, seguida da recuperação independente.
4. **Criação do workgroup e do database `sbom_analytics`** pelo administrador, a partir de `docs/examples/sbom-lab/*-proposal.json`.
5. **Rodada SQL nova** no workflow `sbom-analytics-athena.yml`:
   - primeiro `mode=plan`;
   - depois `mode=execute` com `fresh_round=true`, o hash do plano e a referência de autorização.
6. **Revisão final.** Remove `module.sbom` e `infra/s3-legacy`, e o plano verificado na fase `removal` apaga exatamente os seis endereços antigos. A policy final remove todos os grants do bucket antigo.
7. **Remoção do workgroup, do database e dos cinco objetos `poc_*`** pelo administrador, via APIs Glue/Athena, sem SQL. Em seguida, Infra Apply com drift zero.

**Retomada (`fresh_round`).** Uma rodada só começa vazia com `fresh_round=true`, e só se:
- não houver journal local nem restaurado;
- nenhum dos cinco nomes existir no catálogo.

Qualquer retomada continua exigindo a restauração verificada do journal anterior. O workflow recusa o `round_id` `lab-sbom-athena-v1`.

## Fora do escopo

- Os papéis legados de `infra/iam`, uma raiz separada, ainda citam o ARN do bucket antigo. Depois da remoção, essa referência aponta para um bucket inexistente. Mudá-la exige aplicar aquela raiz, o que não faz parte deste reset.
- Os nomes internos dos módulos Python (`poc.py`, `athena_poc.py`) e de `requirements-sbom-poc.txt` foram mantidos, para não reescrever o histórico e os testes de regressão. Nenhum recurso de nuvem nem workflow ativo usa `poc`.
- As evidências da POC e do reset ficam fora do Git, no diretório privado `audit-evidence/`.
