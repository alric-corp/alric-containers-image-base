# Governança do repositório — perfis LAB e corporativo (G02)

Contrato de revisão, ownership e gates de merge da branch de código `develop`.
O arquivo versionado é [`policies/governance/develop-protection.json`](../policies/governance/develop-protection.json);
o template corporativo de ownership é [`policies/governance/CODEOWNERS.template`](../policies/governance/CODEOWNERS.template).
**Este documento e esses arquivos não alteram Settings do GitHub.**

| Item | Estado |
| --- | --- |
| Perfil LAB | `OWNER_ACCEPTED_LAB_EXCEPTION`: leitura da API em 13/10/2026 igual ao contrato (`verify --profile lab` = `MATCH`) |
| Perfil corporativo | `PROPOSED_AWAITING_APPROVAL`: não aplicado; a leitura atual diverge dele por desenho (`verify --profile corporate` = `DRIFT`) |
| CODEOWNERS | Removido no LAB pelo owner em `03165e6` (09/10/2026); template corporativo só com placeholders |
| Aplicação remota | `AWAITING_APPROVAL`; nenhuma alteração de Settings foi feita |

O aceite LAB vale para a POC pessoal. Ele não é aceite corporativo, não
equivale a revisão independente e não pode ser exportado para outra
organização por cópia de configuração.

## 1. Perfil LAB: controles efetivos

Lidos pela API em 13/10/2026 (somente GET):

| Controle | Valor efetivo |
| --- | --- |
| Pull request para `develop` | Exigido, com **0** aprovações; aprovações antigas são descartadas a cada push |
| Required checks | `Unit & integration tests` e `Repository & workflow lint`, emitidos pelo app GitHub Actions (15368), com branch atualizada (`strict`) |
| Force push / exclusão de `develop` | Bloqueados |
| Rulesets | Nenhum (repositório e organização; plano free sem rulesets de organização) |
| Actions | SHA completo obrigatório; `GITHUB_TOKEN` padrão somente leitura; workflows não aprovam PR; fork exige aprovação só de first-time contributors |
| Environments `DEV` e `HOM` | Somente `develop`; sem revisor; sem bypass de administrador |
| Environment `lab-image-base-infra` | Somente `develop`; revisor obrigatório `TomasAlric`; `prevent_self_review=false` |

Depois do merge, os gates técnicos continuam fechados para publicação e
promoção (seção 5). Eles impedem publicar ou promover um artefato inválido;
não impedem integrar uma regressão de código em `develop`.

### Exceções conscientes

| Controle | LAB | Motivo registrado |
| --- | --- | --- |
| Aprovação obrigatória | 0 | Mantenedor único: o autor não aprova o próprio PR, e o time `github_xj7_maintainer` tem um membro (API 13/10/2026), sem acesso a este repositório |
| Revisão de code owner | Desligada; sem CODEOWNERS | O owner removeu `.github/CODEOWNERS` em `03165e6` (edição direta em `develop`, sem PR) |
| `enforce_admins` | Desligado | Decisão do owner para o sandbox (13/09/2026); controle previsto para o corporativo |
| Validação FULL como required check | Não | Antes do gate agregado (seção 3) o workflow era filtrado por paths; com o gate, exigi-lo no LAB é decisão do owner |
| Revisor em `DEV`/`HOM` | Nenhum | Aprovação DEV automática após gates; HOM desabilitado (`promote-hom.json`) |
| `prevent_self_review` no Environment de Infra | `false` | O único revisor é o próprio autor |

### Limites do LAB

- Um administrador pode integrar sem os checks e empurrar direto em `develop`;
  `03165e6` (`[skip ci]`, sem PR) mostra que esse caminho é usado.
- Workflows com `id-token: write` mudam sem segunda pessoa.
- Um PR pode integrar com a validação FULL ainda rodando ou reprovada.
- Checks de PR executam o código do próprio PR: alterar o teste altera o
  gate. Só revisão independente dos arquivos que definem os gates mitiga isso.
- Assinatura e provenance autenticam o resultado de uma origem aprovada; não
  detectam intenção maliciosa integrada ([ADR-0002](adr/0002-sigstore-trust-model.md)).

