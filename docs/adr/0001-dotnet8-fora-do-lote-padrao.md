# ADR-0001 — `dotnet8` fora do lote padrão, sem sair do catálogo

| Informação | Valor |
| --- | --- |
| Estado | Proposto (Aceito com a aprovação de code owner do PR que o integra) |
| Data | 12/09/2026 |
| Owners | Containers Products (`@alric-corp/github_xj7_maintainer`) + Owner da RFC-013 |
| Revisão | `review_by` em [`policies/operations/health.json`](../../policies/operations/health.json) (`2026-10-09`); vencida, vira alerta do job de saúde |
| Aplicação | `exceptions.dotnet8` na política; três lotes de [`workflow.yml`](../../.github/workflows/workflow.yml); lint [`default_batch.py`](../../scripts/pipeline/catalog/default_batch.py) no check obrigatório |
| Origem | Roadmap consolidado da RFC-013, item "dotnet8 fora do lote padrão" (P1, Fase 1) |

## Contexto
> **Substituído em parte pelo [ADR-0007](0007-multi-source-alpine-dotnet8.md) (17/09/2026).**
> A causa desta exclusão — o Wolfi não publicar `dotnet-8-sdk` corrigido — deixou de
> valer quando `dotnet8` passou a ser construído a partir do Alpine v3.24, onde as cinco
> CVEs estão corrigidas na origem. `dotnet8` voltou ao catálogo como par `dotnet8`/
> `dotnet8-dev`, sem exceção de saúde. O texto abaixo é preservado como registro da
> decisão original e não foi reescrito.


`frameworks/dotnet8.yaml` compõe a imagem com `dotnet-8-sdk` do Wolfi. O scan
Trivy bloqueia o framework com CVEs **com correção disponível** segundo o
advisory (`8.0.129-r1`), mas o `APKINDEX` de `packages.wolfi.dev/os` publica
no máximo `dotnet-8-sdk 8.0.127-r0` — conferido em 09/09/2026 e novamente em
12/09/2026. Rebuild não resolve, porque o pacote corrigido não existe na
origem que o apko consulta. O gate está certo em bloquear: a política do
produto é zero exceções ao gate de CVE, inclusive na recuperação de emergência.

Consequências observadas enquanto `dotnet8` fica no lote automático:

- O build diário (`0 3 * * *`) e todo `validate-pr` terminam em `failure` por
  um único job previsível (`Validate dotnet8` → `Build & push dotnet8`), como
  no push `34555637518` e no diário `34574793032` de 11/09/2026 — 14/15
  frameworks aprovados e publicados, run vermelho mesmo assim. Vermelho crônico
  treina quem lê a ignorar o vermelho, o que anula o valor do alerta.
- O framework nunca produziu artifact aprovado, nunca publicou e nunca teve
  `stable`; o repositório ECR `image-base-dotnet8` existe, vazio, com
  `IMMUTABLE_WITH_EXCLUSION` aplicado por API.
- O .NET 8 encerra o suporte LTS em novembro de 2026; o catálogo já publica
  `dotnet10`/`dotnet10-dev` como trilha LTS corrente.
- O critério de saída da Fase 1 do roadmap exige build diário `success` e
  saúde sem alerta além dos históricos que expiram da janela.
- O inventário de gates do M12 registrou que
  `dotnet8` **não** seria reclassificado como consultivo para deixar o CI
  verde. Este ADR mantém isso: o scan continua gate real e continua
  bloqueando `dotnet8` sempre que ele for buildado; o que muda é o lote que o
  pipeline pede automaticamente, não a decisão do gate.

## Decisão

1. `dotnet8` **sai do lote padrão** dos três chamadores de `workflow.yml`
   (`validate-pr`, `build-base-images` — build diário e push — e
   `promote-stable`). Em `workflow_dispatch`, `build-base-images` usa o input
   manual `frameworks`, cujo default é `["go1-26"]`: um dispatch sem alterar
   o input builda `go1-26`, não o lote padrão; só um input esvaziado cai no
   lote padrão pela expressão `… && inputs.frameworks || '[…]'`.
2. `dotnet8` **permanece no catálogo** (`frameworks/dotnet8.yaml` inalterado)
   e no ECR (repositório, imutabilidade e ausência de `stable` intocados).
   `workflow_dispatch` com `["dotnet8"]` continua sendo entrada válida: é o
   mecanismo de reteste, e o gate de CVE continua bloqueando enquanto a
   correção não existir.
3. A exclusão é uma **exceção versionada** com motivo, dono, `review_by` e este
   ADR, em `policies/operations/health.json` → `exceptions`. A mesma lista já
   faz a saúde reportar o framework como `known` (não como alerta novo) e
   alertar quando `review_by` vencer. Uma única fonte: todo framework nessa
   lista está fora do lote; todo framework do catálogo fora dela está no lote.
