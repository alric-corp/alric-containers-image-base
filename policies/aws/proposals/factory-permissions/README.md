# P1-04 — Exemplos de IAM, PROPOSED / NOT APPLIED

Contrato canônico, parâmetros, fontes, riscos e plano de validação:
[docs/iam-permission-contract.md](../../../../docs/iam-permission-contract.md).
Os jobs AWS não consomem estes exemplos como permissões; somente testes
offline os leem. Nenhum arquivo é aplicado à AWS por esta entrega.
O [trust ativo versionado](../../github-actions-image-base-trust.json) permanece intacto.

| Arquivo | Finalidade |
| --- | --- |
| [inventory.json](inventory.json) | Operações e fontes, vínculo entre cada Sid/action e necessidade |
| [execution.identity.template.json](execution.identity.template.json) | Requests recorrentes ECR, incluindo imagens/evidence e retag |
| [provisioning.identity.template.json](provisioning.identity.template.json) | DescribeRepositories/CreateRepository/PutImageTagMutability exigidos pelo publicador atual |
| [trust.template.json](trust.template.json) | Trust proposta por subject, repository/IDs e main; não aplicada |
| [parameters.fixture.json](parameters.fixture.json) | Conta/identidade sintéticas, somente dois repos; não é configuração corporativa |

Na trust proposta, `repository` usa `StringEquals` e exige o nome exato.
Uma renomeação exige atualizar essa condição mesmo com IDs preservados;
enquanto o nome não corresponder, a autenticação falha. Consulte o
[procedimento de renomeação](../../../../docs/repository-rename.md), incluindo
as demais referências e condições envolvidas.

O [renderizador](../../../../tools/render_iam_proposal.py) produz JSON local
em diretório novo fora do checkout. Substitui o marcador ECR_REPOSITORY_ARNS
por uma lista tipada; não executar templates brutos na AWS. Runtime isolado
não é compatível com o step de provisioning atual. Os exemplos não oferecem
exclusividade de escrita de stable nem inventam condição por tag Docker.