Permanecem com o owner: administração do repositório e dos Settings
(proteção, Environments, Actions, secrets), merge, dispatch dos workflows
manuais (recovery, Infra apply, analytics), a role IAM central externa e as
contas AWS. Há dois administradores diretos; as aprovações históricas do
segundo foram testes do mecanismo de code owner, não um processo de revisão.

O perfil LAB não serve para produção porque não comprova revisão por uma
segunda pessoa, permite bypass administrativo, não exige ownership dos
caminhos privilegiados e não bloqueia o merge de mudanças de impacto
compartilhado sem FULL aprovada.

## 2. Perfil corporativo proposto

Contrato mínimo para mudanças relevantes à Factory, aplicável depois de
aprovação e com identidades corporativas reais:

| Controle | Proposta |
| --- | --- |
| Revisão | 1 aprovação de code owner diferente do autor; aprovação do último push; descarte de aprovações antigas; conversas resolvidas |
| Administradores | `enforce_admins=true`; nenhum `bypass_pull_request_allowances`; required checks presos ao app GitHub Actions |
| Histórico | Sem force push e sem exclusão de `develop` |
| Ownership | CODEOWNERS ativo a partir do template, com slugs verificados e permissão de escrita |
| Environments | `DEV` sem revisor (aprovação automática após gates); `HOM` e Infra com revisor e `prevent_self_review=true`; somente `develop`; sem bypass |
| Actions | Manter SHA obrigatório, token somente leitura e workflows sem aprovação de PR; aprovação de forks para todos os colaboradores externos |

Pré-condição para não travar a fila: o time de mantenedores precisa de pelo
menos dois membros elegíveis com escrita, para que todo autor tenha outro
code owner disponível (seção 6).

### Ownership e mudanças de IAM e supply chain

O template aplica a semântica do GitHub: vale a última linha que casa com o
arquivo, e qualquer dono listado nela aprova. Por isso um caminho que exige
Security ou Cloud/IAM lista somente esse time.

| Classe de caminho | Dono proposto | Exemplos |
| --- | --- | --- |
| Produto, regras e gates | Mantenedores da Factory | `frameworks/`, `scripts/`, `policies/`, `tests/runtime/` |
| Workflows com `id-token: write` ou secrets | Security | `workflow.yml`, `build-base-images.yml`, `dev-stable.yml`, `promote-stable.yml`, `recover-stable.yml`, `infra-*.yml`, `renovate.yml` |
| Âncoras de confiança e identidades de assinatura | Security | `melange/keys/`, `melange/certificates/`, `policies/release/signing-identities.json`, `wolfi_trust.py`, `scripts/verify-image.sh` |
| IAM, trust OIDC e state | Cloud/IAM | `policies/aws/`, `infra/iam/`, `infra/backend.py` |
| Contratos de governança e CODEOWNERS | Security | `policies/governance/`, `.github/CODEOWNERS` |

Mudar uma policy IAM ou de trust no repositório não a aplica: a aplicação
continua externa, com plan/apply revisados e read-back
([contrato IAM](iam-permission-contract.md)). Atualizações de pins de
Actions, imagens e do executor compartilhado entram por PR com FULL e
revisão; Dependabot e Renovate não fazem automerge.

## 3. Required checks reais

| Check (nome exibido) | Origem | Reporta em todo PR para `develop`? | Pode ser required? |
| --- | --- | --- | --- |
| `Unit & integration tests` | `ci.yml` / `test` | Sim | Sim — LAB e corporativo |
| `Repository & workflow lint` | `ci.yml` / `lint-workflows` | Sim | Sim — LAB e corporativo |
| `Factory PR validation gate` | `workflow.yml` / `validation-gate` | Sim | Sim — corporativo; no LAB, decisão do owner |
| `validate-pr / …`, `Validate full catalog for shared-impact PR / …` | `workflow.yml` | Só quando selecionados; nomes dos jobs aninhados variam com a matriz | Não individualmente; o gate agregado os representa |
| `Infra contracts and formatting`, `Infra plan (same-repository PR only)` | `infra-pr.yml` | Não: filtro de paths | Não |
| `go126-requested-batch / …` | `image-trust-scope.yml` | Não: filtro de paths | Não |

