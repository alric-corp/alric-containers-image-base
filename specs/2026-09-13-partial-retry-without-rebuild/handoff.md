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

## Handoff pós-aceite hospedado — 2026-09-14

O run `34889507318` comprovou o retry/reuse hospedado no mesmo run e sem
rebuild. Attempt 1 foi validado com falha exclusiva da barreira; o attempt 2,
via `Re-run failed jobs`, reutilizou `runtime-go1-26-1`, selecionou attempt 1,
registrou `reused=true` e terminou SUCCESS. A comparação de jobs, artifacts,
steps, timestamps, índices, manifests e hashes está na evidence incremental.

```text
LAB_IMPLEMENTATION = IMPLEMENTED
LOCAL_VERIFICATION = PASS
INDEPENDENT_REVIEW = APPROVE
ATTEMPT_1_EXECUTED = VALIDATED
ATTEMPT_2_EXECUTED = VALIDATED
RETRY_REUSE_HOSTED = PASS
PUBLICATION_CONTINUATION = PENDING
HOSTED_ACCEPTANCE = PENDING — continuação de publicação não exercitada
```

Não houve AWS, ECR, assinatura, attestation, provenance, SBOM push, stable,
promotion ou recovery. A próxima fase deve ser separada, usar destino de teste
isolado, proibir `stable`, coletar os subjects/digests exigidos e obter
autorização explícita antes de qualquer escrita externa.

## Handoff — implementação local do job de publicação — 2026-09-15