4. Um **lint offline no check obrigatório** (`make lint-local`, job
   `lint-workflows`) reprova qualquer divergência entre os três lotes e
   `catálogo − exclusões`, nome repetido ou desconhecido, e exceção sem os
   campos obrigatórios, com `review_by` inválido ou com `adr` fora da
   [convenção](README.md) de `docs/adr/`. O lote é conferido como **literal
   canônico** — array JSON em `validate-pr` e `promote-stable`; em
   `build-base-images`, exatamente a expressão que escolhe o input do
   dispatch com o array como fallback. Qualquer outra expressão (`vars`,
   `env`, `secrets`, `inputs` sem a guarda, `fromJSON`, concatenação,
   fallback) é recusada: uma fonte externa decidiria o lote automático fora
   da política versionada.

## Consequências

- Build diário e `validate-pr` passam a refletir só falhas reais dos 16
  frameworks ativos (catálogo de 17 após as variantes `-dev` de `go1-25`
  e `java25`, menos `dotnet8`). A saúde continua listando `dotnet8` como `known`.
- Reincluir um framework exige remover a exceção **e** adicioná-lo aos três
  lotes; excluir outro exige o inverso, com motivo, dono, data e ADR. O lint
  impede fazer só metade.
- `review_by` vencido **não** reprova o lint (bloquearia todos os PRs por uma
  data); é alerta diário do job de saúde, que exige renovar a data com nova
  justificativa ou revogar a exceção.
- Um lote passado por `workflow_dispatch` não é validado contra a exclusão:
  operação manual, com o gate de CVE intacto.
- Quem consumia `image-base-dotnet8` não é afetado: nunca houve imagem
  publicada nesse repositório.

## Alternativas rejeitadas

| Alternativa | Por que não |
| --- | --- |
| Manter `dotnet8` no lote até o Wolfi corrigir | Vermelho crônico sem ação possível; contraria o critério de saída da Fase 1 e degrada o alerta |
| Remover `frameworks/dotnet8.yaml` do catálogo | Perde a definição revisada e o reteste por dispatch; a RFC-013 registra "retirar do catálogo **ou** aceitar exceção formal" — a exceção formal preserva a reversibilidade |
| Exceção no gate de CVE (permitir a CVE por prazo) | Política vigente é zero exceções ao gate; um bypass geral ou por CVE exigiria escopo, aprovador e validade próprios e não resolve a ausência do pacote corrigido |
| Trocar `dotnet-8-sdk` por `aspnet-8-runtime` (runtime-only, M07) | O scan do diário de 11/09 (`build-scans-dotnet8-1`, run `34574793032`) lista 28 achados por arquitetura em sete pacotes — `dotnet-8`, `dotnet-8-runtime`, `dotnet-8-sdk`, `aspnet-8-runtime` e os targeting packs — todos `8.0.127-r0 → 8.0.129-r1`; o `APKINDEX` publica as mesmas versões para `aspnet-8-*`. Uma variante runtime-only seria bloqueada pelos mesmos achados |
| Lista de exclusão em arquivo próprio em `policies/release/` | Duplicaria motivo/dono/data da exceção de saúde ou exigiria a saúde ler dois arquivos; a invariante "exceção de saúde ⇔ fora do lote" é mais simples e verificável |

## Critério de reinclusão (ou revogação)

Reincluir `dotnet8` quando **todas** as condições valerem:

1. `packages.wolfi.dev/os` publica `dotnet-8-sdk ≥ 8.0.129-r1` (ou o advisory
   que motivou o bloqueio deixa de apontar correção inexistente);
2. um `workflow_dispatch` de `["dotnet8"]` aprova validação (scan nas duas
   arquiteturas) no runner hospedado;
3. PR remove `exceptions.dotnet8` da política e devolve `dotnet8` aos três
   lotes (o lint exige as duas coisas), com o run acima referenciado.

Revogar em vez de reincluir — retirando `dotnet8` do catálogo em ADR próprio —
se o fim do suporte LTS (novembro de 2026) chegar antes da correção, ou se o
Owner da RFC decidir que a trilha .NET 8 não entra em produção.

## Evidência

Spec, aceite e evidência local em
[`specs/2026-09-12-dotnet8-fora-do-lote-padrao/`](../../specs/2026-09-12-dotnet8-fora-do-lote-padrao/spec.md).
O aceite hospedado (primeiro build diário `success` após o merge e saúde
subsequente) fica registrado ali como NOT RUN até acontecer.
