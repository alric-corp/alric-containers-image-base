# M09/M16: ferramentas e fronteiras de confiança

Primeira parte preparada sobre `97c3cb4` (M12, PR #19); trazida depois para
a `main` de então (`432da4e`, já com M13/M14/M15) e novamente, após uma
revisão externa, para a `main` atual (`81c8f4e`, com os bumps do Dependabot
em `aquasecurity/setup-trivy`, `actions/cache` e `actions/setup-node`). Não
altera identidades de assinatura, trust policy AWS, Environments nem o
workflow gerado de triagem.

## Implementação

- Todos os checkouts dos workflows mantidos à mão usam `persist-credentials:
  false` — sete passos em cinco workflows, incluindo `recover-stable.yml`,
  que entrou na `main` (M15) depois da primeira parte desta branch. Nenhum
  passo desses jobs faz push por Git.
- Guard de entrada antes de qualquer credencial AWS, compartilhado por
  build, validação, promoção e recuperação
  ([validate_inputs.py](../scripts/pipeline/catalog/validate_inputs.py)): nomes únicos
  do catálogo `frameworks/*.yaml`, soak finito e não negativo (zero continua
  válido para os testes autenticados já previstos) e digest no formato
  `sha256:<64 hex>`. A recuperação passava por uma checagem própria em shell
  que aceitava qualquer caminho terminando em `.yaml` existente
  (`../frameworks/go1-26` passava); agora exige o padrão do nome **e**
  pertinência ao catálogo. O input rejeitado não é ecoado de volta no log.
- Nenhuma entrada é interpolada dentro de um `run` nos jobs privilegiados:
  `matrix.framework` (publicação) e `inputs.soak-hours` (promoção) passaram a
  chegar por `env:` e ser usadas com aspas. Os dois vinham, em última
  instância, de input de `workflow_dispatch`.
- Regra virou lint, não faxina de uma vez só:
  [lint_workflow_hardening.py](../scripts/pipeline/governance/lint_workflow_hardening.py)
  roda no check obrigatório `lint-workflows` e reprova checkout sem
  `persist-credentials: false`, expressão dentro de `run`, job executor sem
  `timeout-minutes`, workflow sem `permissions` no topo e Action externa sem
  SHA completo. Rodado contra os workflows da `main` de hoje, aponta
  exatamente as nove lacunas que esta branch corrige — é a prova de que o
  lint pega o problema real, não só o estado já limpo.
- Melange acompanha o artifact do bundle com seu arquivo de versão.
  Apko/Trivy, cosign/AWS/Docker e cosign/Trivy/AWS/gh/buildx têm suas versões
  registradas por etapa, com commit/run/tentativa, junto dos artifacts
  existentes. Skopeo mantém arquivo de versão e verificação de
  disponibilidade antes da AWS. O coletor não exporta ambiente nem secrets.
- Código não confiável em contexto privilegiado: nenhum workflow mantido à
  mão usa `pull_request_target`, `issue_comment` ou `workflow_run`. PRs entram
  por `pull_request`, que roda com token de leitura e sem OIDC. O único
  `workflow_run` do repositório está no `cve-triage.lock.yml` gerado, que já
  condiciona a execução a `workflow_run.repository.id == github.repository_id`
  e `!workflow_run.repository.fork`, e cujo gatilho automático está pausado.
  Nenhum job faz checkout de uma ref controlada pelo autor do PR.
- Campos de diagnóstico: nenhum workflow imprime `toJSON(github)`, `printenv`
  ou dump de ambiente. O coletor de versões grava só a saída dos comandos de
  versão em allowlist, mais commit/run/tentativa. Verificado por varredura nos
  seis workflows e coberto por teste (`test_records_versions_without_secrets`).
- `renovate.json` prepara propostas semanais de atualização dos digests de
  apko, melange, Skopeo e actionlint nos workflows/Makefile. Só o manager
  customizado, sem concorrer com o Dependabot de Actions, sem tocar o lock
  gerado e sem automerge. Nenhum digest foi atualizado por esta entrega.

## Configuração remota: observada e alterada em 09/09/2026

Antes de alterar, o estado foi lido pela API — não presumido pela presença de
arquivo. Alterações feitas com autorização explícita do responsável.

| Controle | Antes | Depois |
| --- | --- | --- |
| Secret scanning | desativado | **ativado** |
| Push protection | desativado | **ativado** |
| `sha_pinning_required` (Actions) | `false` | **`true`** |
| Acesso do time `github_xj7_maintainer` ao repo | **nenhum** | `write` |
| CODEOWNERS | 100% comentado, inerte | regras ativas e comprovadas no PR #41 |
| Revisão obrigatória de PR | não configurada | 1 aprovação + code owner + dismiss stale |
| Required checks (`test`, `lint-workflows`) | obrigatórios | inalterado |
| `enforce_admins` | encontrado `false` numa revisão externa posterior | **`true`** (reaplicado) |
| Default token do Actions | `read`, sem aprovar PR | inalterado |
| `allowed_actions` | `all` | inalterado |
| Dependabot security updates | desativado | inalterado (fora do pedido) |
| Rulesets | lista vazia | inalterado — vazio **não** significa ausência de branch protection |

Detalhes que mudam a leitura desses controles:

- O time `github_xj7_maintainer` existia, com um membro, e **não tinha acesso
  nenhum a este repositório**. Code owner sem permissão de escrita é ignorado
  pelo GitHub: as regras comentadas não teriam funcionado nem se
  descomentadas. Por isso o acesso de escrita veio antes de ativar a revisão.
- `@vigcf` (admin do repositório) entra como dono adicional no CODEOWNERS
  para a regra ser satisfazível: o time tem um membro só e ninguém aprova o
  próprio PR — com `enforce_admins: true`, admin também não contorna.
- O GitHub lê o CODEOWNERS da **branch base** do PR. As regras deste arquivo
  só valem para PRs abertos depois que ele estiver na `main`; este PR ainda é
  avaliado pelo CODEOWNERS inerte da `main`, então cai na exigência simples
  de uma aprovação.
- `sha_pinning_required` só foi ativado depois de conferir que todos os
  `uses:` do repositório já estão em SHA de 40 caracteres — inclusive os do
  `cve-triage.lock.yml` gerado, que não é editado à mão.
- Consequência operacional imediata: com `enforce_admins: true` e uma
  aprovação obrigatória, este próprio PR precisa da aprovação do outro admin
  para entrar. Isso é o comportamento pretendido, não um efeito colateral.
- **`enforce_admins` regrediu para `false` entre a entrega original e uma
  revisão externa posterior (achado real dessa revisão, não presumido).** A
  API de proteção da `main` confirmou o valor `false` sem nenhum ruleset
  compensatório — nesse estado, um administrador contornava a revisão
  obrigatória mesmo com a documentação afirmando o contrário. Reaplicado via
  `POST .../branches/main/protection/enforce_admins` e reconfirmado `true`.
  Este plano não tem acesso ao audit log de organização (recurso Enterprise)
  para determinar a causa da regressão; não presumir que o valor
  permanecerá estável sem reverificação periódica.

## Aceite

- [x] Entradas inválidas falham antes da autenticação AWS: o guard é o passo
  seguinte ao checkout, antes de `configure-aws-credentials`, nos quatro
  workflows que autenticam. Coberto por testes de unidade e de CLI (exit
  code, catálogo, traversal, digest malformado, input não ecoado).
- [x] Checks não precisam de credencial Git persistida: `test` e
  `lint-workflows` rodam com `persist-credentials: false` e o lint reprova
  qualquer checkout novo que esqueça a opção.
- [x] Entradas inválidas falham antes da AWS **num dispatch real**, não só
  em teste local: ver "Dispatch real com entrada inválida" abaixo.
- [x] Proteção de revisão demonstrada em PR de teste, nas duas camadas:
  esta PR (#28) ficou `REVIEW_REQUIRED`/`BLOCKED` até `vigcf` aprovar (a
  aprovação anterior, no SHA `12ec2ed`, foi descartada por
  `dismiss_stale_reviews` após mais um push de documentação; a aprovação
  válida foi no SHA `ef04072`), mesclada como `53e7d14`. Com o CODEOWNERS já
  ativo na `main`, [PR #41](https://github.com/alric-corp/alric-containers-image-base/pull/41)
  (descartável, um comentário em `.github/workflows/test-promotion.yml`)
  comprovou a exigência **específica** de code owner pós-merge: o GitHub
  computou `@vigcf` e o time `@alric-corp/github_xj7_maintainer` como
  revisores exigidos direto do CODEOWNERS (`codeowners/errors` vazio), o PR
  ficou bloqueado antes de qualquer aprovação, e só liberou depois de `vigcf`
  — code owner de fato para esse caminho — aprovar. Mesclado como `d3ccafd`.
- [ ] Ativar Renovate com acesso somente a este repositório e comprovar o
  primeiro PR real de digest, incluindo atualização consistente de todas as
  ocorrências, disponibilidade multi-arch, lint/build/scan e revisão humana.
- [ ] Validar as alterações em publicação/promoção autenticadas e conferir os
  artifacts com versões e ausência de credenciais persistidas.
- [ ] Testar fork (pertence ao M05) e falhas/cancelamentos conforme os
  demais critérios. O job com permissão OIDC continua autorizado a obter
  tokens; o guard impede chegar ao passo AWS com input inválido, não
  constitui uma nova fronteira de IAM.
- [ ] Decidir política/automação de versões Trivy/cosign além dos pins das
  Actions e acompanhar os PRs Dependabot. Registro de versão não é
  atualização. M09 permanece parcial.

## Dispatch real com entrada inválida

Dois `workflow_dispatch` reais de `recover-stable.yml` na branch desta PR,
depois do merge com a `main` atual:

- [Run 34415174826](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34415174826):
  `framework=../frameworks/go1-26` (fora do catálogo, mesmo traversal que a
  checagem antiga em shell aceitava).
- [Run 34415195003](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34415195003):
  `framework=go1-26` válido, `digest=sha256:not-a-real-digest` malformado.

Os dois falharam no passo `Validate inputs before privileged operations` com
a mensagem exata `"Invalid workflow inputs: use unique framework names from
the catalog, a finite nonnegative soak and a sha256:<64 hex> digest."` — e
`Configure AWS credentials (OIDC)` e todos os passos seguintes aparecem como
`skipped` no job, confirmando que a autenticação AWS nunca foi tentada.
Nenhum dispatch com input válido foi executado como controle: o próximo passo
do workflow depois do guard já reescreveria `stable` de um repositório real
(`docker buildx imagetools create`), o que exigiria autorização separada.

## Autoria solicitada pelo mantenedor

`AGENTS.md` registra Codex como autor principal dos commits que Codex
implementar: `git commit --author='Codex <codex@openai.com>' ...`. A
identidade Git do operador permanece como committer, sem configuração global
alterada. Autoria não confere acesso ao repo, assinatura verificada nem
endosso da OpenAI. Não reescrever histórico anterior.

## CI real

- Primeira parte, commit `8f64de1`: [checks rápidos](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34396480166)
  aprovados e [build/scan](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34396480594)
  com bundle e 14/15 frameworks aprovados, incluindo os seis pares
  runtime/dev do M07. Único bloqueado: `dotnet8`, no scan. Publicação e
  promoção não executam em PR, por desenho.
- Segunda parte: [run 34412945439](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34412945439),
  `test` e `lint-workflows` aprovados, com o step `Workflow hardening rules`
  `success` no runner — o lint novo roda de verdade no check obrigatório, não
  só localmente.
- A API do GitHub retornou `author.login: codex` para o commit `8f64de1`,
  confirmando o vínculo da autoria da primeira parte ao perfil
  https://github.com/codex.

## Validação local

- 81 testes de pipeline e 13 de certificados aprovados. Novos nesta parte:
  digest válido/inválido, CLI do guard (framework único, traversal, input não
  ecoado, variável ausente) e dez casos do lint de hardening.
- `actionlint` aprovado nos seis workflows mantidos à mão;
  `lint_workflow_hardening.py` aprovado na branch e reprovando as nove
  lacunas da `main`; `git diff --check` sem erros.
- Renovate 44.74.0: `renovate-config-validator --strict renovate.json`
  aprovado na primeira parte; o serviço de atualização não foi executado.
