# Progresso — ativação DEV

> Consolidação das evidências mostradas no `PROGRESSO.md`.
>
> Este documento funciona como checkpoint para troca de sessão. A baseline de origem relata implementação, mas os marcos abaixo só devem ser marcados como concluídos quando houver evidência da revisão/execução no ambiente correto.

---

## 1. Baseline da execução

```text
REPOSITORIO = itau-corp/itau-xj7-container-image-base
BRANCH_ATUAL = develop

BASELINE_SHA_COMPLETO = 2801363f11fffff715952a33a0b70d37e5ae9cfc3
REUSABLE_SHA_COMPLETO = 129a2ef2d4ffa036212fa5eb26e6b899373f75a3

AWS_CONTA_DEV_CONFIRMADA = 173574590485
AWS_REGIAO_DEV_CONFIRMADA = sa-east-1

ULTIMO_MARCO_TRABALHADO = M05
PROXIMO_MARCO = M06 ou M07 em paralelo

PROMOCAO_AUTORIZADA = NAO
```

### Observações da baseline

- O reusable foi **re-pinado em 2026-09-23**.
- Antes do re-pin, a referência `1e516411` ainda utilizava o runner anterior.
- A conta DEV foi confirmada contra a configuração `.iupipes.yml`.
- A região DEV é `sa-east-1`.
- O `M05` confirmou um **Terraform plan verde e legítimo**.
- O erro de OIDC do **IUConfia/Sonar** é lateral ao Terraform e não invalida `plan/apply`.
- O kill switch de promoção permanece fechado porque `STABLE_PROMOTION_AUTHORIZED` não está presente no nível do repositório.
- A promoção para `stable` deve continuar fazendo `skip` enquanto o kill switch não for explicitamente autorizado.

> **Segurança:** não registrar secrets neste arquivo. IDs e contas só devem permanecer no repositório se isso estiver de acordo com a política corporativa.

---

# 2. Marcos

| Marco | Escopo | Estado | Evidência / observação |
|---|---|---|---|
| **M00** | Registrar baseline e escopo de DEV | **CONCLUÍDO** | `HEAD 2801363 @ develop`; CI leve `35755593711 = success`; Build/Publish/Infra cancelado porque o golden path não executou |
| **M01** | Fechar Settings, variáveis e aprovações do GitHub | **CONCLUÍDO** | `default=develop`; repo vars vazio porque runners/vars são org-level; kill switch fechado; environment `dev` existe; branch protection aplicada em 2026-09-23 |
| **M02** | Provar checkout e acesso ao reusable no ARC | **CONCLUÍDO** | Run `35755595108`; `registry.yml@1e516411` resolvido por SHA; nested jobs `validate` + `source-control` com sucesso no ARC; sem `403` |
| **M03** | Provar capacidades de build e rede do ARC | **BLOQUEADO** | Docker/QEMU/melange funcionaram parcialmente; causa raiz dos erros identificada como **egress para Wolfi**. Ainda há confirmação pendente de `--privileged` no scale-set ARC |
| **M04** | Vincular identidades, IAM e OIDC ao DEV real | **PARCIAL** | Policy/docs/trust JSON/tests alinhados; 17 testes ligados ao escopo passaram; OIDC da infraestrutura DEV comprovado; prova de auth do publisher continua pendente |
| **M05** | Revisar plano de infraestrutura DEV | **CONCLUÍDO** | PR #9, run `35881599616`; plan verde, somente `+create`, sem destroy/replace |
| **M06** | Aplicar e verificar infraestrutura DEV | **NÃO VERIFICADO** | Apply autorizado, mas ainda não executado/validado no checkpoint |
| **M07** | Fechar certificados e confiança corporativa | **CONCLUÍDO** | 11/11 certificate checks verdes + `image-trust-gate PASS`, run `35910364212` após rerun |
| **M08** | Publicar primeiro candidate Go em DEV | **NÃO VERIFICADO** | Candidate `go1-26` ainda não publicado |
| **M09** | Promover e verificar primeiro stable DEV | **NÃO VERIFICADO** | Depende do fluxo de candidate e da autorização de promoção |
| **M10** | Ativar e observar operação agendada | **NÃO VERIFICADO** | — |
| **M11** | Certificar catálogo completo em DEV | **NÃO VERIFICADO** | — |
| **M12** | Executar aplicações consumidoras nas duas arquiteturas | **NÃO VERIFICADO** | — |
| **M13** | Validar recovery DEV e fechar o aceite | **NÃO VERIFICADO** | — |

