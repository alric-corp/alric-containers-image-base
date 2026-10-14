# Contrato operacional de alertas (G05)

Complementa o [contrato operacional](m11-m04-operational-health.md). Define o
evento de alerta que sai da detecção existente, os dados mínimos que podem
deixar o repositório e a diferença entre detecção, entrega e reconhecimento.
Implementação: [`alert_events.py`](../scripts/pipeline/operations/alert_events.py);
política: [`policies/operations/alerting.json`](../policies/operations/alerting.json).

| Item | Estado |
| --- | --- |
| Detecção (pins e saúde operacional) | Implementada e hospedada (último run lido: 38400943111, 13/10/2026) |
| Contrato de eventos | Implementado e testado localmente com transportes simulados |
| Canal oficial desta fase | Run do `pipeline-health.yml`: falha do job e resumo (decisão do owner, 02/10/2026) |
| Entrega externa | `NOT_CONFIGURED`: `external_destination=null` por decisão do owner; ativação aguarda aprovação |
| Reconhecimento humano (ACK) | `NOT_PROVEN` |
| SLO/SLA | Nenhum aprovado; nenhum valor deste documento é compromisso |

Detecção em verde ou em vermelho não prova atendimento. Este contrato não
oculta alertas: os dois `stable_age_hours` do incidente G01 e o
`execution_scope_review` vencido continuam eventos bloqueantes enquanto a
condição existir. Mudar `review_by` exige decisão do owner, não do alerta.

## 1. Ciclo do alerta

| Etapa | Hoje | Contrato G05 | Pendência |
| --- | --- | --- | --- |
| Detectar | `pin_inventory check` e `operational_health report`, diário (05:40 UTC) e por dispatch | Relatório ausente ou inválido vira evento `critical`/`high` | O scheduler é de melhor esforço e o health não observa o próprio cron |
| Classificar | Níveis `alert`, `known`, `out_of_scope`, `unknown` | Severidade, bloqueio e identidade estável; níveis suprimidos permanecem visíveis | Severidades são proposta |
| Encaminhar | Falha do job e resumo; notificação nativa do GitHub não verificada | `reports/alert-events.json` com os eventos; entrega externa `NOT_CONFIGURED` | Canal externo, destinatários e janela de atendimento |
| Reconhecer | Nenhum registro | ACK exigido e sempre `NOT_PROVEN` sem registro humano | Onde e por quem o ACK é registrado |
| Investigar | Runbook por classe de sinal (contrato operacional, seção 7) | `occurrence_id` liga o evento ao run e à tentativa | — |
| Recuperar | Procedimentos existentes; holds e recovery são G01/G07 | Sem ação automática | Autorização de cada recuperação |
| Encerrar | O alerta some quando a condição deixa de existir | O evento deixa de ser emitido; não há notificação `resolved` sem estado entre runs | Registro humano de encerramento |

No `pipeline-health.yml`, o passo `Build alert events without external
delivery` roda depois das medições, com `continue-on-error`, e grava
`reports/alert-events.json` no artifact `pipeline-health-<attempt>` (30 dias),
além de uma tabela no resumo. O passo final continua decidindo o job só por
pins e métricas; se os eventos não forem gerados, há um aviso no run.

## 2. Evento v1

Somente estes campos saem do repositório:

| Campo | Conteúdo |
| --- | --- |
| `event_id` | SHA-256 de origem, métrica e assunto: a mesma condição mantém o id entre runs |
| `occurrence_id` | `<run_id>-<attempt>-<event_id[:16]>`: esta detecção; usado como chave de idempotência |
| `state` | `firing` |
| `test` | `true` somente para o evento de teste controlado (`--test-event`) |
| `severity`, `severity_source` | Classificação da política; `default` indica métrica nova ainda não classificada |
| `blocking` | `true` quando o health falha por esse sinal |
| `source`, `level`, `metric`, `subject` | Origem (`operational_health`, `pin_inventory`, `health_monitor`), nível original, métrica e assunto |
| `summary` | Mensagem em uma linha, truncada e mascarada |
| `detected_at` | `generated_at` do relatório de health |
| `routing_key` | Chave de roteamento da política, nunca uma pessoa |
| `run` | Repositório, workflow, run, tentativa, SHA e URL |
| `repetitions` | Quantas vezes a condição apareceu no mesmo run |
| `acknowledgement` | `{"required": true, "status": "NOT_PROVEN"}` |

