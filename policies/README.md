# Políticas do produto

Configuração revisada que define decisões de operação e release. Os módulos
em `scripts/pipeline/` aplicam as regras; os workflows controlam a execução.

| Arquivo | Consumidor | Responsabilidade |
| --- | --- | --- |
| `governance/reusable-workflows.json` | `governance/workflow_dependencies.py` | Origem GitHub.com aprovada da biblioteca; callers/actions literais por SHA, checkout e grupo Dependabot devem permanecer coerentes |
| `operations/health.json` | `operations/operational_health.py`, `catalog/default_batch.py` | Donos, alertas, cron e retenção das evidências; `exceptions` é a lista de frameworks fora do lote padrão (motivo, dono, `review_by`, ADR) |
| `operations/ecr-lifecycle.json` | ECR, após preview revisado | Expira somente imagens sem tag após 30 dias; preserva releases com tag |
| `release/promotion-quarantine.json` | `release/find_promotion_candidate.py` | Digests retirados de stable que não podem ser promovidos novamente |
| `release/signing-identities.json` | `release/verify_promotion.py` | Nome atual, nomes históricos e IDs imutáveis assinados do repositório e da organização |
| `aws/github-actions-image-base-trust.json` | IAM, role `github-actions-image-base` | Trust policy OIDC aplicada, restrita ao subject exato da main |

Alterações passam por PR e revisão dos donos em `.github/CODEOWNERS`. O lint
compara a política de retenção com os workflows locais e reutilizáveis reais.
Quarentena é por digest e repositório, com motivo, autor e data; consulte o
[runbook de recuperação](../README.md#recuperação-de-stable-runbook-m15).
Uma exceção em `health.json` tira o framework dos três lotes de `workflow.yml`
e o mantém no catálogo; o lint do lote padrão exige as duas coisas juntas, os
lotes como literal canônico (nunca `vars`/`env`/`secrets`/`fromJSON`) e `adr`
como caminho relativo `docs/adr/NNNN-titulo.md` na
[convenção](../docs/adr/README.md).

Estes arquivos não armazenam credenciais ou estado gerado de execução.

A policy IAM é a configuração desejada; editar o arquivo não a aplica na AWS.
A migração de nomes de 10/09/2026 registrou aplicação, verificação
e limites. Nomes históricos só são aceitos para assinaturas/provenance, com
IDs assinados iguais aos do repositório atual; eles não têm acesso OIDC à role.

O [contrato IAM P1-04](../docs/iam-permission-contract.md) descreve o
inventário de operações e a proposta de execução/provisionamento para
revisão Cloud/IAM. Não substitui a policy acima nem é consumido como
permissão pelos workflows. Validação local não comprova autorização efetiva
ou isolamento de stable.