Estados usados:

```text
NÃO_VERIFICADO
EM_ANDAMENTO
PARCIAL
BLOQUEADO
CONCLUÍDO
```

---

# 3. Detalhamento dos marcos concluídos

## M01 — GitHub Settings e proteção da `develop`

A proteção da branch `develop` foi aplicada em **2026-09-23** com:

- required status checks estritos;
- `Unit & integration tests`;
- `Repository & workflow lint`;
- 1 aprovação obrigatória;
- descarte de reviews stale;
- aprovação de CODEOWNERS;
- force push bloqueado;
- exclusão da branch bloqueada;
- `enforce_admins=false`.

O job `infra-registry` não foi incluído como required check porque é condicional.

---

## M03 — Build, arquitetura e rede do ARC

O teste confirmou que:

- Docker/QEMU estão disponíveis;
- `melange` conseguiu executar com `--privileged` em cenário parcial;
- foram gerados pacotes `.apk` para `amd64` e `arm64` a partir de cache.

A causa raiz dos erros observados não era o código da factory.

### Causa raiz

O runner ARC não alcançava diretamente:

```text
packages.wolfi.dev
34.160.111.32
```

Os requests apresentavam:

```text
connection reset by peer
```

inclusive em:

```text
HEAD APKINDEX.tar.gz
GET *.apk
```

Com isso, `apko lock/build` não conseguia consultar um índice fresco.

**Diagnóstico:** problema de egress/rede/proxy corporativo.

---

## M04 — Identidade, IAM e OIDC

Foi confirmado:

- identidade do repositório preenchida;
- identidade do owner preenchida;
- conta DEV associada;
- `policy + docs + trust JSON + tests` alinhados;
- **17 testes relevantes verdes**;
- OIDC de infraestrutura DEV validado com `AssumeRole=success`.

Continuam em aberto:

1. prova de autenticação do `PUBLISHER` em um build real;
2. decisão/hardening da trust implementada com `StringLike:*` versus template mais restritivo.

---

## M05 — Terraform plan DEV

Run:

```text
35881599616
```

Resultado:

```text
PLAN VERDE E REVISADO
```

O plan mostrou:

- somente `+create`;
- ambiente greenfield;
- `0 destroy`;
- `0 replace`;
- **48 recursos**;
- **16 frameworks**;
- para cada framework:
  - `repository`;
  - `lifecycle_policy`;
  - `repository_policy`.

### Configuração esperada por repositório

```text
image-base-<framework>
```

Características:

- `IMMUTABLE_WITH_EXCLUSION`;
- exceção/wildcard para `stable`;
- criptografia `AES256`, sem KMS;
- `scan_on_push`;
- `force_delete=false`;
- tags:
  - `ManagedBy`;
  - `Source`;
  - `Environment=dev`;
- lifecycle protegendo `stable`;
- expiração das demais imagens em aproximadamente 7 dias;
- org-pull para os 5 Org IDs corporativos;
- conta DEV em `sa-east-1`.

O erro OIDC do IUConfia/Sonar foi classificado como lateral e benigno para o Terraform.

---

# 4. M07 — Certificados e confiança corporativa

## Resultado

```text
11/11 Certificate VERDES
image-trust-gate PASS
run 35910364212
```

O gate ficou verde após rerun de um job.

O diagnóstico anterior de que `apko exit 1` era a causa central estava incorreto. Os componentes abaixo permaneciam verdes:

- `apko`;
- `melange`;
- `SBOM`;
- `oci_artifact`.

