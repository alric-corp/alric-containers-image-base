# M11/M04: resultado visível, saúde operacional e política de alerta

Duas coisas diferentes, que costumam ser confundidas: **o resultado de um
run** (o que aconteceu com cada framework naquele run) e **a saúde do
pipeline ao longo do tempo** (está atualizando? o agendamento está
acontecendo?). Cada uma tem seu próprio lugar e seu próprio dono.

## 1. Resultado por framework, no run

[`pipeline_summary.py`](../scripts/pipeline/operations/pipeline_summary.py) lê as
evidências que os jobs já preservam como artifacts e escreve uma tabela no
`GITHUB_STEP_SUMMARY` — no build (`build-base-images.yml`) e na promoção
(`promote-stable.yml`). Colunas: framework, digest do índice, arquiteturas,
resultado do scan, CVEs sem correção, contrato funcional, publicação,
promoção, motivo e links diretos para os artifacts de evidência.

Três distinções que a tabela mantém separadas porque exigem ações
diferentes:

| Estado | Significa | O que fazer |
| --- | --- | --- |
| `bloqueado` | Trivy saiu com 1: há achado **com correção disponível** | atualizar o pacote (rebuild resolve) |
| `CVEs sem correção` | contagem informativa, coletada sem `--ignore-unfixed` | acompanhar; o gate não bloqueia e rebuild não resolve |
| `erro de infraestrutura` | scanner não concluiu (saída diferente de 0/1, erro, evidência ausente) | **não é resultado de segurança** e não pode ser lido como aprovação |

Um framework sem nenhuma evidência aparece como linha explícita (`sem
evidência`), nunca omitido: um job que morreu antes de subir o artifact não
pode desaparecer da tabela. E um framework cujo contrato funcional não roda
neste lote aparece como `não executado` **com o motivo**, decidido pelo mesmo
código versionado que monta a matriz de contratos
([`runtime_images.plan`](../scripts/pipeline/runtime/runtime_images.py)).

## 2. Saúde do pipeline, ao longo do tempo

[`operational_health.py`](../scripts/pipeline/operations/operational_health.py) roda em
[`pipeline-health.yml`](../.github/workflows/pipeline-health.yml) (diário,
05:40 UTC, e `workflow_dispatch`) e mede, com dados reais da API:

- **idade do ponteiro `stable` por framework** — quando ele foi movido pela
  última vez. Vem do passo `Promote to stable` do job de promoção, que
  distingue "promoveu" de "rodou e pulou por não ter candidato". Não é a
  idade da imagem por trás do ponteiro (essa é mais antiga: passou pelo
  soak); o `imagePushedAt` exato está na evidência de promoção, que o
  próprio gate grava a cada ciclo.
- **última publicação bem-sucedida por framework** — pelo job de publicação
  daquele framework, não pela conclusão agregada do run (que fica vermelha
  por causa de um framework e não diz nada sobre os outros).
- **execução esperada x real do cron**, por cron, com o atraso de disparo.
- **atraso de fila** (`created_at` → `run_started_at`): espera por runner,
  não duração de job.

O mesmo workflow executa `pin_inventory check`: além dos pins de ferramentas,
compara a signing key Wolfi remota com o pin local. Divergência e endpoint
indisponível falham health após preservar evidência; não atualizam a chave e
não são dependência dos builds. Donos/canal permanecem os da policy existente.
Consulte [rotação e limite de auto-discovery](wolfi-signing-key.md).

### Como cada run agendado é atribuído ao seu cron

A API do GitHub **não expõe** `github.event.schedule` num run. Adivinhar pelo
horário não funciona: na conta real, um disparo do cron diário das 03:00
chegou às 07:36. A atribuição sai de **qual job rodou**: `build-base-images`
só roda no cron diário e `promote-stable` só no horário — o outro aparece
`skipped`. O mapa cron → job está declarado em
[`policies/operations/health.json`](../policies/operations/health.json) e um lint
offline (no check obrigatório) exige que política e workflow declarem os
mesmos crons.