Um required check cujo workflow não roda por filtro de paths fica
"esperado" para sempre e bloqueia PRs não relacionados. Um job pulado por
`if:` reporta sucesso. O `lint` deste contrato rejeita required checks que
não sejam emitidos em todo PR.

**Mudanças que exigem FULL.** `pr_execution_scope.py` seleciona FULL para
qualquer path de produto fora do recorte Go P0-04 (fail-safe) e `NONE`
quando nenhum path toca a allow-list do push de `workflow.yml` (mesma lista,
conferida por teste). O PR de `workflow.yml` roda sem filtro de paths e o
job `Factory PR validation gate` reporta em todo PR: passa somente se o
perfil foi resolvido e a validação selecionada (P0-04 ou FULL) concluiu com
sucesso; em `NONE`, nenhuma validação de imagem roda. O gate não faz checkout
nem executa código do PR. Enquanto ele não for required, a validação continua
informativa no merge e o revisor precisa confirmá-la verde antes de integrar.

## 4. Exceções e mudanças emergenciais

- **Exceção ao perfil:** registro com owner, motivo, escopo, data de
  expiração, aprovador de Security e evidência. Sem registro, a divergência
  aparece como `DRIFT` em `verify` e deve ser tratada como incidente.
- **Mudança emergencial:** segue o mesmo PR, com revisão priorizada por code
  owner diferente do autor e os mesmos checks.
- **Break-glass** (checks indisponíveis por dependência externa e correção
  urgente): administrador autorizado desliga temporariamente o controle
  estritamente necessário, integra, religa e executa `verify` em seguida.
  Registrar quem, por quê, PR, horários e leitura pós-religamento, com
  revisão posterior. Force push, exclusão de branch ou bypass sem registro
  não são caminhos de emergência.

## 5. Gates de merge × publicação × promoção

| Momento | Gates | Bloqueia |
| --- | --- | --- |
| PR → `develop` | Required checks rápidos; FULL/P0-04, trust e Infra informativos; revisão no corporativo | Integração de código |
| Push/schedule em `develop` | Validação do golden path, contratos runtime, gate de publicação, build e push, assinatura/attestations | Publicação no ECR DEV |
| Aprovação DEV | Trust, apps consumidoras, re-scan, holds e read-back | `stable` DEV e manifesto `DEV_STABLE` |
| Promoção HOM / recovery | Manifesto, soak, re-scan, trust, cópia e read-back; HOM desabilitado | `stable` HOM |

O build diário publica somente o golden path; regressões nas demais imagens
aparecem na validação FULL do PR ou na certificação FULL manual. Por isso
FULL bloqueando o merge é um controle de integração, não de publicação.

## 6. Risco de travar o mantenedor único

Aplicar o perfil corporativo neste LAB travaria a fila: o time de code owners
tem um membro, o autor não aprova o próprio PR, a aprovação do último push
exige outra pessoa e `enforce_admins` impede o administrador de contornar.
Isso já ocorreu: em 30/09/2026 `infra/lifecycle/configure_github.py` aplicou
`enforce_admins=true` com uma aprovação obrigatória
([read-back](evidence/dev-hom-bootstrap/github-readback.json)) e a proteção
foi depois devolvida ao perfil LAB. O perfil LAB atual não trava (0
aprovações, bypass administrativo); o corporativo só pode ser aplicado com
pelo menos dois mantenedores elegíveis e o break-glass da seção 4.

## 7. Verificação independente (somente leitura)

```sh
python3 -B -m scripts.pipeline.governance.repository_protection lint
python3 -B -m scripts.pipeline.governance.repository_protection verify --profile lab --json reports/governance-lab.json
python3 -B -m scripts.pipeline.governance.repository_protection verify --profile corporate --json reports/governance-corporate.json
```

`lint` é offline e também roda nos testes unitários. `verify` usa somente
GET autenticado (`gh`, com permissão de leitura da proteção) e devolve
`MATCH`/`DRIFT`; erro de leitura ou 404 ambíguo é inconclusivo (código 2),
nunca `MATCH`. Rulesets não modelados aparecem como `DRIFT`.