O job `lab-publish` foi implementado em
`.github/workflows/partial-retry-lab.yml`, condicionado a
`run_attempt == 2 && needs.lab-retry.result == 'success'`, com
`scripts.pipeline.runtime.retry_lab_publish` (novo módulo, domínio
`runtime`) fazendo o binding fail-closed antes de qualquer auth AWS. Perfil
A (preprovisioned + execution-only): nenhum `CreateRepository`/
`PutImageTagMutability` no job. Destino fixo: conta 712107929769, região
us-east-1, role `github-actions-image-base-p102-lab`, repos
`p102-lab-go1-26`/`p102-lab-go1-26-dev` — nada disso existe/foi aplicado
ainda; são os mesmos valores da proposta em
`policies/aws/proposals/p102-lab-permissions/` (removido nesta limpeza; ver histórico Git).
Ver [plan.md](plan.md#implementação-local-do-job-de-publicação--2026-09-15)
para a arquitetura completa.

```text
PUBLICATION_JOB_IMPLEMENTATION = IMPLEMENTED
PUBLICATION_JOB_LOCAL_VERIFICATION = PASS
PUBLICATION_INFRA_DESIGN = PROPOSED
PUBLICATION_INFRA_APPLIED = NO
AWS_EXECUTION = NOT RUN
PUBLICATION_CONTINUATION = PENDING
P1-02 HOSTED_ACCEPTANCE = PENDING
```

Próximo passo: revisão independente desta implementação antes de qualquer
integração adicional; decisão externa de Cloud/IAM sobre a role/repos
isolados continua pendente e é pré-requisito para qualquer execução
hospedada real.

## Handoff — correção F1/F2 da revisão adversarial — 2026-09-15

Revisão independente retornou CHANGES REQUIRED (F1 HIGH: OCI publicado não
vinculado por digest ao gate de retry/reuse; F2 MEDIUM: `digest_equal` sem
validação de formato). Ambos corrigidos — ver
[plan.md](plan.md#correção-f1f2-da-revisão-adversarial-do-job-de-publicação--2026-09-15)
para os detalhes. Novo guard `require_gate_layout_binding` (sem import de
`scripts.pipeline.release`) e novo step no workflow, entre a revalidação
OCI e a auth AWS. `finalize()` reforça a mesma invariante. Estados
inalterados quanto à execução:

```text
PUBLICATION_JOB_IMPLEMENTATION = IMPLEMENTED
PUBLICATION_JOB_LOCAL_VERIFICATION = PASS
PUBLICATION_INFRA_APPLIED = NO
AWS_EXECUTION = NOT RUN
PUBLICATION_CONTINUATION = PENDING
P1-02 HOSTED_ACCEPTANCE = PENDING
```

Próximo passo: nova revisão independente desta correção.

## Handoff — correção do job_inventory (Lab publish) — 2026-09-15

Execução hospedada real do run `34976226951`: attempt 1 **PASS**; attempt
2 (`gh run rerun --failed`) **FAILED** antes de qualquer verificação de
retry/reuse, com `INVALID_SCENARIO — "unexpected job in laboratory run"`.
Causa: `retry_lab.py::job_inventory()` nunca foi atualizado para tolerar
o job `Lab publish` (adicionado na fase de implementação anterior) no
mesmo grafo. Zero efeito AWS confirmado (`RoleLastUsed={}`, ambos os ECRs
vazios). Detalhes completos em
[plan.md](plan.md#correção-do-job_inventory-para-reconhecer-lab-publish--2026-09-15)
e [evidence.md](evidence.md#run-hospedado-34976226951-e-correção-do-job_inventory--2026-09-15).

Corrigido localmente: nova constante `PUBLISHER = 'Lab publish'`;
`job_inventory()` passou a reconhecer e ignorar esse job (sem tratá-lo
como producer), simétrico ao tratamento já existente do consumidor.
Nomes desconhecidos continuam fail-closed (sem `startswith('Lab ')`
permissivo). `retry_lab_publish.py`/AWS/ECR/IAM não foram tocados.

```text
P1_02_ATTEMPT_1 = PASS
P1_02_ATTEMPT_2 = FAILED — HISTORICAL RUN 34976226951
RETRY_REUSE_HOSTED = PASS
PUBLICATION_JOB_FIX = IMPLEMENTED
PUBLICATION_JOB_FIX_LOCAL_VERIFICATION = PASS
AWS_PUBLICATION_EXECUTION = NOT RUN
PUBLICATION_CONTINUATION = PENDING
P1-02 HOSTED_ACCEPTANCE = PENDING
```

Próximo passo: revisão independente desta correção; só depois disso um
novo attempt hospedado (dispatch novo, não rerun) pode ser autorizado.

## Handoff — encerramento hospedado do P1-02 — 2026-09-15

Revisão independente da correção do `job_inventory` retornou **APPROVE**
e foi integrada via PR #68 (merge
`b910bd076021fc349615ee7dd191c7da9f3a009e`). Um novo ciclo hospedado
completo foi executado: run `34986578076`, attempt 1 via
`workflow_dispatch` (PASS, barreira controlada) e attempt 2 via
`gh run rerun --failed` (PASS), com publicação real na conta/região
sandbox. Detalhes completos em
[plan.md](plan.md#encerramento-hospedado-do-p1-02--2026-09-15),
[evidence.md](evidence.md#hosted-acceptance-final--2026-09-15) e
[acceptance.md](acceptance.md#hosted-acceptance-final--2026-09-15).

### Final proven state

- Mesmo run, mesmo SHA (`b910bd076021fc349615ee7dd191c7da9f3a009e`) entre
  attempt 1 e attempt 2 — attempt 2 via rerun, nunca novo dispatch.
- `selected_attempt=1`, `reused=true`.
- No rebuild: `execution_metadata_equal=true` em todos os 12 producers;
  `report_sha256`/`index_digest`/`platforms` idênticos entre attempts;
  nenhum artifact equivalente novo (`runtime-go1-26-2`) criado.
- Preservação exata de digest OCI, runtime e dev, incluindo ambas as
  plataformas (amd64/arm64), do gate até o registry remoto.
- OIDC sandbox: role isolada `github-actions-image-base-p102-lab`
  assumida pela primeira vez; sem fallback para a role operacional.
- ECR isolado: `p102-lab-go1-26`/`p102-lab-go1-26-dev`, `IMMUTABLE`, tag
  determinística `p1-02-lab-34986578076-2`.
- Cosign (assinatura), SBOM SPDX e provenance SLSA attestados e
  verificados sob a identidade própria do laboratório.
- Stable jamais tocada (`stable_touched=false`; repositórios operacionais
  sem escrita nova durante a janela do run).

### Explicit non-claims

Não comprovado por este P1-02:

- ambiente corporativo (esta execução usa apenas o sandbox AWS isolado
  712107929769/us-east-1, com role e repositórios ECR dedicados ao
  laboratório, fora do prefixo `image-base-*` operacional);
- IAM/PKI/rede corporativa;
- homologação AppSec;
- ECR corporativo/operacional (`image-base-go1-26`/`-dev` permanecem
  intocados);
- promoção de stable em produção;
- P1-04;
- nível SLSA formal (a attestation de provenance é produzida e
  verificada, mas nenhuma classificação de nível SLSA foi avaliada ou
  reivindicada nesta spec).

```text
P1_02_ATTEMPT_1 = PASS
P1_02_ATTEMPT_2 = PASS
JOB_INVENTORY_FIX_HOSTED = PASS
RETRY_REUSE_HOSTED = PASS
PUBLICATION_CONTINUATION = PASS
AWS_PUBLICATION_EXECUTION = PASS — SANDBOX LAB ONLY
P1-02 HOSTED_ACCEPTANCE = PASS
STABLE_PRODUCTION_PROMOTION = NOT RUN
```

A infraestrutura sandbox (role `github-actions-image-base-p102-lab`,
repositórios `p102-lab-go1-26`/`p102-lab-go1-26-dev`, conteúdo publicado
sob a tag `p1-02-lab-34986578076-2`) permanece existente e não foi
deletada nesta sessão; não é infraestrutura de produção. Próximo passo:
revisão final de evidências e decisão externa sobre quaisquer fases
subsequentes (aceite corporativo, P1-04, etc.), fora do escopo desta
spec.