Não saem: relatórios brutos, logs, variáveis de ambiente, tokens, conteúdo
de artifacts nem a mensagem completa. No resumo, contas AWS, ARNs, tokens
GitHub, chaves AWS, credenciais em URL, `Bearer` e e-mails são mascarados.
A classificação desses dados no canal corporativo continua com o owner.

`known` e `out_of_scope` não geram eventos, mas aparecem em `suppressed` e
no resumo com contagem. Qualquer outro nível, inclusive um novo, é roteado.

## 3. Entrega e reconhecimento

`deliver` existe para um destino aprovado e só foi exercitado com transportes
simulados. Sem destino, todo evento fica `NOT_CONFIGURED`, sem tentativa.

| Status | Significado | Retry |
| --- | --- | --- |
| `ACCEPTED` | 2xx com o campo de recibo do destino | — |
| `AMBIGUOUS` | 2xx sem recibo ou corpo ilegível | Não: pode ter sido processado |
| `FAILED_AUTH` | 401/403 | Não |
| `FAILED_HTTP` | Outro erro HTTP | 408/429 sim; 5xx só com idempotência no destino |
| `FAILED_TIMEOUT` | Sem resposta; resultado desconhecido | Só com idempotência |
| `FAILED_TRANSPORT` | Falha de conexão | Sim se a requisição não saiu; senão só com idempotência |
| `RETRY_EXHAUSTED` | Tentativas esgotadas (máximo 3, espera 2 s e 8 s) | — |

Nenhum status de entrega é ACK: `acknowledged` é sempre `false`. Falha de
entrega fica registrada e não apaga o evento nem muda o resultado do health.
A credencial de um destino futuro vem de Actions secret, só no cabeçalho, e é
removida de qualquer mensagem de erro registrada.

ACK humano exige um registro fora da fábrica, vinculado ao `event_id` e ao
`occurrence_id`, com papel de quem reconheceu, horário e referência
(ticket ou mensagem). Até existir esse registro, `G05_HUMAN_ACK=NOT_PROVEN`.

## 4. Indicadores mínimos propostos (sem meta)

| Indicador | Fonte possível | Mensurável hoje |
| --- | --- | --- |
| Idade do último `stable` aprovado | Health (`stable_age_hours`, proxy por job); exato pelo Release Store e ECR | Proxy sim; exato não (exige leitura AWS) |
| Idade de candidatos validados | `candidate.json` (`dev_validated_at`) no Release Store | Não pelo health |
| Holds ativos e duração | `state/*.json` (`hold`, `pending_release`, `updated_at`) | Não pelo health; ligado à G01 |
| Falhas de workflows relevantes | API de runs (build, promoção, health) | Parcial: o health mede lacunas, não taxa de falha |
| Detecção → ciência do responsável | Registros de ACK | Não |
| Incidente → recuperação | Registros de abertura e encerramento | Não |
| Última execução bem-sucedida do health | Observador externo | Não: o health não mede o próprio cron |

Os limites internos atuais (30 h, 48 h, 12 h) continuam limites de alerta,
não SLO. Qualquer meta exige dados representativos e aprovação dos
responsáveis.

## 5. Heartbeat externo mínimo (proposta, não ativada)

Para detectar a ausência do próprio health, um observador fora do GitHub
receberia um sinal mínimo (run, horário) a cada execução concluída e
alertaria se ele faltar por mais que o limite aprovado (o atual é 30 h).
Depende de destino, credencial, dono e aprovação. O observador também pode
falhar; dependências comuns com o canal de alerta precisam ser avaliadas.