### A cadência nominal do cron não é a cadência real

Medido em 09/09/2026 na conta real, na janela desde a criação do workflow:

| Cron | Ocorrências esperadas | Runs | Cobertura | Atraso p90 | Maior intervalo |
| --- | --- | --- | --- | --- | --- |
| `0 3 * * *` (build diário) | 2 | 2 | 100% | 5788s (~1h36) | 24,1h |
| `17 * * * *` (promoção horária) | 49 | 5 | **10,2%** | 1636s (~27min) | 24,1h |

O agendador do GitHub entrega runs agendados em regime de melhor esforço:
**a promoção "horária" aconteceu 5 vezes em 49 oportunidades**, e o build
diário chegou com mais de uma hora e meia de atraso no p90. Qualquer
afirmação de SLA baseada na cadência nominal do cron (ex.: "promoção em até
1h") é falsa neste ambiente. Por isso o alerta usa **lacuna sem run**
(`gap_alert_hours` por cron), não contagem de ocorrências perdidas: um alerta
que dispara todo dia por um comportamento estrutural da plataforma treina
quem lê a ignorá-lo.

### Limites e por que estes números

Todos em [`policies/operations/health.json`](../policies/operations/health.json),
sob revisão de code owner. Nenhum é SLA prometido a consumidor — são limites
internos de alerta, derivados da cadência observada:

| Limite | Valor | Origem |
| --- | --- | --- |
| `publication_age_hours` | 30 | 24h do build diário + 6h de margem: alerta = dois ciclos seguidos sem publicar aquele framework |
| `stable_age_hours` | 48 | 24h + soak de 6h + margem para a promoção real |
| `gap_alert_hours` (diário) | 30 | um ciclo perdido, contando o atraso observado |
| `gap_alert_hours` (horário) | 12 | metade do maior intervalo observado (24,1h): pega a parada, não a irregularidade normal |
| `queue_delay_p90_seconds` | 900 | espera por runner observada hoje é ~0s; 15min é degradação clara |
| `update_pr_stale_days` | 7 | uma semana é o ciclo do Renovate/Dependabot |

### `unknown` não é aprovação, e `known` não é alerta novo

Primeiro run hospedado em 10/09/2026: [34493238551](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34493238551).
Detectou o digest indisponível do Skopeo, uma lacuna histórica de 24,08h na
promoção e truncamento após consultar 90 runs. O ajuste desta entrega filtra
PRs/branches sem autorização de publicação e sobe o teto para 300. Contra os
mesmos 92 runs reais, bastaram 53 consultas, sem truncamento; o alerta de
agendamento permaneceu. A configuração nova ainda precisa entrar na `main`.

- `alert` — limite rompido; o job falha.
- `known` — exceção documentada em `exceptions`, com **motivo, dono, data de
  revisão e ADR obrigatórios**. Hoje só `dotnet8` (ver abaixo). Não falha o job.
  **Uma exceção com `review_by` vencida gera alerta própria**: a exceção
  também não pode apodrecer em silêncio. Desde o
  [ADR-0001](adr/0001-dotnet8-fora-do-lote-padrao.md), toda exceção está
  também **fora do lote padrão** de `workflow.yml`; o lint
  [`default_batch.py`](../scripts/pipeline/catalog/default_batch.py), no check
  obrigatório, impede que a lista e os três lotes divirjam.
- `unknown` — a medida não teve dado porque a busca de jobs foi truncada pelo
  limite de chamadas. Não é falha comprovada nem aprovação; o truncamento em
  si vira alerta, porque a resposta é medir melhor.

#### A exceção conhecida do `dotnet8`, conferida na origem

O scan bloqueia com 28 achados por arquitetura em `dotnet-8-*`, todos
apontando correção em `8.0.129-r1`. O APKINDEX real de
`packages.wolfi.dev/os` (conferido em 09/09/2026) publica no máximo
`dotnet-8-sdk 8.0.127-r0` — **a versão corrigida não existe no repositório
que o apko consulta** (reconferido em 12/09/2026). Rebuild não resolve: depende
de a Wolfi publicar o pacote, ou de retirar `dotnet8` do catálogo. Registrado
como exceção com dono e revisão em 09/10/2026, não como "falha crônica que a
gente ignora". Em 12/09/2026 o framework saiu do lote padrão
([ADR-0001](adr/0001-dotnet8-fora-do-lote-padrao.md)): continua no catálogo e
nesta tabela como `known`, deixa de pintar o build diário de vermelho, e o
critério de reinclusão está no ADR.

## 3. Canal, dono e notificação

| Item | Estado |
| --- | --- |
| Dono | `@alric-corp/github_xj7_maintainer` (POC), escalonamento `@vigcf` |
| Canal implementado | **falha do job `pipeline-health.yml` + tabela no resumo do run** |
| Destino externo | **não definido** (`channel.external_destination: null`) |

A RFC pede, explicitamente, implementar notificação **somente depois** de
definir destino e política. Então o canal de hoje é o que o GitHub já
entrega sem nenhum segredo novo nem integração: o job falha, e quem acompanha
o repositório recebe a notificação nativa de workflow com falha. Isso cobre
inclusive o caso difícil — o cron que **não** gera run —, porque o job de
saúde tem agendamento próprio e mede a ausência do outro.

Para ligar um destino externo (canal corporativo, e-mail de plantão), a ordem
é: preencher `channel.external_destination` e o dono na política, combinar
quem recebe e em que nível (`alert` só, ou também `known`), e só então
implementar o envio. O ponto de integração é o passo final de
`pipeline-health.yml`, que já tem os alertas classificados em
`reports/operational-health.json`.

## 4. Retenção de evidências, alinhada ao uso

A finalidade de cada prazo está em `retention_days`, e um lint offline no
check obrigatório compara o declarado com o `retention-days` real de cada
`upload-artifact`. Política que diverge do workflow não protege prazo nenhum.

| Artifact | Prazo | Finalidade |
| --- | --- | --- |
| `melange-repo` | 1 dia | insumo intermediário, reconstruído em minutos |
| `validated-oci-*` | 3 dias | janela de retry da publicação sem revalidar |
| `build-scans-*`, `publication-*` | 30 dias | auditoria do que foi escaneado e publicado |
| `runtime-*` | 30 dias | evidência do contrato funcional que autorizou publicar |
| `promotion-*`, `promotion-scans-*` | 30 dias | por que promoveu ou não, e o re-scan do soak |
| `recovery-*` | 30 dias | runbook de recuperação do M15 |
| `pipeline-summary-*`, `pipeline-health-*` | 30 dias | resultado e saúde, para comparar no tempo |

No [retry parcial P1-02](../specs/2026-09-13-partial-retry-without-rebuild/spec.md),
o contrato de attempt anterior só é reutilizado no mesmo run, para o OCI
validado atual e seu par compilado. A janela efetiva continua limitada pelo
OCI de 3 dias; manter reports por 30 dias não prolonga essa janela nem
autoriza rebuild automático no publicador. Metadados incompletos, histórico
malformado ou producer mais recente falho bloqueiam o reuso.

**`retention-days` não é backup** (achado do R03): uma reexecução completa
produz digests novos e não recupera artifact vencido. A recuperação de
`stable` por digest (M15) depende do ECR, não destes artifacts — o prazo aqui
cobre auditoria e diagnóstico, não recuperação de imagem.

A [lifecycle ECR](../policies/operations/ecr-lifecycle.json) foi aplicada e
relida nos 15 repositórios do sandbox em 10/09/2026. Seleciona somente imagens
sem tag após 30 dias; os previews selecionaram zero imagens. Releases e
assinaturas com tag ficam preservadas. [Evidência](evidence/ecr-lifecycle-2026-09-10.json).
