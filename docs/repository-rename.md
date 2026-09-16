# Renomeação dos repositórios e confiança AWS

Em 10/09/2026 os repositórios passaram a se chamar:

| Nome anterior | Nome atual |
| --- | --- |
| `alric-corp/itau-xj7-containers-image-base` | `alric-corp/alric-containers-image-base` |
| `alric-corp/itau-xj7-reusable-workflows` | `alric-corp/alric-containers-reusable-workflows` |

Os clones foram renomeados, seus remotes atualizados e os vínculos dos worktrees
reparados. Não foi necessário recriar histórico, branches ou PRs.
Referências executáveis, Dependabot e guias atuais usam os novos nomes.
Documentos e registros de histórico/entregas também foram atualizados para
os novos nomes (o GitHub redireciona as URLs antigas de qualquer forma).
Evidências criptográficas — certificados, attestations e a policy de
identidades de assinatura — são a exceção: contêm o nome antigo e não podem
ser reescritas sem alterar a evidência (ver "Assinaturas anteriores à
renomeação" abaixo).

## Dependência compartilhada

Renomear o repositório não reescreve commits antigos. O workflow compartilhado
anterior ainda chamava a action Trivy pelo nome antigo; trocar apenas o prefixo
do `uses:` no consumidor não corrigiria essa referência interna.

Os chamadores agora usam `0459275b4a2ffbe6e8961041e7b93b41e88ba215`, publicado
na branch do [PR #2 da biblioteca](https://github.com/alric-corp/alric-containers-reusable-workflows/pull/2),
com a referência interna corrigida. O pin continua imutável. A action Trivy
mantém o commit de sua implementação e recebe somente o novo nome de repositório.

## AWS

Conta: `712107929769`. Role: `github-actions-image-base`.
A [trust policy](../policies/aws/github-actions-image-base-trust.json) foi
atualizada na AWS e lida novamente para confirmar o resultado. A única mudança
é o nome do repositório no subject OIDC:

```text
repo:alric-corp@178685987/alric-containers-image-base@1360616627:ref:refs/heads/main
```

A comparação continua sendo `StringEquals`, com `aud=sts.amazonaws.com`,
provider `token.actions.githubusercontent.com` e ação `sts:AssumeRoleWithWebIdentity`.
IDs permanentes da organização e do repositório permanecem iguais. O nome
antigo, PRs, forks e outras branches não correspondem ao subject autorizado.
A role não foi recriada; permissões de ECR e conteúdo/tags de imagens não
foram alterados por esta migração.

## Assinaturas anteriores à renomeação

Certificados e attestations existentes contêm o nome antigo e não podem ser
reescritos sem alterar a evidência. A [policy de identidades](../policies/release/signing-identities.json)
registra esse alias explicitamente.

O gate tenta a identidade atual e, se a verificação criptográfica falhar, a
identidade histórica exata. Cosign e provenance precisam aprovar **a mesma
identidade e o mesmo digest**, sempre no workflow `build-base-images.yml` e na
`main`. Não há regex ampla para o nome do assinador.

Para esse produto, o resultado criptograficamente verificado da provenance
também precisa confirmar `sourceRepositoryIdentifier=1360616627` e
`sourceRepositoryOwnerIdentifier=178685987`, além da URI e branch esperadas.
Esses valores vêm do certificado assinado, não do predicate controlado pelo
workflow. Recriar outro repositório com o nome antigo não satisfaz os IDs.
O gate registra a identidade aceita em `verified-identity.json` junto das
evidências de promoção/recuperação. Falhas não conservam relatórios de uma
tentativa anterior como aprovação.

## Alcance da validação

Os testes verificam nomes atual e histórico, rejeição de IDs errados ou
ausentes, branch indevida, IDs apenas no predicate e mistura de assinadores.
Os checks de integração usam o commit exato do executor com o nome atualizado.
O registro de execução fica em `docs/evidence/repository-rename-2026-09-10.json`.

A leitura da policy confirma a configuração aplicada, mas não representa uma
nova sessão OIDC emitida por um runner na `main`. Publicação ECR e movimentação
de stable não fazem parte desta validação; dependem dos fluxos normais após
integração do PR.

Referências: [renomeação e Actions](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository),
[OIDC GitHub/AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws),
[claims OIDC](https://docs.github.com/en/actions/reference/security/oidc).
