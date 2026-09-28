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
   **Corrigir os YAMLs não basta:** reexecuções de runs históricos reutilizam
   SHA e ref originais. Siga [Retirada da autorização histórica](#retirada-da-autorizacao-historica).
5. Confirme branch protection, checks, trust e environment, além da evidência F
   da retirada histórica. Só então altere a default branch:

   ```sh
   # Comando preparado; executar somente com autorização de cutover.
   gh api --method PATCH repos/alric-corp/alric-containers-image-base \
     -f default_branch=develop
   ```

6. Releia Settings e valide que os próximos schedules usam o SHA de `develop`.
   Confirme que dispatch de `main` e PR para `main` não alcançam AWS DEV,
   sem executar publicação/promoção como parte desta migração. Build,
   certificações, soak e stable reais dependem de autorização operacional própria.

O health exige `develop` somente onde o run é evidência de operação DEV:
atribuição de schedules e publicação/promoção por framework. Runs analisados
e fila mantêm a população da janela, inclusive PRs `feature/* -> develop`,
cujo `head_branch` é a feature. O início da nova série de schedules pode
acusar falta de histórico; não reduza thresholds nem use runs de `main` para
preencher essa lacuna.

O GitHub executa schedules a partir da default branch. Enquanto ela for
`main`, as definições antigas continuam sendo as definições agendadas; trocar
apenas o guard local não altera esse comportamento remoto. Não há mudança de
cron ou promessa de pontualidade do scheduler.

<a id="retirada-da-autorizacao-historica"></a>
## Retirada da autorização histórica

O GitHub permite reexecutar um run por até 30 dias, com o SHA e a ref
originais ([documentação](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)).
A reexecução pede um token OIDC novo; se a trust aplicada ainda aceitar o
subject, a AWS emite credenciais novas. Alterar YAML em `develop` ou `main`
não altera esses runs.

### Inventário somente leitura (28/09/2026)

| Caminho | Runs elegíveis | Subject aplicado na AWS | Aceita rerun antigo? |
| --- | --- | --- | --- |
| Infra PR plan | 6 runs com base `main` (PRs #89, #93, #94, #98 ×2, #99), todos com `Configure Infra plan credentials = success`; o mais recente, [35568076949](https://github.com/alric-corp/alric-containers-image-base/actions/runs/35568076949), é de 2026-09-21T06:20:54Z | `…:pull_request` (sem base) | **Sim**, até ~2026-10-21T06:20Z |
| Infra apply | 2 dispatches em `main` (35482328892, 35482563600), 2026-09-20 | `…:environment:lab-image-base-infra`; environment com reviewers e branch policy `main` | Sim, com aprovação de reviewer, até ~2026-10-20T01:53Z |
| Produto (build, promoção, recovery, certificações, health) | Runs de `main` na janela: `workflow.yml` 142, `promote-stable.yml` 60, `pipeline-health.yml` 20, `recover-stable.yml` 3, catalog 1, app 1 | `…:ref:refs/heads/main` | Sim, enquanto a trust aceitar `main` |

As três roles têm `MaxSessionDuration = 3600`. Sessões emitidas pelos runs
de 20–21/09 já expiraram; o risco são credenciais **novas** emitidas por
reexecução. Mudar a trust não encerra sessões já emitidas: ao aplicar a
suspensão, aguarde 1 hora ou revogue explicitamente as sessões anteriores.

### Plano

**A. O que suspender antes de publicar `develop`.** A trust da role de plan,
porque o subject `:pull_request` não distingue a base e é o único caminho
que nem a troca de trust do produto nem a restrição do environment cobrem.
Os caminhos mutáveis de produto e apply ficam congelados operacionalmente
(sem dispatch, recovery ou apply manual) até o passo C.

**B. Como impedir credenciais novas para rerun antigo de `main`.**

- Infra PR: remover temporariamente a instrução `Allow` da trust de plan,
  sem outro subject, sem wildcard e sem claim nova, até a janela de 30 dias
  do último run elegível com base `main` expirar. Com a margem de um dia, a
  data é 2026-10-22.
- Produto: a trust com o subject exato de `develop`, sem `main`, faz o
  `AssumeRoleWithWebIdentity` de qualquer rerun de `main` falhar.
- Infra apply: com a branch policy do environment trocada para `develop`, um
  job de rerun com ref `main` não é elegível para o environment.

Apagar os runs históricos também encerraria a elegibilidade, mas é
irreversível e destrói evidência citada; só com decisão explícita.

**C. Controles externos a mudar**, todos sob autorização própria e por IaC
revisado quando aplicável:

1. Trust da role `…-infra-plan`: suspensa até 2026-10-22.
2. Trust da role de produto: subject exato `ref:refs/heads/develop`.
3. Environment `lab-image-base-infra`: branch policy `main` → `develop`,
   preservando reviewers.
4. YAMLs de `main`: alteração revisada que remova ou guarde os caminhos AWS,
   para que PRs novos para `main` não reabram a janela de rerun depois da
   restauração da trust de plan.

**D. Impacto no Infra PR atual.** Durante a suspensão, PRs para `develop`
executam `Test Infra contracts without AWS credentials`, mas o job de plan
falha ao assumir a role. Mudanças de Infra aguardam a restauração, ou seguem
por apply com reviewer quando autorizadas. Se o job de plan for required
check, esses PRs ficam bloqueados nesse período.

**E. Restauração segura.** Depois de 2026-10-22, e somente com o item C.4
aplicado em `main`:

1. Reaplicar a trust de plan com o mesmo subject exato
   `repo:alric-corp@178685987/alric-containers-image-base@1360616627:pull_request`,
   `repository_id` e `repository_owner_id`, sem ampliar nada.
2. Validar com um PR interno para `develop` (plan executa) e confirmar que
   um PR para `main` não chega ao step de credenciais.

**F. Evidência de que a autorização antiga morreu:**

- `aws iam get-role` das três roles: plan suspensa e depois restaurada com
  o subject exato; produto só com `refs/heads/develop`.
- `deployment-branch-policies` do environment listando somente `develop`.
- Inventário de Infra PR com base `main`: todos os runs com `created_at`
  anterior a 30 dias no momento da restauração, e nenhum run novo com base
  `main` depois do item C.4.
- CloudTrail `AssumeRoleWithWebIdentity`: nenhuma emissão para as roles de
  plan e produto a partir de ref, base ou run de `main` após a suspensão;
  eventos negados, se houver, registrados como evidência.
- Nenhum run histórico foi reexecutado para produzir essa prova.

## IAM e OIDC

| Caminho | Subject / impacto externo |
| --- | --- |
| Produto: build, promoção e recovery | Substituir o subject ref-based exato por `repo:alric-corp@178685987/alric-containers-image-base@1360616627:ref:refs/heads/develop` na role de produto aplicada |
| Infra PR plan | Suspender até 2026-10-22 e depois restaurar exatamente `repo:alric-corp@178685987/alric-containers-image-base@1360616627:pull_request`; impor base `develop` pelos guards, inclusive na retirada dos YAMLs antigos de `main` |
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