## 6. Ciclo de vida e transporte plugável

[`alert_delivery.py`](../scripts/pipeline/operations/alert_delivery.py) consome
`alert-events.json` num job próprio, separado do health, e registra:

| Estado | Quando | Nunca a partir de |
| --- | --- | --- |
| `EVENT_CREATED` | O evento existe no run | — |
| `DELIVERY_ATTEMPTED` | Cada tentativa, com status e erro mascarado | — |
| `DELIVERED` | O destino aceitou e devolveu referência, ou uma criação ambígua foi encontrada ao reler o destino | Suposição após timeout |
| `ACKNOWLEDGED` | Ação humana lida do destino: pessoa da lista `acknowledgers`, tipo `User`, fora de `automation_actors`, depois da entrega e com referência verificável | Entrega, recibo, HTTP 2xx, health verde ou ação de bot |
| `RESOLVED` | A condição sumiu de um run posterior e o destino foi atualizado | — |

O destino é a fonte de verdade entre runs: o alerta já aberto recebe um
comentário em vez de nova criação; uma lista ilegível do destino impede
qualquer escrita (`FAILED_RECONCILE`); uma criação com resultado incerto é
reconciliada relendo o destino antes de outra tentativa; falha ao atualizar um
alerta aberto não é repetida e aparece como `last_attempt`. Retry limitado a
três tentativas (2 s, 8 s) somente para 408/429/5xx e falhas de conexão.
`resolved_without_ack` evidencia alertas que se resolveram sem reconhecimento.

**Opção recomendada: Issues do GitHub** (adapter `github-issues`), porque
mantém o canal já decidido pelo owner (GitHub), não exige fornecedor nem
licença e dá um ACK auditável na timeline da issue. Uma issue por `event_id`
(rótulo `factory-alert-<16 hex>` e marcador `event_id:` no corpo); ACK é o
rótulo `factory-alert-ack` aplicado por uma pessoa autorizada; resolução
comenta, rotula `factory-alert-resolved` e fecha. Issues não criadas pelo
adapter nunca são alteradas. Limite: não é plantão nem escalonamento.

O adapter está declarado em `alerting.json` com `enabled: false`. Informações
mínimas que o owner precisa fornecer para habilitá-lo:

1. Repositório das issues. Neste repositório público as issues são públicas;
   um repositório privado de operação exige token com escrita de issues
   nele (o `GITHUB_TOKEN` só escreve no próprio repositório).
2. `assignees`: quem é notificado.
3. `acknowledgers`: quem pode reconhecer (logins).
4. Se falha de entrega deve reprovar o job de entrega (hoje reprova; o health não muda).
5. Expectativa de tempo até o ACK, se houver, sem virar SLO automaticamente.

## 7. Ativar o destino quando aprovado

1. PR com os valores acima em `alerting.json` (`enabled: true`) e
   `external_destination: "github-issues"` em `health.json`; o lint recusa
   adapter habilitado sem repositório, destinatários e `acknowledgers`.
2. Job `deliver` em `pipeline-health.yml`, depois do health, com `issues: write`
   só nele, baixando o artifact do run e enviando `alert-delivery-<attempt>`
   como evidência (retenção declarada em `health.json`).
3. Aceite controlado: dispatch com `--test-event`, issue `[TESTE]` criada
   (`DELIVERED`), rótulo de ACK aplicado pela pessoa autorizada, próximo run
   registra `ACKNOWLEDGED` com autor, horário e referência; com token sem
   permissão, `FAILED_AUTH` aparece e o health não muda.

## 8. Decisões do owner

- Canal externo e destinatários (o registro de 02/10/2026 cita Teams via
  Power Automate só como possibilidade futura).
- Severidades da política e quais eventos podem sair do repositório.
- Onde o ACK é registrado e quem o faz.
- Falha de entrega deve ou não reprovar o job de health.
- Heartbeat externo e indicadores com meta, quando houver compromisso
  operacional.
