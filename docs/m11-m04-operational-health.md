# M11/M04 / P1-08: contrato operacional, alertas e proposta de SLO/SLA

Revisão documental de 13/09/2026 sobre main
`d60be51de7d1480b40fb333b0d1afc6d7b0d1158` (PR #58 integrado).
Este é o documento canônico de operação. A premissa de autoria/sustentação
dos workflows federados permanece no [ADR-0003](adr/0003-controles-seguranca-workflows-federados.md).
Não estabelece SLA, atendimento 24x7, plantão nomeado ou autorização de serviços.

| Dimensão | Estado desta fatia |
| --- | --- |
| Documentação operacional | PROPOSED para revisão independente |
| Health, pins, resumos e timing | IMPLEMENTED, com os limites abaixo |
| Operação exercitada | OBSERVED_IN_EVIDENCE somente nos runs e períodos registrados |
| Envio externo pela fábrica | NOT IMPLEMENTED; `external_destination` continua null |
| Entrega de notificações e reconhecimento | NOT VERIFIED / NOT_MEASURED |
| Canal, responsáveis e acordo corporativos | EXTERNAL_PENDING |

IMPLEMENTED descreve código; OBSERVED_IN_EVIDENCE requer observação datada;
NOT_MEASURED indica dado ausente; PROPOSED não é meta aprovada; EXTERNAL_PENDING
exige decisão dos responsáveis. Aprovar este texto não encerra o P1-08 completo.

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

A promoção preserva os diretórios por framework dentro de dois bundles:
`promotion-batch-<attempt>` (outcomes e snapshots ECR anteriores) e
`promotion-scans-batch-<attempt>` (scans e versões das ferramentas), por 30
dias. O download com merge mantém esses diretórios para os consumidores;
os links do resumo apontam para o bundle da tentativa correspondente.
O documento `promotion-batch.json` mantém `unit_results` com frameworks,
status (`PENDING`, `AUTHORIZED`, `FAILED` ou `SKIPPED`), fase,
`prewrite_authorized`, `promoted` e erros. `AUTHORIZED` só indica promoção
concluída quando acompanhado de `promoted=true` e das confirmações por
framework. `prewrite_barrier_complete` registra o término da avaliação de
todas as unidades antes das escritas. Falha de uma unidade mantém os
indicadores agregados false; não apaga o outcome de outra unidade confirmada.

Três distinções que a tabela mantém separadas porque exigem ações
diferentes:

| Estado | Significa | O que fazer |
| --- | --- | --- |
| `bloqueado` | Trivy saiu com 1: há CVE com versão corrigida indicada e/ou secret | conferir relatório por arquitetura e disponibilidade da correção na origem; advisory não prova pacote disponível |
| `CVEs sem correção` | contagem informativa, coletada sem `--ignore-unfixed` | acompanhar; o gate não bloqueia e rebuild não resolve |
| `erro de infraestrutura` | scanner não concluiu (saída diferente de 0/1, erro, evidência ausente) | **não é resultado de segurança** e não pode ser lido como aprovação |

Um framework sem nenhuma evidência aparece como linha explícita (`sem
evidência`), nunca omitido: um job que morreu antes de subir o artifact não
pode desaparecer da tabela. E um framework cujo contrato funcional não roda
neste lote aparece como `não executado` **com o motivo**, decidido pelo mesmo
código versionado que monta a matriz de contratos
([`runtime_images.plan`](../scripts/pipeline/runtime/runtime_images.py)).

O resumo é uma visão de artifacts, não um novo verificador. A coluna
`publicado` reconhece `publication-evidence.json`, produzido na cópia/verificação
de digest **antes** de assinatura/attestations; não prova finalização da release.
O resumo não aplica o binding de retry do publicador e sua escolha entre
artifacts usa ordenação lexical. Consultar o job completo, o artifact exato
e o [contrato de consumo](consumer-verification-contract.md) para afirmar que
uma release é utilizável. A coluna scan usa `build-scans`, não comprova o
re-scan a partir de `promotion-scans`. Ausência de artifact pode ser falha,
não execução ou expiração; nenhuma delas é PASS.

## 2. Saúde do pipeline, ao longo do tempo

[`operational_health.py`](../scripts/pipeline/operations/operational_health.py) roda em
[`pipeline-health.yml`](../.github/workflows/pipeline-health.yml) (diário,
05:40 UTC, e `workflow_dispatch`, somente main). Consulta APIs GitHub com
`contents: read` / `actions: read`, sem AWS. Não consulta o ECR. Mede:

- **proxy de movimentação de `stable` por framework** — no fluxo atual,
  `stable_age_hours` lê o artifact `promotion-batch-<attempt>` da tentativa
  exata do job `Authorize and promote stable candidates`, concluído com
  sucesso ou falha. Cada unidade exige autorização prévia, trust, scan,
  escrita concluída, `promoted=true`, read-back `confirmed` e digest observado
  igual ao candidato. Um par compilado exige ambos os membros e binding
  coerente; um framework interpretado é uma unidade individual. Uma unidade
  confirmada continua válida quando uma unidade independente falha:
  a conclusão agregada não apaga o sucesso individual nem aprova o lote
  inteiro. Skip, escrita parcial ou read-back falho não renovam a idade da
  unidade afetada. Usa `completed_at` do job, sem consultar o ECR atual. Para
  runs históricos, preserva o proxy anterior: passo `Promote to stable`
  bem-sucedido em `Promote <framework>`, sem garantia de read-back final.
- **última publicação bem-sucedida por framework** — pelo job de publicação
  daquele framework, não pela conclusão agregada do run (que fica vermelha
  por causa de um framework e não diz nada sobre os outros).
- **execução esperada x real do cron**, por cron, com o atraso de disparo.
- **intervalo entre criação e início do run** (`created_at` → `run_started_at`),
  exibido como fila; não isola toda espera por runner nem dependências de jobs.

O coletor considera runs cujo path é um dos arquivos declarados em
`policies/operations/health.json` → `schedules` (hoje `workflow.yml`,
`promote-stable.yml` e `pipeline-health.yml`). Publicação e promoção usam
eventos push/schedule/dispatch da main; desde a separação build/promoção,
um dispatch manual de `promote-stable.yml` que promova de fato também entra
nessa série — o que não acontecia quando só `workflow.yml` era considerado.
`recover-stable.yml` não tem schedule próprio e continua fora dela. Ordena
runs por `created_at` decrescente e retém o primeiro job qualificante
encontrado; não ordena globalmente todas as conclusões de jobs entre
attempts/runs.

A janela pedida é 7 dias, encurtada se o workflow foi criado depois. Busca
até seis páginas de 100 runs do repositório antes do filtro de path; jobs
são lidos em uma página de até 100 por run. O workflow passa
`--max-job-queries 300` (CLI isolada: default 40) à busca por framework.
`truncated` sinaliza esse orçamento, **não** completude da listagem de runs
ou jobs. A atribuição de schedules também consulta jobs. Erro HTTP/JSON em
`gh_json` vira ausência de dados; não há marcador completo para distinguir
erro de API de falta real de histórico. Conferir cobertura antes de interpretar
“nenhum alerta”. Esses limites não foram alterados nesta entrega.

Para os novos jobs de promoção, o coletor lê adicionalmente o inventário de
artifacts do run e exige listagem completa (até 100), um único bundle não
expirado da tentativa exata e JSON por framework. Download somente leitura
com `actions: read`, sem novo IAM, limitado a 8 MiB/120s; cada documento tem
limite de 1 MiB. O ZIP é lido como dados, nunca extraído ou executado. Scans
grandes ficam no bundle separado e não são baixados pelo health. Evidência
ausente, inválida, ambígua ou expirada aparece em `promotion_evidence_gaps`
e alerta `unknown`; não atualiza a idade e não autoriza uma release. Uma
promoção mais antiga confirmada continua visível com sua idade original.

O mesmo workflow executa [`pin_inventory check`](../scripts/pipeline/governance/pin_inventory.py): além dos pins de ferramentas,
compara a signing key Wolfi remota com o pin local. Divergência e endpoint
indisponível falham health após preservar evidência; não atualizam a chave e
não são dependência dos builds. Donos/canal permanecem os da policy existente.
Consulte [rotação e limite de auto-discovery](wolfi-signing-key.md).

Pins e métricas usam `continue-on-error` para preservar o outro relatório;
o passo final exige outcome success dos dois. O upload
`pipeline-health-<attempt>` preserva `reports/` por 30 dias com
`if-no-files-found: warn`, condicionado a `!cancelled()`. Falha precoce,
cancelamento ou upload com warning pode deixar evidence incompleta.

### Como cada run agendado é atribuído ao seu cron

A atribuição implementada sai de **qual grupo de jobs não ficou skipped**,
não de adivinhar pelo horário de criação. Desde a separação build/promoção,
cada cron agendado vive no seu próprio arquivo (`23 3 * * *` em
`workflow.yml`, `17 * * * *` em `promote-stable.yml`, `40 5 * * *` em
`pipeline-health.yml`), então hoje nenhum arquivo tem dois crons competindo
pelo mesmo run — o mecanismo de "job não-skipped" continua existindo porque
generaliza para esse caso sem exigir outra reescrita se algum dia voltar a
acontecer. O mapa cron → arquivo → job está declarado em
[`policies/operations/health.json`](../policies/operations/health.json) e um
lint offline (no check obrigatório) exige que a política declare exatamente
os crons agendados em `.github/workflows/*.yml`, cada um apontando para o
arquivo que de fato o agenda.

Sem grupo único, o run fica `unattributed_scheduled_runs`; não se inventa
um cron. Para cobertura/atraso, o código associa cada criação ao slot nominal
anterior mais próximo. É uma aproximação: não comprova qual slot gerou um
run muito atrasado. A lacuna usa `created_at`, não conclusão ou publicação.

O build diário ocorre nominalmente às 03:23 UTC, aproximadamente 00:23 em
America/Sao_Paulo. O cron permanece UTC. O minuto 23 evita a concentração de
disparos no início da hora; não transforma o scheduler em garantia de prazo.
`gap_alert_hours` permanece 30 para build/health e 12 para promoção.

O health compartilha o **mesmo scheduler GitHub** que observa e não mede seu
próprio cron de 05:40. Uma indisponibilidade compartilhada pode impedir a
detecção tempestiva. Não existe monitoramento independente. Também não se
deduz que 05:40 observou um ciclo completo: são 2h17 após o build nominal
de 03:23, e o soak padrão é 6h. Os horários são configuração, não prazo.
O GitHub documenta possibilidade de atrasos e descarte sob carga em
[schedule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

O caller candidato usa `factory-build-publish-${github.repository}` e
`cancel-in-progress: false` até concluir build, contratos, publicação,
assinatura e attestations. PRs de validação não compartilham esse lock.
O [modelo de concorrência GitHub](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
mantém por padrão somente um pendente, substituível por disparo posterior;
o run ativo permanece. Não é promessa de executar cada trigger nem de ordem
por dispatch. Ao analisar tempo com `ci_timing`, marque os jobs conhecidos
como serializados: espera pelo lock não é exclusivamente fila de runner.

Após o merge autorizado e o término do golden path congelado, a promoção
deve permanecer ACTIVE, governada por `STABLE_PROMOTION_AUTHORIZED`. Este PR
não reativa o workflow nem muda o valor false. Promoção e recuperação usam
o mesmo lock `stable-mutation-<role>-<region>` e não cancelam o escritor ativo.
Esse lock permanece inalterado: prioriza consistência das tags sobre a
latência de recuperação de emergência. Recovery pode esperar atrás do lote
de promoção ativo. O timeout de 60 minutos do job de promoção é um limite
superior configurado de execução, não a espera esperada da recuperação nem
garantia do tempo total em fila. Em emergência, inspecione o run ativo e sua
evidência antes de decidir a ação operacional; não contorne o lock.
Autorização do par e segurança de ambos vêm antes de qualquer tag write;
as duas escritas ECR continuam sem atomicidade distribuída. Falha parcial
mantém o par não promovido, evidencia o estado anterior e exige triagem pelo
runbook de recuperação antes de declarar o par coerente.

### Snapshot histórico: a cadência nominal não é a cadência real

Snapshot registrado em 09/09/2026, na janela então descrita como “desde a
criação do workflow”. Números preservados; esta tabela não contém limites
UTC completos ou dataset bruto suficiente para reapurá-los. Não é medição
atual, inventário completo ou base suficiente para compromisso estatístico:

| Cron | Ocorrências esperadas | Runs | Cobertura | Atraso p90 | Maior intervalo |
| --- | --- | --- | --- | --- | --- |
| `0 3 * * *` (build diário) | 2 | 2 | 100% | 5788s (~1h36) | 24,1h |
| `17 * * * *` (promoção horária) | 49 | 5 | **10,2%** | 1636s (~27min) | 24,1h |

Naquele snapshot, o agendador entregou runs com irregularidade:
**a promoção "horária" aconteceu 5 vezes em 49 oportunidades**, e o build
diário chegou com mais de uma hora e meia de atraso no p90. Qualquer
afirmação de SLA baseada na cadência nominal do cron (ex.: "promoção em até
1h") é falsa neste ambiente. Por isso o alerta usa **lacuna sem run**
(`gap_alert_hours` por cron), não contagem de ocorrências perdidas: um alerta
que dispara todo dia por um comportamento estrutural da plataforma treina
quem lê a ignorá-lo.

### Limites declarados versus condições efetivamente avaliadas

Todos em [`policies/operations/health.json`](../policies/operations/health.json),
sob revisão de code owner. Nenhum é SLA prometido a consumidor — são limites
internos de diagnóstico/alerta. A interpretação executável prevalece sobre
comentários da policy; ela permanece inalterada:

| Limite | Valor | Uso atual |
| --- | --- | --- |
| `publication_age_hours` | 30 | Alerta se idade do job de publicação >30h, ou falta dado; 24h+6h é margem declarada, não prova “dois ciclos perdidos” |
| `stable_age_hours` | 48 | Alerta se proxy de movimentação >48h, ou falta dado; não lê estado atual do registry |
| `gap_alert_hours` (diário) | 30 | Alerta se sem run, última criação >30h ou maior lacuna interna >30h |
| `gap_alert_hours` (horário) | 12 | Mesma regra, com 12h; lacuna histórica continua alertando enquanto estiver na janela |
| `queue_delay_p90_seconds` | 900 | Declarado, mas **não usado por evaluate para gerar alerta**; fila é exibida |
| `update_pr_stale_days` | 7 | Declarado, mas não lido pelo check de pins; CLI usa seu próprio default `--stale-days 7`; PR stale é informativa, não torna o check falho |

O inventário checa disponibilidade de pins e reporta PRs abertas de autores
cujo login contém renovate/dependabot. Consulta limitada a 100 PRs; idade
calculada desde `created_at`, sem medir revisão ou última atividade. Erro
nessa consulta vira lista vazia: ausência não prova automação ativa nem
inexistência de PRs fora do recorte. Somente resultados de pin com
`available=false` tornam o check falho.

### `unknown` não é aprovação, e `known` não é alerta novo

Primeiro run hospedado em 10/09/2026: [34493238551](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34493238551).
Detectou o digest indisponível do Skopeo, uma lacuna histórica de 24,08h na
promoção e truncamento após consultar 90 runs. O ajuste daquela entrega filtra
PRs/branches sem autorização de publicação e sobe o teto para 300. Contra os
mesmos 92 runs reais, bastaram 53 consultas, sem truncamento; o alerta de
agendamento permaneceu. Naquele momento a configuração ainda precisava
entrar na main; na baseline desta revisão, filtro e teto 300 já estão presentes.

- `alert` — limite rompido; o job falha.
- `known` — exceção documentada em `exceptions`, com **motivo, dono, data de
  revisão e ADR obrigatórios**. Hoje nenhuma (ver exemplo histórico abaixo).
  Não falha o job.
  **Uma exceção com `review_by` vencida gera alerta própria**: a exceção
  também não pode apodrecer em silêncio. Toda exceção em `exceptions` está
  também **fora do lote padrão** de `workflow.yml`; o lint
  [`default_batch.py`](../scripts/pipeline/catalog/default_batch.py), no check
  obrigatório, impede que a lista e os três lotes divirjam.
- `unknown` — a medida não teve dado porque a busca de jobs foi truncada pelo
  limite de chamadas. Não é falha comprovada nem aprovação; o truncamento em
  si vira alerta, porque a resposta é medir melhor.

`review_by` é comparado a meia-noite UTC da data declarada: vencido quando
`review_byT00:00:00Z < generated_at`, inclusive durante o próprio dia de
revisão. O alerta de vencimento é separado; não transforma os registros
`known` da exceção em saúde comprovada. O lint verifica campos/ADR/data,
mas não falha por vencimento; essa detecção pertence ao health.

#### Exemplo histórico: a exceção do `dotnet8` (12/09/2026 – 17/09/2026)

O scan bloqueava com 28 achados por arquitetura em `dotnet-8-*`, todos
apontando correção em `8.0.129-r1`. O APKINDEX real de
`packages.wolfi.dev/os` (conferido em 09/09/2026) publicava no máximo
`dotnet-8-sdk 8.0.127-r0` — **a versão corrigida nunca existiu no repositório
que o apko consulta** (reconferido em 12/09/2026). Rebuild não resolvia:
dependia de a Wolfi publicar o pacote, ou de retirar `dotnet8` do catálogo.
Registrado como exceção com dono e revisão em 09/10/2026, não como "falha
crônica que a gente ignora". Em 12/09/2026 o framework saiu do lote padrão,
continuando no catálogo e nesta tabela como `known`. Em 17/09/2026, com o
suporte LTS do .NET 8 a terminar em novembro e sem correção do Wolfi à
vista, `dotnet8` foi removido do catálogo; não há mais nenhuma exceção
`known` registrada. `dotnet10`/`dotnet10-dev` seguem no caminho suportado.
Este exemplo permanece para ilustrar como o mecanismo `known` funciona
quando alguma exceção futura for registrada; a decisão original está
consolidada na [RFC-013](../RFC-013-Image-Base-Completa-com-Mermaid.md) e em
[Corporate Production Readiness](corporate-production-readiness.md).

## 3. Canal, dono e notificação

| Item | Estado |
| --- | --- |
| Dono | `@alric-corp/github_xj7_maintainer` (POC), escalonamento `@vigcf` |
| Canal implementado | **falha do job `pipeline-health.yml` + tabela no resumo do run** |
| Destino externo | **não definido** (`channel.external_destination: null`) |

Essas identidades são configurações da POC, não nomeações corporativas ou
plantão. O código não usa owner/escalation/channel para encaminhar mensagens.
Preencher um campo não implementaria envio, confirmação ou escalonamento.

| Etapa | Implementação / prova necessária | Estado atual |
| --- | --- | --- |
| Problema detectado | Pins/health classificam resultados, annotations e saída; conferir JSON e outcome real | IMPLEMENTED; OBSERVED_IN_EVIDENCE na amostra P1-08 |
| Relatório produzido | JSON em reports, resumo no run e upload de artifact quando possível | IMPLEMENTED; upload e conteúdo observados, sem prova de leitura humana |
| Notificação enviada | Notificações nativas dependem de configuração GitHub; nenhum emissor externo da fábrica | Nativo NOT VERIFIED; externo NOT IMPLEMENTED |
| Entrega confirmada | Registro do destino associando mensagem ao alerta/run, com horário | NOT VERIFIED; dado não produzido pelo health |
| Atendimento reconhecido | Responsável identifica recebimento e assume triagem, com horário | NOT_MEASURED; nenhum ACK/escalonamento automático implementado |

Falha de job não prova notificação; resumo não prova leitura; tentativa de
envio não prova entrega; entrega não prova reconhecimento. O GitHub permite
configurar notificações de runs e possui regras próprias para schedules;
seguir um repositório não comprova que estes owners receberam um alerta.
Ver [notificações de workflow](https://docs.github.com/en/actions/concepts/workflows-and-actions/notifications-for-workflow-runs).

**Plano futuro, não executado:** Containers Products e responsáveis externos
definem canal aprovado, destinatários, classificação/retenção, quais estados
enviar, janela de atendimento e escalonamento. Depois, em fatia autorizada,
implementar a integração e testar com mensagem controlada identificada como
teste, sem causar falha operacional. Registrar identificador do alerta/run,
horário da detecção, tentativa, comprovante de entrega no destino e ACK do
responsável; validar também falha de envio e encaminhamento. Até haver esses
registros, taxa de entrega e tempo de reconhecimento são NOT_MEASURED, sem
SLO numérico. O destino segue null nesta entrega.

## 4. Retenção de evidências, alinhada ao uso

A finalidade de cada prazo está em `retention_days`, e um lint offline no
check obrigatório compara o declarado com o `retention-days` real de cada
`upload-artifact` **deste repositório**. Política que diverge do workflow não
protege prazo nenhum. Os artifacts que o executor compartilhado sobe
(`melange-repo`, `build-scans-*`, `sbom-*`, `runtime-*`, `validated-oci-*`) têm
sua retenção declarada e testada em `alric-containers-reusable-workflows`, não
por este `retention_days` nem por este lint.

| Artifact | Prazo | Finalidade |
| --- | --- | --- |
| `melange-repo`, locks e `sbom-*` (executor compartilhado) | 30 dias | insumos/evidências para auditoria e replay, sujeitos à disponibilidade upstream |
| `validated-oci-*` (executor compartilhado) | 3 dias | janela de retry da publicação sem revalidar |
| `build-scans-*` (executor compartilhado) | 30 dias | auditoria do que foi escaneado |
| `runtime-*` (executor compartilhado) | 30 dias | evidência do contrato funcional que autorizou publicar |
| `publication-*` | 30 dias | auditoria do que foi publicado |
| `promotion-*`, `promotion-scans-*` | 30 dias | por que promoveu ou não, e o re-scan do soak |
| `recovery-*` | 30 dias | runbook de recuperação do M15 |
| `pipeline-summary-*`, `pipeline-health-*` | 30 dias | resultado e saúde, para comparar no tempo |
| `image-trust-*` | 30 dias | evidência da integração de confiança de certificados |
| `infra-apply-plan-*` | 1 dia | plano binário aprovado, consumido somente pelo mesmo run/revisão |
| `infra-apply-evidence-*`, `infra-pr-plan-*` | 5 dias | evidências de apply e plano somente leitura do PR |

No retry parcial (P1-02), o contrato de attempt anterior só é reutilizado no
mesmo run, para o OCI
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
assinaturas com tag ficam preservadas.

## 5. Indicadores e semântica do tempo

SLI é medição objetiva com escopo conhecido. SLO é uma meta operacional,
identificada como proposta ou aprovada. SLA é um compromisso acordado com
consumidores e responsáveis; não nasce da configuração ou deste documento.

Os indicadores abaixo distinguem o que o health já calcula do que exige
apuração adicional. Para I01–I04, a janela padrão é a efetiva do JSON de health,
até 7 dias; usar `generated_at` como referência, não a hora em que o relatório
foi baixado.

| ID / pergunta | Fonte e cálculo | Unidade / escopo | Ausência, limite e estado |
| --- | --- | --- | --- |
| I01 — Há lacuna de execução? | `schedules`: `generated_at − último created_at` e máximo entre criações consecutivas atribuídas ao cron | Horas, por cron na janela | Sem run gera alerta; falta de dados não é zero. Não mede sucesso, intervalo anterior ao primeiro run nem cadência do próprio health. IMPLEMENTED / observado em reports |
| I02 — Há evidência recente de publicação por framework? | `frameworks`: `generated_at − completed_at` do primeiro job de publicação success encontrado na busca | Horas, cada um dos 17 frameworks; reportar à parte os 16 ativos e a exceção | Sem dado = desconhecido quanto ao registry, alerta/known/unknown conforme avaliação. É proxy de job, não consulta de release verificável agora. IMPLEMENTED / observado em reports |
| I03 — Há evidência recente de escrita de stable? | `frameworks.stable_age_hours`: `generated_at − completed_at` do job com passo de escrita success | Horas por framework na janela | Não exige read-back e exclui recovery/dispatch direto. Não comprova digest atual, frescor do conteúdo ou promoção confirmada. IMPLEMENTED / observado como proxy |
| I04 — Exceções precisam de decisão? | Policy `exceptions` e `review_by`; contar datas cuja meia-noite UTC é anterior a `generated_at` e datas ausentes | Quantidade e lista por framework em cada avaliação | `known` não elimina a pendência. Campos inválidos são falha de policy, não zero; vencimento gera alerta separado. IMPLEMENTED / observação limitada à exceção existente |
| I05 — Quanto levou da elegibilidade à promoção confirmada? | PROPOSED: por índice, `t_confirmado − t_elegível`; início exige push ECR + soak efetivo e demais pré-condições, fim exige evidence read-back/digests e timestamp da etapa | Horas por framework/digest; janela de acompanhamento META A DEFINIR | NOT_MEASURED como série. `evaluated_at` da seleção não é primeira elegibilidade; falta de timestamp ou candidato não vira duração zero. Não usar idade do antigo stable como início |
| I06 — Quantos frameworks ativos estão sem release utilizável? | PROPOSED: inventariar os 16 ativos por instante; separar com release verificada, sem release e sem dados, vinculando índice, assinatura/provenance e requisitos de consumo | Contagem por framework e agregado; instante de leitura e período META A DEFINIR | NOT_MEASURED nesta entrega; requer consulta/autenticação do registry e verificação. Ausência no health não prova ausência no ECR; exceção é estrato explícito, não sucesso |

Estado/idade do **conteúdo** apontado por stable é outra observação: o seletor
em [find_promotion_candidate.py](../scripts/pipeline/release/find_promotion_candidate.py)
registra `stable_digest`, `stable_pushed_at` e `stable_age_hours` a partir do
`imagePushedAt` da imagem que tinha a tag **antes da escrita**, no instante
`evaluated_at`. Esses campos não são atualizados pelo read-back para representar
o novo conteúdo. O nome `stable_age_hours` nos dois reports tem semânticas
diferentes; não juntar as séries apenas pelo nome.

| Timestamp | Semântica e uso permitido |
| --- | --- |
| OCI config `created` | Data de composição controlada pelo build/data do commit; não é publicação ou promoção |
| ECR `imagePushedAt` | Data de push do objeto de imagem consultado, conforme [API ImageDetail](https://docs.aws.amazon.com/AmazonECR/latest/APIReference/API_ImageDetail.html); não é relógio de movimentação da tag |
| Seletor `evaluated_at` | Instante em que aquela seleção avaliou o inventário; não primeira elegibilidade |
| Job `completed_at` | Conclusão de job; é o timestamp usado nos proxies I02/I03, não o instante exato de escrita/read-back |
| Step read-back `started_at` / `completed_at` | Intervalo da confirmação nos jobs da API. A evidence registra status/digest, sem timestamp próprio de read-back |
| Health `generated_at` | Referência temporal da coleta; não comprova recência da próxima execução nem entrega do alerta |

Para afirmar promoção confirmada, exigir `promoted=true`,
`read_back_status=confirmed` e igualdade `candidate_digest ==
stable_digest_observed` no artifact do run/attempt certo. P1-01 garante o
estado naquele instante, não contra alteração administrativa futura.

### Timing e amostras

[`ci_timing.py`](../scripts/pipeline/operations/ci_timing.py) é análise sob
demanda, não é chamado automaticamente pelos workflows. Recebe IDs de runs;
total é `updated_at − created_at`, duração de job é `completed_at − started_at`
e espera bruta é `started_at − created_at` do job. Flags `--dependent` e
`--serialized` anotam, não subtraem dependências/concorrência. Jobs skipped
têm tempos nulos; conclusão de checks obrigatórios não exige resultado success.
A CLI lê apenas a primeira página de jobs: verificar completude antes de usar.

Health e timing calculam p90 escolhendo a amostra ordenada no índice
`round(0.9*(n−1))`, sem interpolação, e mediana dos valores presentes. É uma
estatística descritiva, sem intervalo de confiança ou estimativa de SLA. Um
snapshot histórico de timing (09/09/2026) cobriu 8 runs de fast checks e 5 de
validação; esses dados não medem tempo até stable nem comportamento
corporativo. Nenhum novo percentil foi calculado para a amostra curta desta
fatia.

## 6. Proposta de SLO e fronteira do SLA

Não há SLA corporativo acordado documentado nem SLO corporativo aprovado.
Os limites de 30h/48h/12h continuam thresholds técnicos, não compromissos.
As propostas abaixo são pauta de avaliação, sem mudar a policy:

| Proposta / indicador | Meta e justificativa | Viabilidade, dependências e avaliador | Revisar quando |
| --- | --- | --- | --- |
| Continuidade das execuções, I01 | PROPOSED: avaliar 30h para build e 12h para promoção como candidatos a limites de acompanhamento, sem percentual de disponibilidade | Reutilizam thresholds; lacuna histórica de 24,08h em reports mostra que 12h não está comprovado como atendido. Containers Products avalia dados e regras do scheduler com responsáveis da execução | Janela maior/completa, mudança de cadência/runner ou ocorrência de lacuna silenciosa |
| Atualização e release utilizável, I02/I03/I05/I06 | META A DEFINIR / EXTERNAL_PENDING; negociar frescor e tempo até promoção por framework | Faltam série de elegibilidade/confirmação e inventário verificado; Wolfi, CVEs, soak, infra e gates influenciam. Containers Products + consumidores + AppSec avaliam cobertura e tratamento de bloqueios | Dados representativos por framework, mudança de cobertura ou de critérios de elegibilidade |
| Revisão de exceções, I04 | PROPOSED: manter decisão rastreável até a data de revisão, sem prazo de correção de CVE | Um único caso observado não prova rotina; depende de triagem e autoridade de exceção. Containers Products e code owners; AppSec para decisão sob sua competência | Vencimento, nova exceção ou mudança de responsável |
| Entrega/atendimento de alerta | META A DEFINIR / EXTERNAL_PENDING; separar prazo de entrega e reconhecimento | Sem emissor externo ou série de entrega/ACK, não há meta numérica viável demonstrada. Containers Products e responsáveis pelo canal/atendimento avaliam | Canal autorizado, teste de entrega, responsáveis/janela definidos e amostra de operação |

Qualquer SLA exige escopo de frameworks/consumidores, horários de atendimento,
responsáveis, fontes/janelas/cálculos, critérios de violação, comunicação e
tratamento de exceções aprovados. Registrar data/versão e aprovadores reais;
sem acordo, continuar EXTERNAL_PENDING. Não prometer prazo de correção upstream,
promoção em uma hora, atendimento em minutos ou disponibilidade de 99,9%.

Falha de scan corretamente bloqueada comprova um controle e pode coexistir
com catálogo desatualizado. Falhas upstream/infra, falta de dados e no-op não
saem de métricas para melhorar números; devem aparecer como classes distintas.
Uma exclusão documentada (ADR, owner e review_by, como a do `dotnet8` até sua
remoção do catálogo em 17/09/2026) fica identificada fora do denominador
ativo, sem ser contada como release saudável.

## 7. Responsabilidade e diagnóstico

| Papel | Mantém / investiga / decide | Comunicação e limite |
| --- | --- | --- |
| Containers Products | Mantém workflows/testes/pins/runbooks e investiga primeiro a evidence da fábrica | Consolida impacto por framework/digest e comunica responsáveis e consumidores afetados; canal/janela corporativos ainda não definidos |
| Code owners e AppSec/Segurança | Code owners revisam policy/quarentena; AppSec decide exceções de segurança sob sua competência | Nenhuma exceção automática ou dispensa de gate; papel conforme [ADR-0003](adr/0003-controles-seguranca-workflows-federados.md) |
| Cloud / IAM / Network / PKI e responsáveis pelos serviços | Investigam/resolvem acessos, registry, runners, rede e confiança corporativos correspondentes | Containers Products apresenta erro, instante e recurso permitido; acessos e aceites EXTERNAL_PENDING |
| Times consumidores | Verificam bases e diagnosticam impacto nos builds/deploys de suas aplicações | Precisam receber orientação quando seu digest/framework for afetado; promoção/recovery da base não reverte aplicações |

Os handles da seção 3 continuam identidades de sandbox. Não há nomeação
corporativa de pessoas para plantão nem compromisso 24x7. A cadeia de
comunicação é uma responsabilidade proposta a operacionalizar, não prova de envio.

| Classe / sinal | Evidence e primeira ação de diagnóstico | Escalar quando / prova para encerrar |
| --- | --- | --- |
| Lacuna cron / health ausente | Conferir `generated_at`, janela, runs schedule e grupos ativos; distinguir API incompleta e ausência de execução | Scheduler/runner/serviço fora da competência do produto. Encerrar diagnóstico com execução/dados retomados e causa registrada; alerta histórico pode persistir até sair da janela |
| Vulnerabilidade ou secret bloqueante | Ler Trivy e evidence das duas arquiteturas, digest e packages; confirmar se a versão corrigida existe na origem | Correção depende de upstream ou decisão AppSec. Encerrar bloqueio só com candidato aprovado pelos gates ou exclusão formal; não alterar Trivy para obter verde |
| Erro operacional / evidence ausente | Conferir primeiro step falho, exit code, logs, acesso e retenção; falta de relatório não é scan PASS | Dependência de Cloud/IAM/Network/PKI/serviço. Encerrar com execução válida e evidence completa, preservando o erro original |
| Falta de candidato / soak / no-op | Ler `reason`, inventário usado pelo seletor, soak e digests; distinguir sem build, em quarentena, ainda em soak, anterior a stable e já stable | Ausência persistente de candidato aponta para publicação/upstream; no-op por digest igual não é incidente por si, mas não zera idade nem prova frescor. Encerrar com motivo e identidade comprovados |
| Publicação/signing/provenance incompletos | Conferir job inteiro além de `publication-evidence`, digests e attestations conforme [contrato de consumo](consumer-verification-contract.md) | Falha de serviço/identidade ou inconsistência. Encerrar com mesma identidade validada e verificável; assinatura ausente nunca vira aprovação |
| Promoção / mismatch de read-back | Conferir `promotion-evidence`, `promotion-scans`, steps de escrita/confirmação e candidato | Mismatch ou falha após escrita exige investigação: stable pode ter sido movida. Encerrar com digest confirmado e causa registrada, usando [promoção](../README.md#gate-de-promoção-para-stable-canário-de-soak) e [recovery](../README.md#recuperação-de-stable-runbook-m15) quando autorizado |
| Recovery / quarentena | Consultar evidence própria de recovery, digest anterior/restaurado e policy; health não cobre esse caminho | Necessidade de recuperação segue autorização/runbook; encerrar com verificações e read-back, comunicando impacto. Quarentena impede repromoção via mudança explícita revisada |
| Pin indisponível / drift Wolfi | Conferir tool-pins, falha de endpoint e hash; seguir [pins](../README.md#dependências-do-pipeline-e-tags) e [Wolfi](wolfi-signing-key.md) | Rotação/indisponibilidade requer owner e revisão; encerrar com origem/pin conferidos. Nunca atualizar trust automaticamente |
| Exceção vencida / exclusão formal | Conferir owner, review_by UTC, motivo e o ADR referenciado na exceção | Decisão vencida vai ao owner/code owners/AppSec aplicável. Encerrar com decisão revisada rastreável; renovação de data sozinha não corrige CVE |
| Alerta sem confirmação de recebimento | Preservar alerta, verificar se há envio/destino/recibo; hoje não há integração externa | Responsáveis pelo canal e operação definem caminho autorizado. Encerrar entrega somente com comprovante; encerrar atendimento exige ACK e resolução registrada |

Diagnóstico começa por leitura. Este runbook referencia procedimentos que
podem escrever/publicar, mas não concede autorização automática para executá-los.
Uma resolução deve registrar origem/causa, framework, run/attempt, commit,
digest, decisão, responsável e evidence de conclusão, sem dados internos restritos.

## 8. Aceites restantes do P1-08

Para fechar a fatia operacional completa, além desta documentação:

- definir owners corporativos reais, canal/destinatários, janela de atendimento
  e escalonamento, com responsabilidades e classificação/retenção aprovadas;
- decidir e autorizar integração externa; comprovar envio, entrega e
  reconhecimento em teste controlado, incluindo falha de entrega;
- obter série suficiente e completa por framework, separando execução,
  publicação, frescor/utilizabilidade e promoção confirmada;
- avaliar SLOs e formalizar eventual SLA com responsáveis/consumidores;
- decidir tratamento da dependência comum do scheduler, sem pressupor watchdog;
- prover acessos/serviços corporativos e realizar o primeiro aceite operacional
  corporativo. IAM, PKI, ECR, rede, scanner e Sigstore seguem os ADRs/RFC.

Nenhum desses aceites é inferido de aprovação documental. P1-01 permanece
hosted PASS limitado aos runs/frameworks comprovados; P1-02 e P1-03 PENDING.
Observações novas ficam como evidence, sem encerrar outra spec por inferência.