Depois de uma aplicação autorizada, outra pessoa confirma o perfil com
`verify` e com casos negativos em PR isolado, sem credenciais AWS: PR sem
aprovação, check obrigatório reprovado, PR com FULL reprovada (o gate deve
reprovar), PR só de documentação (o gate deve passar sem validar imagens) e
tentativa de merge administrativo. Esses testes não foram executados nesta
entrega.

## 8. Decisões pendentes do owner

1. Manter o perfil LAB como está ou registrar outra exceção datada.
2. Identidades corporativas: slugs dos times de mantenedores, Security e
   Cloud/IAM, com pelo menos dois mantenedores elegíveis.
3. Mapeamento final do template (por exemplo, se workflows privilegiados
   exigem Security ou somente mantenedores).
4. Integrar o `Factory PR validation gate` e torná-lo required (corporativo;
   opcional no LAB). Todo PR passa a abrir um run curto de `workflow.yml`.
5. Revisor em `HOM`: com o cron horário, cada execução elegível pediria
   aprovação; alternativa é promover HOM só por dispatch com revisor.
6. Uso de rulesets (com bypass restrito a break-glass) em vez de proteção
   clássica no ambiente corporativo.

## 9. Seleção, aplicação e rollback de Settings

**Perfil vigente:** LAB (`OWNER_ACCEPTED_LAB_EXCEPTION`). Ele continua o padrão
operacional até uma decisão diferente do owner; nenhum passo abaixo é
executado por merge, workflow ou script deste repositório. O perfil
corporativo não pode ser aplicado enquanto houver menos de dois mantenedores
elegíveis com escrita.

Diferenças do LAB para o corporativo (saída de `verify --profile corporate`
sobre o estado vivo do LAB):

| Controle | LAB | Corporativo |
| --- | --- | --- |
| `enforce_admins` | `false` | `true` |
| Aprovações / code owner / último push | 0 / não / não | 1 / sim / sim |
| Resolução de conversas | não | sim |
| Required checks | 2 | 3 com o gate agregado (só depois de integrado e provado) |
| Environment `HOM` | sem revisor | revisor com `prevent_self_review` |
| Environment de Infra | revisor, `prevent_self_review=false` | revisor, `prevent_self_review=true` |
| CODEOWNERS | ausente | ativo a partir do template, com slugs reais |

**Aplicação** (administrador, com autorização específica; `<perfil>` é `lab` ou `corporate`):

1. Pré-checagem: `verify --profile lab --json before.json` deve dar `MATCH`
   (estado conhecido) e o perfil escolhido deve passar no `lint`.
2. Corpo do PUT a partir do arquivo versionado:
   `jq '.profiles.<perfil>.protection' policies/governance/develop-protection.json > body.json`.
3. `gh api --method PUT repos/alric-corp/alric-containers-image-base/branches/develop/protection --input body.json`.
4. Somente no corporativo: Environments `HOM` e `lab-image-base-infra` com
   `reviewers` (ids numéricos de times/usuários), `prevent_self_review: true` e
   a mesma `deployment_branch_policy` personalizada, via
   `PUT repos/.../environments/<nome>`; CODEOWNERS ativo por PR.
5. Pós-checagem: `verify --profile <perfil>` deve dar `MATCH`. Qualquer
   `DRIFT` ou leitura inconclusiva aciona o rollback.

**Gate agregado (opcional):** primeiro um PR acrescenta
`Factory PR validation gate` ao perfil desejado no JSON; depois
`PATCH repos/.../branches/develop/protection/required_status_checks` com
`{"strict": true, "checks": [...]}` (três checks, `app_id` 15368) e `verify`.
Rollback: o mesmo `PATCH` com os dois checks do LAB.

**Rollback:** `jq '.profiles.lab.protection' ... > lab.json` e `PUT` dele;
nos Environments, `reviewers: []` mantendo a política de branch; `verify
--profile lab` deve voltar a `MATCH`. Administradores conseguem editar a
proteção mesmo com `enforce_admins` ligado, então o rollback não depende de
outro revisor. Alterar Settings não dispara workflows.