Foram identificados **3 bugs distintos de runtime/cross-platform**, sem relação direta com trust.

### Bug 1 — diretório temporário não compartilhado no DinD

Commit:

```text
370e2c0
```

Problema:

- o contrato usava `/tmp`;
- o `.tar` gerado pelo `skopeo` não estava no filesystem compartilhado pelo DinD;
- `docker load` não encontrava o artefato.

Correção:

```text
tempdir -> dir-layout.parent
```

---

### Bug 2 — permissão do `build.sh` Java

Commit:

```text
e27f1e1
```

Problema:

```text
build.sh = 100644
```

No checkout Linux, o bit executável não estava disponível, resultando em:

```text
exit 126
permission denied
```

Correções:

- ajuste da permissão para `100755`;
- execução explícita com:

```bash
sh ./build.sh
```

---

### Bug 3 — pull do `skopeo` sem retry

Commit:

```text
5820b2d
```

Problema:

- `pull()` implícito do `skopeo`;
- EOF transitório do CDN do `quay.io`.

Correção:

- implementação de retry no `pull()`.

Foi confirmado que `quay.io` estava acessível, com **21/22 pulls OK**, portanto não precisava de mirror como o `wolfi.dev`.

### Testes

```text
13/13 unit tests verdes
```

Os fixes foram validados nos runtimes:

- Go;
- Java;
- .NET;
- Node;
- Python.

---

# 5. Checkpoint da última sessão

```text
DATA_UTC = 2026-09-23
MARCO = M07 (CONCLUIDO)
MARCO_ANTERIOR = M05
```

## Estado

PR em trabalho:

```text
PR #9
feat/dev-activation-repin-orgids
```

Estado consolidado:

- certificate trust verde ponta a ponta;
- 11/11 frameworks verdes;
- `image-trust-gate PASS`;
- mirror Wolfi validado;
- CA compatível com DinD;
- `melange + apko TLS PASS`;
- reusable validado;
- fixes de runtime validados no CI;
- unit tests verdes.

## Arquivos alterados no checkpoint

Principais pontos:

```text
scripts/pipeline/runtime/runtime_images.py
runtime/projects/java/Dockerfile
runtime/projects/java/build.sh
tests/unit/pipeline/runtime/test_runtime_images.py
PROGRESSO.md
```

Mudanças relevantes:

- tempdir usando `layout.parent`;
- retry do `pull()`;
- correção do build Java;
- testes atualizados.

## O que ainda não foi executado

- merge do PR #9;
- M06 — apply DEV + read-back;
- M08 — publicação do candidate `go1-26`;
- prova real de autenticação do `PUBLISHER` com OIDC.

No checkpoint:

```text
PENDENTE_COMMIT = --
```

Tudo estava commitado; faltava confirmar o CI do último HEAD.

### Próxima ação registrada

```text
confirmar CI verde no HEAD 5820b2d
→ merge PR #9
→ reabrir M06 (apply)
→ executar M08 (candidate go1-26)
```

---

# 6. Baseline Windows — falhas conhecidas

As falhas de baseline Windows não foram associadas ao M04.

Problemas observados:

- `UnicodeDecodeError` relacionado a `cp1252`;
- exemplo em `test_pin_inventory`;
- privilégio/symlink em `test_wolfi_trust`;
- pin de QEMU em `test_immutable_qemu_pattern`;
- diferenças de path separator em `test_unsafe_zip_paths`.

Resumo:

```text
governança: 5 fail + 6 error
```

Essas falhas não tocavam diretamente os arquivos de policy/identity do M04.

Os **17 testes que consumiam os arquivos alterados no M04 passaram**.

Também foi corrigida a referência dos prompts operacionais:

```text
antes: marcos-dev/
agora: TODO/
```

---

# 7. Bloqueios, pendências e decisões

