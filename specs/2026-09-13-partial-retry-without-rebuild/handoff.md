# HANDOFF — P1-02

Baseline origin/main `285ada4d6948c2d7e7508dd0ba8883c38306c7a1`; branch local
`feat/partial-retry-without-rebuild`. Shared fixado7a9b055, sem alteração.
Estado: implementação local concluída e verificada, preparada para revisão.

## Entrega local

- Consumer baixa runtime de todos os attempts do run, mantendo artifacts
  separados; selector valida metadados paginados, producer, reports e OCI real.
- Report registra contexto do producer. Seleção usa maior attempt numérico
  compatível com índice/manifests e par -dev atuais. Status-only não aprova.
- Producer mais novo falho sem report bloqueia; success herdado permite report
  anterior cujo producer original passou. M13 permanece por framework.
- Gate e metadados são preservados na evidence de publicação. Não há rebuild,
  repack ou novo índice; download/verificação do par -dev acrescenta IO.
- 294 unitários,24 integração,26 testes novos PASS. Lints local/shared/workflows,
  actionlint do workflow modificado, contexto e diff PASS. Actionlint amplo:
  três diagnósticos preexistentes somente no lock gerado de CVEs, reproduzidos
  na HEAD; não alterado nesta fatia.
- 14 arquivos no diff, listados em [evidence.md](evidence.md). Shared limpo.
- Histórico malformado, expirado ou legado sem contexto pode exigir novo run.
  Nome do job producer depende do reusable fixado. APIs/download inconclusivos
  falham fechado; nenhuma heurística cross-run ou fallback para PASS antigo.

Preservar a diferença run_id/attempt, vínculo por índice OCI e falha fechada.
Não confundir success herdado de job com execução nova. Não fazer merge,
commit/push/PR, auto-aprovação, mudança de Wolfi/IAM/CVE ou rebuild no publicador.

Próximo passo: revisão independente antes de qualquer integração. Hosted
acceptance real ainda precisa de rerun seguro após merge/autorização, conforme
[plan.md](plan.md); evidências em
[evidence.md](evidence.md). Revisão independente Opus 5 MAX: NOT RUN.
HOSTED ACCEPTANCE = NOT RUN.

## Atualização pós-integração — 2026-09-14

O snapshot pré-merge acima permanece histórico. P1-02 está integrado via
PR #55/e3ed682; a coleta atual usa main 8ed8260 e
[registra](evidence.md#reconciliação-hospedada--2026-09-14) o gate e os reports
de 34852458933/1, índices runtime/dev e publicação normal confirmados.
**HOSTED ACCEPTANCE = PENDING**: selected_attempt=1, reused=false;
nenhum attempt > 1 na janela de 23 runs. Nova coleta ainda não revisada
independentemente.

Nenhum rerun de lote foi executado ou recomendado: os candidatos examinados
não apresentam a falha downstream exigida. Próxima ação: autorização para
preparar/revisar o ensaio isolado do plan, com alvos, SHA e escritas explícitos
antes de qualquer execução. Não usar ausência de logs ou digest igual como
prova única de ausência de rebuild. Aceites corporativos continuam externos.


## Handoff incremental — laboratório local — 2026-09-14

Baseline: `62af489234e29f7f731a7b9c6266143229087129` (merge PR #63).
Ler a seção de laboratório no plan para evento, inputs, ordem, retenção,
abort conditions, evidência e limite da publicação futura.

| Estado | Resultado desta rodada |
| --- | --- |
| LAB_DESIGN | Especificado para revisão |
| LAB_IMPLEMENTATION | IMPLEMENTED, fase sem publicação |
| LOCAL_VERIFICATION | PASS, resultados nesta seção nova da evidence |
| INDEPENDENT_REVIEW | PENDING para o laboratório |
| EXECUTION_AUTHORIZED | NO |
| ATTEMPT_1_EXECUTED | NOT RUN |
| ATTEMPT_2_EXECUTED | NOT RUN |
| HOSTED_ACCEPTANCE | PENDING para P1-02 |

Workflow: .github/workflows/partial-retry-lab.yml. Módulo auxiliar:
scripts/pipeline/runtime/retry_lab.py. O helper compara evidência do gate real;
não substitui seleção funcional nem publica. Os contratos locais chamam os
reusables existentes e preservam os probes de trust já obrigatórios.
A futura autorização deve identificar o SHA **integrado do laboratório**, não
esta baseline. Não executar dispatch/rerun por inferência da aprovação local.

Prioridade de revisão: contexto/guard, ordem da barreira, comparação com jobs
copiados, completude dos artifacts, fail-closed e ausência de caminho ECR.
Mesmo dois attempts satisfatórios não comprovam continuação da publicação:
a extensão isolada correspondente exige proposta/revisão/autorização própria.
A disponibilidade futura dos pacotes e o comportamento real das APIs entre
attempts permanecem sujeitos ao ensaio; fixtures não provam execução hospedada.
Não encerrar outras specs nem alterar pins, IAM, promoção ou health.
