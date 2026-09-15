# P1-02 — Proposta de IAM/ECR para publication continuation, PROPOSED / NOT APPLIED

Contrato, investigação read-only e recomendação:
[specs/2026-09-13-partial-retry-without-rebuild/evidence.md](../../../../specs/2026-09-13-partial-retry-without-rebuild/evidence.md#investigação-sandbox-read-only-para-infraestrutura-de-publicação--2026-09-15)
e [plan.md](../../../../specs/2026-09-13-partial-retry-without-rebuild/plan.md#proposta-de-infraestrutura-para-publication-continuation--2026-09-15).
Corrigida após revisão independente adversarial (findings F1–F5, ver
[correção registrada no plan.md](../../../../specs/2026-09-13-partial-retry-without-rebuild/plan.md#correção-da-proposta-após-revisão-independente-adversarial--2026-09-15)).
Nenhum arquivo deste diretório é lido por workflow ou script ativo; nenhuma
chamada AWS aplicou estes templates. A role/policy existente
`github-actions-image-base` / `github-actions-image-base-ecr` e o
[trust ativo versionado](../../github-actions-image-base-trust.json)
permanecem intactos e fora desta proposta.

## Primary architecture

| Item | Valor |
| --- | --- |
| Role (nome de proposta, não aplicada) | `github-actions-image-base-p102-lab` |
| Repos (NOT_FOUND hoje, a criar) | `p102-lab-go1-26`, `p102-lab-go1-26-dev` |
| Trust primária | [trust.template.json](trust.template.json) — inclui `job_workflow_ref` |
| ECR | `IMMUTABLE`, sem `imageTagMutabilityExclusionFilters` |
| Perfil de execução | A — preprovisioned + execution-only |

| Arquivo | Finalidade |
| --- | --- |
| [trust.template.json](trust.template.json) | **Primária.** `aud`/`sub`/`repository`/`repository_id`/`repository_owner_id`/`ref` exatos, mais `token.actions.githubusercontent.com:job_workflow_ref` restringindo a assunção ao job definido em `partial-retry-lab.yml@refs/heads/main` |
| [trust.template.fallback-no-job-workflow-ref.json](trust.template.fallback-no-job-workflow-ref.json) | **Fallback / compatibility option**, não primária — mesmas condições, sem `job_workflow_ref`; só deve ser usada se essa claim se mostrar indisponível/instável no caminho real de dispatch, e após nova revisão |
| [execution.identity.template.json](execution.identity.template.json) | Profile A (recomendado): leitura/escrita de imagem, escopo exato aos dois ARNs lab; sem `CreateRepository`/`PutImageTagMutability`/`PutImageScanningConfiguration`/`TagResource`/`ListTagsForResource` |
| [provisioning.identity.template.json](provisioning.identity.template.json) | Profile B (alternativa, não recomendada): só `ecr:CreateRepository` nos dois ARNs lab — ver seção "Profile B" abaixo sobre por que `PutImageTagMutability` foi removido |

## Por que role nova, não reuso

Observado por investigação read-only em 2026-09-15 (`aws iam get-policy-version`
sobre a policy anexada à role existente): o `Resource` da policy de produção é
`arn:aws:ecr:us-east-1:712107929769:repository/image-base-*` — um prefixo
wildcard que cobre todo o catálogo de produção. Reutilizar
`github-actions-image-base` para o laboratório não criaria isolamento algum:
a mesma credencial já alcança os repositórios de produção hoje, sem qualquer
mudança de policy.

## Por que os repos NÃO se chamam `image-base-p102-lab-*`

Uma revisão independente anterior apontou que os nomes originalmente
propostos (`image-base-p102-lab-go1-26`/`-dev`) ainda casavam com o mesmo
wildcard `image-base-*` da role operacional — ou seja, mesmo com uma role
nova e corretamente escopada (LAB → PROD isolado), a role de **produção**
continuaria alcançando os repositórios do **laboratório** (PROD → LAB não
isolado), sem nenhuma mudança na policy existente. Isso não viola o
requisito contratual do P1-02 (que protege produção/`stable` do
laboratório, não o inverso), mas é uma capacidade residual sem função —
nada no design usa ou precisa que a role de produção alcance os repos lab.

Corrigido: os nomes `p102-lab-go1-26`/`p102-lab-go1-26-dev` não começam com
`image-base-` e portanto não casam com `image-base-*`:

```text
"p102-lab-go1-26".startswith("image-base-")      -> False
"p102-lab-go1-26-dev".startswith("image-base-")  -> False
```

Confirmado por teste dedicado, não só inspeção visual — ver
[test_p102_lab_iam_proposal.py](../../../../tests/unit/pipeline/governance/test_p102_lab_iam_proposal.py).

## Escopo exato

```text
arn:aws:ecr:us-east-1:712107929769:repository/p102-lab-go1-26
arn:aws:ecr:us-east-1:712107929769:repository/p102-lab-go1-26-dev
```

`image-base-go1-26` e `image-base-go1-26-dev` (produção) não aparecem em
nenhum ARN desta proposta, e os nomes lab não compartilham o prefixo
`image-base-` com nenhum repositório operacional. Confirmado `NOT_FOUND`
para os dois repositórios lab em 2026-09-15 — nenhum recurso a preservar,
nenhum consumidor a considerar.

## Trust: por que `job_workflow_ref` é a recomendação primária, não opcional

GitHub-side (`permissions: id-token: write` só no job `lab-publish`, quando
esse job existir) limita **quem pode pedir** um token OIDC. AWS-side
(`token.actions.githubusercontent.com:job_workflow_ref` na trust) limita
**qual workflow pode assumir a role** com o token pedido. As duas camadas
são complementares e nenhuma substitui a outra: sem a condição AWS, qualquer
job deste repositório em `main` que ganhasse `id-token: write` no futuro
(por engano ou não) poderia assumir a mesma role, já que a trust hoje
avaliada pela AWS só enxerga `sub`/`aud`, que não mudam por arquivo de
workflow. Por isso `trust.template.json` (com `job_workflow_ref`) é a
proposta primária; a variante sem essa claim é fallback explícito, não a
opção preferida.

## Execution profile — actions deliberadamente omitidas

A policy de produção também concede `ecr:CreateRepository`,
`ecr:PutImageTagMutability`, `ecr:PutImageScanningConfiguration`,
`ecr:TagResource` e `ecr:ListTagsForResource` no mesmo statement de
execução recorrente. `execution.identity.template.json` **não** reproduz
nenhuma delas: as três últimas não são justificadas por nenhum step
observado em `build-base-images.yml` nem inventariadas em
[docs/iam-permission-contract.md](../../../../docs/iam-permission-contract.md);
as duas primeiras pertencem exclusivamente a `provisioning.identity.template.json`
(Profile B), nunca ao perfil de execução recorrente. Least privilege, não
paridade cega com a role existente.

## Profile A — preprovisioned + execution-only (recomendado)

Adaptação deliberada do caminho produtivo, não "o mesmo caminho sem
alteração": produção executa `Ensure ECR repository exists`
(`describe-repositories` + `create-repository` condicional) e depois
`put-image-tag-mutability` **incondicionalmente**, a cada run, mesmo quando
o repositório já existe. O laboratório Profile A assume os dois
repositórios já provisionados por operador/Cloud e não executa nenhum
desses steps durante a execução do `lab-publish`.

Por que isso não enfraquece R7: R7 lista os gates que o P1-02 precisa
preservar — artifact selecionado, publicação por digest,
digest preservation/read-back, Cosign, provenance, SBOM, isolamento M13,
continuação do retry. "Ensure repository exists" e a reconfiguração de
mutabilidade não estão nessa lista: são bookkeeping de provisionamento,
cujo efeito (repositório existente, mutabilidade `IMMUTABLE` configurada)
é idêntico independentemente de quem o executa ou quando. Descrição
correta: **mesmo caminho de publication/integrity (copy por digest,
read-back, sign, attest, SBOM) com provisionamento externo deliberadamente
separado** — não "mesmo caminho sem alteração".

Classificação: `ACCEPTABLE_LAB_ADAPTER`.

## Profile B — self-provisioning (alternativa documentada, não recomendada)

`provisioning.identity.template.json` contém somente `ecr:CreateRepository`
nos dois ARNs lab — **sem** `ecr:PutImageTagMutability`. Motivo: a API
`create-repository` aceita `--image-tag-mutability` na própria chamada de
criação (confirmado pelo código produtivo em
[build-base-images.yml](../../../../.github/workflows/build-base-images.yml),
step "Ensure ECR repository exists": `aws ecr create-repository
--image-tag-mutability ...` cria o repositório já com a mutabilidade
definida). Como o design do laboratório não reaplica mutabilidade a cada
execução (ao contrário da produção), `PutImageTagMutability` nunca é
necessário: se o repositório já existir quando o provisionamento rodar,
`CreateRepository` falha com `RepositoryAlreadyExistsException` — fail
closed, sem tentar reconfigurar um recurso existente. `DescribeRepositories`
já é concedido por `execution.identity.template.json`, então não é
duplicado aqui. Não aplicado; Profile A continua a recomendação.

## ECR: `IMMUTABLE` sem exclusão para `stable`

Corrigido após revisão independente: a proposta anterior recomendava
replicar `IMMUTABLE_WITH_EXCLUSION` com exclusão `stable`, igual à
produção. Isso está errado para um repositório de laboratório — a exclusão
existe em produção só porque `promote-stable.yml`/`recover-stable.yml`
precisam sobrescrever esse ponteiro repetidamente. O laboratório nunca
promove e nunca sobrescreve nenhuma tag (o padrão fixo
`p1-02-lab-<run_id>-<attempt>` é único por construção), então a exclusão
não tem uso legítimo e só adiciona uma capacidade sem função: se um bug no
guard de código algum dia produzisse uma tag literal `stable` no
repositório lab, `IMMUTABLE` sem exclusão faz o ECR **rejeitar** a escrita
com erro de imutabilidade, em vez de aceitá-la silenciosamente. Configuração
recomendada para os dois repos lab:

```text
imageTagMutability: IMMUTABLE
encryptionConfiguration.encryptionType: AES256
imageScanningConfiguration.scanOnPush: true
```

Nenhum campo de exclusão de mutabilidade é declarado nessa configuração.

`AES256`/`scanOnPush` são preservados por não introduzirem nenhuma
capacidade de risco. Lifecycle (30 dias para untagged) pode ser replicado
como decisão operacional de provisionamento, não como requisito do
contrato P1-02.

## Stable isolation — quatro camadas

1. A role lab não possui nenhum ARN de repositório de produção.
2. Os repos lab ficam fora do prefixo `image-base-*` da role operacional
   (nomes `p102-lab-*`, confirmados sem overlap).
3. Os repos lab são `IMMUTABLE` sem exclusão para `stable`.
4. Um application guard (a implementar no futuro `lab-publish`) deve
   rejeitar `stable`/`latest`/qualquer repositório fora da allowlist exata
   dos dois ARNs acima/tags vindas de input.

O item 4 **ainda não existe** — não há código de `lab-publish` neste
repositório. Não tratar esta lista como implementação concluída; é o
desenho que a futura implementação deve seguir.

## Sigstore

`partial-retry-lab.yml` não entra em
[policies/release/signing-identities.json](../../../release/signing-identities.json).
A verificação futura do laboratório usa a identidade própria do laboratório
(`.../partial-retry-lab.yml@refs/heads/main`), nunca a identidade do
produto (`build-base-images.yml@refs/heads/main`). Nenhuma mudança ao
[ADR-0002](../../../../docs/adr/0002-sigstore-trust-model.md).

## Limites

Renderização/aplicação: nenhuma. Não existe ainda um renderizador dedicado
a este diretório (o [renderizador do P1-04](../../../../tools/render_iam_proposal.py)
é específico do template `factory-permissions`, com marcadores e parâmetros
diferentes destes — os valores aqui já são concretos, sem `${...}`).
Aplicar estes templates exige revisão de Cloud/IAM e Segurança/AppSec,
decisão explícita sobre a role/trust e execução manual fora deste
repositório.

## Not applied

Nada foi criado ou alterado na AWS por esta proposta.
`PUBLICATION_INFRA_DESIGN = PROPOSED`, `PUBLICATION_INFRA_APPLIED = NO`,
`AWS_EXECUTION = NOT RUN`.