| Item | Estado | Responsável | Critério de liberação |
|---|---|---|---|
| Hardening da trust DEV | **Opcional / decidido não bloquear** | Cloud/IAM, se priorizado | Migrar para `StringEquals`/develop-only + IDs numéricos, ou manter formalmente a decisão atual |
| Prova de auth do PUBLISHER | **PENDENTE** | Cloud/IAM / pipeline | Build real com `Configure AWS credentials (OIDC) = success` |
| Egress Wolfi | **MITIGAÇÃO IMPLEMENTADA E VALIDADA** | Pipeline/Plataforma | Mirror + CA funcionando no fluxo real; confirmar continuidade no candidate |
| OIDC IUConfia/Sonar | **BENIGNO / NÃO BLOQUEIA** | Cloud/IAM, se quiser limpar o log/habilitar Sonar | Ajustar trust do `iuconfia-action-ssm` ou formalizar que o token/Sonar não se aplica à factory |
| Org IDs da org-pull policy | **RESOLVIDO** | — | 5 Org IDs corporativos aplicados; 19 testes ECR verdes |
| `docker run --privileged` no ARC | **PENDENTE** | Plataforma / Infra ARC | Um run onde `Build CA package (amd64+arm64)` finalize com sucesso ou confirmação oficial da plataforma |
| Re-pin do reusable | **RESOLVIDO** | — | PR #6 do reusable mergeado; image-base re-pinado |
| Branch protection `develop` | **RESOLVIDO** | Admin | API retornou 200 e 2 required contexts |
| Variáveis org-level `RUNNER_EKS_OD_*` / `AWS_*` | **PENDENTE DE CONFIRMAÇÃO** | Infra/K8s + Cloud | Consultar org variables ou comprovar em job real |
| `CODEOWNERS` vs `health.json` | **PENDENTE DE GOVERNANÇA** | Usuário / governança | Definir fonte de verdade e confirmar se o time `@itau-corp/xj7-maintainer` deve ser usado |

---

# 8. Mirror Wolfi no Artifactory

Foi criado e validado:

```text
https://artifactory.prod.aws.cloud.ihf/artifactory/wolfi-remote
```

Validações observadas:

- `APKINDEX` retorna `200 OK`;
- `x86_64`;
- `aarch64`;
- `Content-Type: x-gzip`;
- leitura anônima disponível;
- TLS exige CA corporativa.

O primeiro redirecionamento para o mirror funcionou, mas houve:

```text
x509: unknown authority
```

dentro do container `melange`.

## Implementação inicial

Foram adicionados:

```text
WOLFI_CA_BUNDLE
WOLFI_REPOSITORY_URL
```

Com:

- mount do CA;
- `SSL_CERT_FILE`;
- redirect do `certificate_contract`;
- passagem das variáveis pelo `image-trust.yml`.

## Abordagem final — DinD-safe

Em vez de montar um path absoluto do host, a estratégia final foi:

1. copiar o CA para o workspace montado;
2. usar:

```text
SSL_CERT_FILE=/work/corporate-ca.crt
```

3. definir:

```text
WOLFI_CA_SOURCE
```

como path do CA **dentro do runner**.

Default esperado quando o mirror está habilitado:

```text
/etc/ssl/certs/ca-certificates.crt
```

### Alterações no image-base

PR #9, commit:

```text
1ea1003
```

Alterações:

- `build_image.py`;
- `certificate_contract.py`;
- `image-trust.yml`;
- `validate-base-images.yml`;
- caller inputs.

### Alterações no reusable

PR #8:

```text
feat/wolfi-ca-source
```

Incluiu:

- input `wolfi-ca-source`;
- cópia do CA no `docker run` do `melange`;
- `WOLFI_CA_SOURCE` enviado ao `build_image`.

Resultado observado no PR #9:

```text
melange + apko TLS OK contra mirror
validate verde
```

---

# 9. IUConfia / Sonar

O step:

```text
Get secrets from AWS Secrets Manager
```

tenta assumir:

```text
iuconfia-action-ssm
```

para buscar:

```text
GH/FF2/PIPELINE_SONAR
```

e retorna erro semelhante a:

```text
Not authorized sts:AssumeRoleWithWebIdentity
```

