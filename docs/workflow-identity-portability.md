# Identidade de execução e portabilidade dos workflows

Os workflows do Distroless SBOM Analytics descobrem sua identidade pelos contextos nativos do GitHub Actions. Em seguida, comparam essa identidade com a identidade autorizada pelo contrato versionado. Nenhum guard de job contém o nome do owner ou do repositório. Também não há `vars.*` ou secrets novos para owner, repositório ou IDs.

## Identidade observada e identidade autorizada

| | Fonte | Campos |
| --- | --- | --- |
| **Observada** | Contextos nativos `github.*`, lidos pelas variáveis do runner | `GITHUB_REPOSITORY`, `GITHUB_REPOSITORY_OWNER`, `GITHUB_REPOSITORY_ID`, `GITHUB_REPOSITORY_OWNER_ID`, `GITHUB_REF`, `GITHUB_EVENT_NAME` |
| **Autorizada** | [`policies/pipeline/config.json`](../policies/pipeline/config.json): `repository`, `subject_prefix` (`repo:<owner>@<owner_id>/<repo>@<repo_id>`) e `branch` | Nome completo, owner, IDs imutáveis de owner e repositório, `refs/heads/<branch>` |
| **Garantia final** | Trust OIDC da role operacional | `sub` com os mesmos IDs imutáveis e o Environment, além de `repository_id` e `repository_owner_id` |

O primeiro passo depois do checkout, em cada job, é este:

```sh
python3 -B -m scripts.pipeline.governance.configuration --scope DEV --authorized-event workflow_dispatch
```

Ele exige que os seis valores observados existam, sejam válidos e sejam **iguais** aos autorizados. O evento também precisa estar entre os declarados pelo workflow. `pull_request` nunca é aceito. Comparar só com outros campos do próprio contexto não basta: um fork coerente consigo mesmo é recusado.

Se houver qualquer divergência ou ausência, o passo falha sem gravar `GITHUB_ENV` nem `GITHUB_OUTPUT`. Então não existe `AWS_ROLE_ARN` para o passo OIDC, e os passos seguintes (dependências, leitura da API do GitHub, OIDC, S3 e Athena) não rodam. Os passos `always()` só preservam diagnósticos e não usam credenciais.

O guard de job continua restrito a `refs/heads/develop` e `workflow_dispatch`. Os Environments, as permissões, a concorrência e as session policies não mudam.

Workflows que usam essa verificação:
- `sbom-analytics-s3.yml` (`publish` e `recover`);
- `sbom-analytics-athena.yml` (`athena`).

Os outros escopos de `configuration.py` mantêm a semântica anterior: sem `--authorized-event`, ele só confere `GITHUB_REPOSITORY` quando a variável existe.

## Porte para outra organização

O porte altera configuração e controles, não o código dos workflows:

1. Em `policies/pipeline/config.json`: `repository`, `subject_prefix` (com os IDs da organização e do repositório de destino), contas, roles, buckets e backend.
2. Trust OIDC da role operacional com o `sub` e os IDs novos, e os Environments equivalentes, com revisores e branch policy.
3. As dependências `uses:` listadas abaixo. O GitHub não aceita expressão em `uses:`, então cada referência é revista e fixada em SHA no espelho ou allowlist corporativa.

## Inventário de referências fixas (auditoria de 2026-10-12)

| Classe | Onde | Situação |
| --- | --- | --- |
| Referência pessoal substituível por contexto nativo | `sbom-analytics-s3.yml` (2 guards) e `sbom-analytics-athena.yml` (1 guard) | **Substituída** pela verificação acima |
| | `factory-central-role-preflight.yml`: 2 guards `github.repository == '…'`, conta e role literais | Pendente: pode adotar o mesmo mecanismo, mas é outro fluxo, fora deste escopo |
| | `renovate.yml`: `RENOVATE_REPOSITORIES` | Pendente: substituível por `${{ github.repository }}` |
| Identidade esperada necessária à autorização | `policies/pipeline/config.json` (`repository`, `subject_prefix`, `branch`) | Fonte da identidade autorizada |
| | `policies/aws/*.trust.json`, `infra/iam` e `infra/lifecycle` (subjects OIDC) | Controle AWS. Não alterado. |
| | `policies/release/signing-identities.json` e `scripts/verify-image.sh` (identidade de assinatura) | Verificação de proveniência das imagens. Não alterado. |
| Dependência externa com `uses:` fixado em SHA | `actions/*`, `aws-actions/*`, `hashicorp/setup-terraform`, `sigstore/cosign-installer`, `oras-project/setup-oras`, `docker/setup-qemu-action`, `renovatebot/github-action` | Espelhar ou aprovar no porte |
| | `alric-corp/alric-containers-reusable-workflows`: `actions/setup-trivy@eea2d2f…`, `validate-apko-images.yml@fd44ef5…`, `test-runtime-images.yml@fd44ef5…` e `policies/governance/reusable-workflows.json` | Repositório do executor compartilhado. No porte, vira o equivalente corporativo, com SHAs reconfirmados. |
| Identificador de infraestrutura compartilhada | Backend `712107929769-alric-containers-image-base-tfstate`, roles `alric-image-base-factory-*` e `alric-github-repo-1360616627-*`, tag `Source` do root `infra/ecr` | Identidades reais. Não alteradas. |
| Evidência histórica | Fixtures, journals e metadados de runs históricos; docs da POC | Preservada byte a byte |
