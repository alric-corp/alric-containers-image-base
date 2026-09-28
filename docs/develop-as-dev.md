# Migração do LAB: develop como DEV

Esta revisão migra o contrato executável de
`alric-corp/alric-containers-image-base` a partir da baseline histórica
`main@b9ec0cea6c690fc402b0833287e39995de4de437`:

| Branch | Papel nesta entrega |
| --- | --- |
| `develop` | DEV oficial; destino de PRs e branch autorizada a publicar, promover, recuperar e administrar Infra DEV |
| `main` | Reservada para PROD futuro; somente CI genérico sem AWS neste contrato |
| `staging` | HOM futuro; sem implementação nesta entrega |

**Código preparado não significa cutover aplicado.** No preflight, a default
branch remota ainda era `main`, `develop` não existia no remoto e a trust AWS
do produto ainda autorizava `refs/heads/main`. Esta entrega não muda Settings,
IAM, imagens, tags, conta, região, backend ou recursos Terraform.

## Contrato preservado

PRs para `develop` usam validação/trust do produto sem credenciais AWS. Infra
mantém seu contrato separado: PRs internos para `develop` podem assumir a
role de plan, incluindo ensure do backend e locking do state; forks não.
Push, dispatch e schedule DEV continuam usando o mesmo engine, catálogo e
gates. Catalog Certification permanece dispatch FULL fixo; App Certification
exige um source run bem-sucedido de `catalog-certification.yml` em `develop`,
no mesmo repository e tentativa aceita pelo resolver.

Não há mudança em Melange/Apko, composição OCI, multiarch, Trivy, contracts,
publication gate, pair binding, Skopeo, read-back, soak ou recovery sem rebuild.
Os reusables continuam pinados por SHA. Os crons continuam `23 3 * * *`
(build), `17 * * * *` (promoção) e `40 5 * * *` (health).

O signer DEV e a source ref de provenance são exatos:

```text
https://github.com/alric-corp/alric-containers-image-base/.github/workflows/build-base-images.yml@refs/heads/develop
refs/heads/develop
```

As assinaturas, provenance, runs, SHAs e digests históricos de `main` não são
reescritos. O verificador DEV de promoção/recovery rejeita essa origem antiga;
não há allowlist simultânea das duas branches. A stable antiga não é movida
pela migração, mas seu digest pode deixar de ser um destino de recovery
autorizado pela política nova. Antes de retomar stable, registre candidatos
e destinos de recuperação aprovados produzidos em `develop` e aceite
explicitamente essa fronteira histórica. Novas execuções seguem o build DEV
normal e o soak real; não reassine um build antigo para atribuí-lo a `develop`.
App Certification precisa de uma nova certificação FULL autorizada em `develop`.

## Cutover externo, após revisão e autorização

1. Revise o diff e os resultados da suíte oficial. Integre o resultado revisado
   à branch local `develop` e publique/sincronize essa branch sem force push.
   Confira o SHA remoto; publicar somente a baseline antiga não conclui a migração.
2. Configure proteção de `develop`, CODEOWNERS e os required checks reais
   `Unit & integration tests` e `Repository & workflow lint`. Confira eventuais
   rulesets organizacionais. O preflight da API de branch protection de `main`
   retornou `Branch not protected` e a listagem de rulesets, incluindo herdados,
   retornou vazia; não presuma proteção herdada ou aplicada.
3. Antes de liberar qualquer execução mutável, retire a autorização dos
   workflows antigos de `main`. Substitua a trust ref-based do produto pelo
   subject exato de `develop` abaixo, sem manter o de `main`. Troque somente
   a restrição de deployment do environment existente
   `lab-image-base-infra` de `main` para `develop`, preservando reviewers.
