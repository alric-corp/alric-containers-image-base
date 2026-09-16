# M12: inventário de required checks, `needs` e checks consultivos

Auditoria dos sete workflows mantidos à mão (o `cve-triage.lock.yml` gerado
fica de fora, como sempre). Objetivo: confirmar que nada consultivo está no
caminho obrigatório e que nenhum gate real foi enfraquecido para esse fim.

## Required checks (branch protection da `main`)

```
["test", "lint-workflows"]
```

Só isso. As legs de `validate-pr` (uma por framework) **não** são required
status checks — aparecem no PR, mas uma falha ali não bloqueia o merge de
código por si só. Isso é intencional, não um descuido: merge de código
(revisado por `test`/`lint-workflows`) e autorização de publicação por
framework (M13) são gates em pontos diferentes do pipeline, não a mesma
decisão. `dotnet8` falhando `validate-pr` não impede um PR de workflow ser
mesclado; impede especificamente a publicação do framework `dotnet8`, que é
o gate que importa ali.

## Grafo de `needs` nos sete workflows

| Workflow | Job | `needs` |
| --- | --- | --- |
| `validate-base-images.yml` | `melange-bundle` | — |
| | `validate` (matrix) | `melange-bundle` |
| `build-base-images.yml` | `validate` (chama o reusable acima) | — |
| | `build-push` (matrix) | `validate` |
| `promote-stable.yml` | `promote` (matrix) | — |
| `recover-stable.yml` | `recover` | — |
| `test-runtime-images.yml` | `runtime` | — |
| `test-promotion.yml` | `test` | — |
| | `lint-workflows` | — |
| `workflow.yml` | `validate-pr`, `build-base-images`, `promote-stable` | — (cada um chama um reusable) |

`build-push` `needs: validate`, mas (M13) isso não bloqueia o lote inteiro
por framework — cada leg baixa seu próprio artifact `validated-oci-<fw>` e
falha isolada se ele não existir. `needs` aqui expressa "publicação depende
de validação ter rodado", não "publicação do framework A depende do
resultado do framework B".

## Classificação: gate real vs. consultivo

| Passo | Workflow(s) | Classificação | Bloqueia o quê |
| --- | --- | --- | --- |
| `test`, `lint-workflows` | test-promotion.yml | **Gate** | Merge na `main` (required check) |
| `melange-bundle`, `validate` (scan Trivy) | validate-base-images.yml | **Gate** | Disponibilização do artifact `validated-oci-<fw>` — sem ele, `build-push` falha alto e visível para aquele framework |
| `build-push` (verificação de digest, assinatura, provenance) | build-base-images.yml | **Gate** | Publicação da tag de build daquele framework |
| Seleção de candidato, `verify_promotion.py`, re-scan | promote-stable.yml, recover-stable.yml | **Gate** | Promoção/recuperação de `stable` |
| `Report CVEs without an available fix (informational)` | validate-base-images.yml, promote-stable.yml, recover-stable.yml | **Consultivo** | Nada — nunca falha o job (ver `report_unfixed_cves.py`, `main()` sempre retorna `0`) |
| `test-runtime-images.yml` (contratos Node/Python) | test-runtime-images.yml | **Nem gate nem consultivo hoje** | Nada — `workflow_dispatch`/`workflow_call` autônomo, não chamado por `build-base-images.yml`/`promote-stable.yml`. Ver nota abaixo. |

`dotnet8` **não foi reclassificado** como consultivo para deixar o CI verde:
seu scan continua um gate real em `validate-base-images.yml`, bloqueando a
publicação desse framework especificamente — o restante do lote não é
afetado (M13), e o PR/push como um todo pode ficar `failure` por causa
disso, o que é o comportamento correto, não um bug a esconder.

`test-runtime-images.yml` está deliberadamente fora da lista de required
checks e fora do `needs` de qualquer publicador: é um workflow candidato
(M08/M10), ainda não integrado ao gate de M13. Isso é uma lacuna conhecida e
já registrada no checklist principal (M08 — parcial), não uma
reclassificação disfarçada.

## Achado real corrigido durante esta auditoria

`promote-stable.yml` e `recover-stable.yml` tinham o passo consultivo
`Report CVEs without an available fix (informational)` condicionado só a
`steps.candidate.outputs.skip == 'false'` (ou sem `if:` nenhum, no caso do
`recover-stable.yml`) — **sem** `always()`/`failure()`/`cancelled()`. Pela
semântica do GitHub Actions, um `if:` customizado sem uma dessas três
funções herda implicitamente `success()` das etapas anteriores: se o
re-scan bloqueante falhasse, este passo consultivo seria **pulado**, ao
contrário do que o próprio comentário do código sempre afirmou ("roda mesmo
se o re-scan acima já bloqueou a promoção").

Confirmado empiricamente, não só por leitura da documentação: workflow
descartável com um passo que falha de propósito seguido de dois passos
condicionais — um replicando o padrão antigo, outro com `!cancelled()` — [PR
#43](https://github.com/alric-corp/alric-containers-image-base/pull/43)
(fechado sem merge). No run real, o passo sem o guard ficou `skipped`; o
passo com `!cancelled()` rodou (`success`). Corrigido nos dois workflows
acrescentando `!cancelled()` à condição. `validate-base-images.yml` já usava
`if: always()` corretamente desde a implementação original do M11 — só
`promote-stable.yml`/`recover-stable.yml` tinham o gap.

Nenhum outro `if:` customizado sem essas funções apareceu na auditoria além
dos que **devem** mesmo continuar assim: a cadeia de gates de
`promote-stable.yml` (`Install cosign` → `Verify ... signature and
provenance` → `Install Trivy` → `Re-scan` → `Promote to stable`) usa o
mesmo `steps.candidate.outputs.skip == 'false'` de propósito — eles **devem**
parar de cascatear se um gate anterior falhar, e continuam assim.

## Aceite

- [x] Inventário completo dos required checks e do grafo `needs` nos sete
  workflows mantidos à mão.
- [x] Nenhum comentário/relatório consultivo estava no caminho obrigatório
  de merge ou publicação — não havia nada para "tirar" nesse sentido; o
  desenho já mantinha isso separado desde M11/M13.
- [x] Achado real corrigido: visibilidade consultiva de CVEs sem correção
  agora sobrevive à falha do gate que a precede em `promote-stable.yml` e
  `recover-stable.yml`, igual já acontecia em `validate-base-images.yml`.
  Confirmado empiricamente num runner real antes da correção.
- [x] `dotnet8` permanece um gate real, não reclassificado.
- [ ] Validação remota da correção em `promote-stable.yml`/`recover-stable.yml`
  especificamente (não só do mecanismo genérico via PR #43): exigiria
  provocar uma falha real de re-scan num candidato de promoção/recuperação,
  cenário que não ocorre naturalmente nos frameworks reais hoje.