Esse comportamento foi classificado como:

```text
best-effort
benigno
não bloqueante para Terraform
```

As políticas do IUConfia continuaram sendo validadas.

Possíveis ações futuras:

- incluir o repositório na trust da role usada pelo IUConfia;
- ou registrar que Sonar/token não se aplica a essa factory.

---

# 10. Itens resolvidos em 2026-09-23

## Org IDs da policy ECR

O valor de LAB com apenas uma organização foi substituído pelos **5 Org IDs corporativos reais**.

Arquivos envolvidos:

```text
infra/ecr/policies/ecr-repository-org-pull.json
fixture test_ecr_catalog.py
```

Resultado:

```text
19 testes ECR verdes
```

---

## Re-pin do reusable

O PR #6 do reusable foi mergeado.

Depois disso, o image-base foi re-pinado:

```text
1e516411 -> 129a2ef...
```

O re-pin afetou:

- 6 workflows;
- 3 documentos.

Resultado:

```text
workflow_dependencies verde
33 testes deps+doc verdes
```

---

## Branch protection

A proteção da `develop` foi aplicada pelo admin em 2026-09-23.

Required checks:

```text
Unit & integration tests
Repository & workflow lint
```

Também foram configurados:

- PR review;
- dismiss stale reviews;
- CODEOWNERS;
- bloqueio de force push;
- bloqueio de deleção;
- `enforce_admins=false`.

---

# 11. Comando de proteção da branch `develop`

> Executar somente com permissão administrativa e de acordo com a política corporativa vigente.

```bash
gh api -X PUT \
  repos/itau-corp/itau-xj7-container-image-base/branches/develop/protection \
  --input - <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "checks": [
      {
        "context": "Unit & integration tests"
      },
      {
        "context": "Repository & workflow lint"
      }
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": true
  },
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
```

Verificação:

```bash
gh api repos/itau-corp/itau-xj7-container-image-base/branches/develop/protection
```

Esperado:

- HTTP `200`;
- os dois required checks presentes.

---

# 12. Próximas ações recomendadas pelo checkpoint

1. Confirmar o CI verde no HEAD `5820b2d`.
2. Fazer merge do PR #9.
3. Executar o **M06**:
   - Terraform apply;
   - read-back da infraestrutura criada;
   - validação de drift/estado.
4. Executar o **M08**:
   - build real;
   - comprovar OIDC do publisher;
   - publicar candidate `go1-26`;
   - validar artefatos/digests.
5. Confirmar `docker run --privileged` no scale-set ARC em um fluxo completo.
6. Confirmar o escopo/valor das variáveis org-level:
   - `RUNNER_EKS_OD_*`;
   - `AWS_*`.
7. Resolver a fonte de verdade entre `CODEOWNERS` e `health.json`.
8. Manter a promoção para stable bloqueada até autorização explícita.

---

# 13. Resumo executivo

No checkpoint de **23/09/2026**, a ativação DEV já tinha avançado até a certificação de trust:

```text
M00 ✅
M01 ✅
M02 ✅
M03 ⛔
M04 🟡
M05 ✅
M06 ⬜
M07 ✅
M08 ⬜
M09 ⬜
M10 ⬜
M11 ⬜
M12 ⬜
M13 ⬜
```

Principais conquistas:

- Terraform plan DEV validado como greenfield e sem destruição;
- branch protection configurada;
- reusable re-pinado;
- 5 Org IDs corporativos aplicados à policy ECR;
- mirror Wolfi criado;
- trust corporativa ajustada para funcionar em DinD;
- 11/11 certificados verdes;
- `image-trust-gate PASS`;
- 3 bugs cross-platform/runtime corrigidos;
- testes unitários verdes.

Principais pendências:

- merge do PR #9;
- M06/apply + read-back;
- M08/candidate Go;
- autenticação real do publisher;
- confirmação de containers privilegiados no ARC;
- confirmação das variáveis org-level;
- decisão de governança sobre CODEOWNERS;
- promoção stable continua deliberadamente bloqueada.