4. **Verifique também os YAMLs ainda existentes em `main`.** O patch em
   `develop` não muda esses arquivos. Em especial, a trust Infra PR termina
   em `:pull_request`, não identifica a base do PR e não bloqueia sozinha o
   workflow antigo de PR para `main`. Uma alteração separada, revisada e
   autorizada de desativação/guards em `main` deve impedir esse caminho e
   os demais caminhos antigos antes de declarar `main` sem mutação DEV.
   Até isso estar concluído, mantenha os workflows mutáveis afetados suspensos
   operacionalmente; nenhuma suspensão é feita por esta entrega.
5. Confirme branch protection, checks, trust e environment, além da ausência
   de runs antigos com credenciais ativas. Só então altere a default branch:

   ```sh
   # Comando preparado; executar somente com autorização de cutover.
   gh api --method PATCH repos/alric-corp/alric-containers-image-base \
     -f default_branch=develop
   ```

6. Releia Settings e valide que os próximos schedules usam o SHA de `develop`.
   Confirme que dispatch de `main` e PR para `main` não alcançam AWS DEV,
   sem executar publicação/promoção como parte desta migração. Build,
   certificações, soak e stable reais dependem de autorização operacional própria.

O health filtra explicitamente runs de `develop`, inclusive schedules e fila.
O início da nova série pode acusar falta de histórico; não reduza thresholds
nem use runs de `main` para preencher essa lacuna.

O GitHub executa schedules a partir da default branch. Enquanto ela for
`main`, as definições antigas continuam sendo as definições agendadas; trocar
apenas o guard local não altera esse comportamento remoto. Não há mudança de
cron ou promessa de pontualidade do scheduler.

## IAM e OIDC

| Caminho | Subject / impacto externo |
| --- | --- |
| Produto: build, promoção e recovery | Substituir o subject ref-based exato por `repo:alric-corp@178685987/alric-containers-image-base@1360616627:ref:refs/heads/develop` na role de produto aplicada |
| Infra PR plan | Preservar `repo:alric-corp@178685987/alric-containers-image-base@1360616627:pull_request`; impor base `develop` pelos guards, inclusive na retirada dos YAMLs antigos de `main` |
| Infra apply | Preservar `repo:alric-corp@178685987/alric-containers-image-base@1360616627:environment:lab-image-base-infra`; ajustar a branch permitida no environment |

Audience `sts.amazonaws.com`, issuer, repository ID `1360616627`, owner ID
`178685987`, conta `712107929769`, regiões e permissões permanecem iguais.
A policy versionada é configuração desejada, não prova de aplicação. Não
há necessidade de wildcard, nova role ou ampliação de permissões.

## Classificação de referências a main

| Categoria | Ocorrências / tratamento |
| --- | --- |
| `DEV_EXECUTION_ASSUMPTION` | Triggers, guards, signer/source ref, source run de certificação e filtro health migrados para `develop`; docs operacionais acompanham o contrato |
| `DOCUMENTATION_STALE` | README, runbooks, contratos atuais de consumo/IAM/Infra e contribuição atualizados; Settings externos continuam explicitamente pendentes |
| `FUTURE_PROD_REFERENCE` | Modelo `main = PROD futuro`, sem implementação ou credenciais PROD; mantido |
| `HISTORICAL_EVIDENCE` | SHAs, runs, baseline de ADRs, README histórico, `infra/rehearsal-evidence.md`, `infra/repository-preconditions.md`, snapshot `TODO/ALRIC-CONTAINERS-IMAGE-BASE-FLOW.md`, levantamentos corporativos e evidências de `main` mantidos com indicação histórica |
| `GENERIC_GIT_REFERENCE` | CI genérico em `main`, teste negativo da branch antiga, links upstream `blob/main`, arquivos `main.tf`/`main.go`, funções `main()` e referências à configuração remota ainda não migrada permanecem |

O pacote `TODO/` inclui instruções e evidências do port corporativo; não é
configuração executável deste LAB. Suas referências futuras a HOM/PROD e
instruções originais não autorizam implementá-los nesta entrega. `.iupipes.yml`
não existe nesta baseline; nenhum arquivo desse tipo é criado pela migração.
