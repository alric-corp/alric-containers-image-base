# EVIDENCE — P1-02

Estado: implementado e verificado localmente; preparado para revisão independente.
HOSTED ACCEPTANCE = NOT RUN.
Revisão independente: NOT RUN. Sem commit/push/PR.

## Fluxo confirmado no baseline

`285ada4d6948c2d7e7508dd0ba8883c38306c7a1`, origin/main obtida por fetch,
árvore limpa. P1-01/P1-03 já integrados; preservados. Shared fixado e limpo
em `7a9b055a462eeb8552d3404c26538b44e8ccd83f`.

| Campo | OCI validado | Contrato funcional |
| --- | --- | --- |
| run_id | run chamador | mesmo run chamador no pipeline de publicação |
| run_attempt | não está no nome | suffix do artifact |
| producer | shared validate-apko-images / validate | shared test-runtime-images / runtime |
| artifact name | validated-oci-X | runtime-X-N |
| conteúdo | OCI, validated-index.json, SBOM, lock e inputs | runtime-X-amd64.json e runtime-X-arm64.json |
| consumer | build-push, download por nome estável | build-push, download exigindo N=current attempt |
| digest representado | índice OCI e manifests de ambas plataformas | index_digest/manifest_digest; dev_index_digest/dev_manifest_digest em compilados |

Gate antigo lê apenas status; relatórios não registram contexto run/attempt.
Attempt1 com contrato aprovado seguido de falha no publicador pode reexecutar
só publicador no attempt2: OCI antigo é encontrado, runtime-X-2 pode não existir.

## Semântica oficial conferida

- Upload 7.0.1: `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a`.
- Download 8.0.1: `3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c`.
- [Contextos](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#github-context): run_id é estável; run_attempt incrementa.
- [Reruns](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs): mesmo SHA/ref do evento original.
- [Upload fixado](https://github.com/actions/upload-artifact/blob/043fb46d1a93c77aae656e7c1c64a875d1fc6a0a/src/upload/upload-artifact.ts#L68): overwrite apaga objeto e cria outro ID; OCI usa overwrite após scan. Runtime conserva nomes por attempt.
- [Download fixado](https://github.com/actions/download-artifact/blob/3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c/src/download-artifact.ts): com token, repository/run-id delimitam busca; sem token usa run corrente. Pattern zero-match não falha; um match extrai diretamente em path; vários criam diretórios por nome. Não usar merge-multiple.
- [Inputs download](https://github.com/actions/download-artifact/blob/3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c/action.yml): digest-mismatch default error protege ZIP, não vínculo OCI.
- [API artifacts](https://docs.github.com/en/rest/actions/artifacts#list-workflow-run-artifacts): listagem por run_id, sem parâmetro attempt, paginada. Retenção/exclusão/overwrite podem remover artifacts; não há garantia de sobrevivência.
- [Toolkit](https://github.com/actions/toolkit/blob/193fa46c20fde8b0ed54194bc08b841c78c0776d/packages/artifact/src/internal/client.ts#L50): reruns podem apresentar nomes duplicados; latest por nome não ordena suffix numérico de attempts.

## Histórico, sem novo hosted aceite

[R03](../../docs/old-checklist-closure.md) e M13 registram retry no run
34402226000 (09/09/2026), anterior ao gate funcional atual. API filter=all
preserva attempts1/2/3: job Validate go1-26 da tentativa2 e sua cópia na3
têm mesmos timestamps/steps, mas publicação3 reexecutou. Job.run_attempt
pode avançar sem produzir artifact novo. Isso fundamenta a política de
success herdado, não comprova esta implementação.

## Verificação local

Execução em 13/09/2026 UTC, macOS arm64, sobre o diff local do baseline acima.
Unit tests usam fixtures OCI locais, metadados simulados e hashing real;
não precisam de GitHub, AWS, Docker ou build de packages. Integração inclui
o servidor TLS local existente. Não houve chamada de Apko/Melange nesta fatia.

| Check | Resultado observado |
| --- | --- |
| `make test-unit` | exit 0; 294 testes, 5,692s |
| `make test-integration` | exit 0; 24 testes, 11,639s |
| `make lint-local` | exit 0; hardening, 52 pins/49 arquivos e catálogo |
| `make lint-shared` | exit 0; pin/inputs/hardening e políticas operacionais |
| `make lint-workflows` | exit 0 |
| `actionlint .github/workflows/build-base-images.yml` | exit 0 |
| `actionlint` sem argumentos | exit 1; ressalva preexistente abaixo |
| `python3 -B tools/check_ai_context.py` | exit 0 |
| `git diff --check` | exit 0 |
| `python3 -B -m unittest tests.unit.pipeline.runtime.test_contract_evidence -v` | exit 0; 26 testes novos, 0,245s |
| Runtime + gate direcionados | exit 0; 38 testes, 0,241s |

Logs locais: `/private/tmp/p1-02-{unit,integration,lint-local,lint-shared,lint-workflows,actionlint,actionlint-changed,negatives,specific}.log`.

Negativos executados novamente de forma explícita: mismatch de índice,
producer mais recente falho sem report novo e par compilado divergente.
Os três testes passaram comprovando rejeição, exit 0 do unittest, em 0,022s;
`/private/tmp/p1-02-explicit-negatives.log`. Não confundir PASS do teste
negativo com aprovação do artifact rejeitado.

### Decisões observadas em fixture determinística

Run **simulado** `41`, framework `nodejs24`; nenhum run hospedado com esse ID
foi consultado. Índice OCI real da fixture:
`sha256:fd447a61f5bdebb9f60b240a1c7a4a7a8c5c10ec4de7ca93d795b6d26ca22188`.

| Caso | Resultado |
| --- | --- |
| Attempt1 + runtime-nodejs24-1 | passed true, selected_attempt1, reused false |
| Attempt2, somente success herdado do producer | passed true, selected_attempt1, reused true; mesmo índice/manifests e hashes dos reports |
| Attempt2, reports para outro índice | passed false, selected_attempt null; no functional evidence matches |

Saída completa: `/private/tmp/p1-02-decision-samples.json`. Teste de retry
compara todos os bytes do layout antes/depois e comprova ausência de chamadas
de execução/build; teste CLI preserva a decisão em JSON. Attempts2/10
selecionam10, e dois attempts1/2 válidos selecionam2.

### Binding e integração

Producer agora registra schema_version1, repository, run_id, run_attempt e
revision a partir do contexto GitHub, além dos digests já existentes. O
run_id é o run produtor do report; não a origem externa opcional do dispatch
diagnóstico. O reusable continua no mesmo pin e executa o módulo do produto.

Download runtime usa token + repository/run-id explícitos e pattern com
suffix inicial numérico, sem confundir `nodejs22` com `nodejs22-dev`.
Não usa merge-multiple nem relaxa digest-mismatch. A seleção aceita as formas
flat e por nome efetivamente produzidas pelo download v8 e confronta todo o
conjunto baixado com a listagem completa de artifacts do run.

`verified_layout` confere hashes dos blobs e igualdade com validated-index.json
antes do gate. Cada report compara o índice e seu manifest contra essa
identidade; compilados também comparam o índice/manifests atuais do -dev.
A publicação mantém seu verify e Skopeo copy --all --preserve-digests e
read-back existentes. Não há prepare/repack, nova resolução ou novo índice
no publicador. O download adicional do -dev só lê/verifica o artifact aprovado.

runtime-gate-result.json guarda passed, run/attempt corrente, ID/nome/attempt
escolhido, índices/manifests, hashes dos reports, producer observado e reused.
Ele e as respostas API são preservados no artifact publication da tentativa.
JSON inválido, campos duplicados/NaN, legado sem digest/contexto, conflitos,
ausência, download parcial, expiração ou paginação incompleta falham fechado.

### Estado real dos producers e isolamento M13

[Run observado 34735740791](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34735740791),
no baseline285ada4, retornou55 jobs em filter=all. Producer
`build-base-images / Functional contract (go1-26) / runtime / Runtime go1-26 (both architectures)`,
ID103667197573, run_attempt1, completed/success. O contrato python3-13 falhou
nesse mesmo run; isso não deve impedir reutilização de evidência válida Go.

No R03, Validate go1-26 attempt2 (ID102637911743) e cópia attempt3
(ID102640672924) têm os mesmos horários20:42:06–20:42:35 e steps. Publicador3
(ID102640628902) executou20:50:27–20:51:03. A consulta por attempt3 também
retorna a cópia herdada. [API oficial de jobs](https://docs.github.com/en/rest/actions/workflow-jobs#list-jobs-for-a-workflow-run).
Portanto o gate exige producer mais recente success, mas permite artifact
anterior quando seu producer original passou e os digests continuam iguais.
Producer falho/cancelado/incompleto ou ambíguo bloqueia sem depender de novo report.
Essas consultas são pesquisa read-only, não hosted acceptance do novo código.

### Ressalva preexistente do actionlint amplo

Os três diagnósticos são exclusivamente do gerado cve-triage.lock.yml:
concurrency.queue nas linhas414/1147 e SC2016 na linha913. O arquivo está
byte a byte igual à HEAD. Extrair o blob da HEAD e rodar actionlint reproduziu
os mesmos diagnósticos, normalizando somente caminhos dos logs. Registro em
`/private/tmp/p1-02-actionlint-baseline.log`. O Makefile já excluía locks
gerados do lint manual; não foi alterado nem escondido um novo erro.

## Arquivos alterados e escopo

14 arquivos: `.github/workflows/build-base-images.yml`,
`scripts/pipeline/runtime/runtime_images.py`, novo
`scripts/pipeline/runtime/contract_evidence.py`,
`tests/unit/pipeline/runtime/test_runtime_images.py`, novo
`tests/unit/pipeline/runtime/test_contract_evidence.py`, `README.md`,
`docs/m09-m12-reusable-workflows.md`, `docs/m11-m04-operational-health.md`
e os seis Markdown desta spec.

Shared irmão e checkout fixado continuam limpos. Diff vazio para scan,
policies, release, promoção/read-back, Wolfi, catálogo, composição, IAM/OIDC,
pins e RFC ampla. O plano de cobertura e skips existentes foi preservado.
Nenhum commit, push, PR, rerun remoto, publicação ou auto-aprovação.

## Limitações e próximo aceite

Histórico malformado é rejeitado, não silenciosamente descartado; pode exigir
novo run. Relatórios anteriores sem contexto/schema não são migrados.
Disponibilidade/retensão das APIs/artifacts e nome do producer no reusable
fixado fazem parte das dependências. Download -dev e nova verificação de
integridade acrescentam IO; custo no runner hospedado ainda não foi medido.

Revisão independente Opus 5 MAX: NOT RUN. HOSTED ACCEPTANCE = NOT RUN.
Plano controlado em [plan.md](plan.md), sem falhas destrutivas ou alteração
dos gates. Incidente zlib permanece separado.

## Reconciliação hospedada — 2026-09-14

Adendo aos snapshots históricos, sem alterar seus resultados. Coleta somente
leitura do GitHub, concluída em 2026-09-14T14:26:52Z. Nenhum retry foi acionado.

### Janela, paginação e revisão

Consulta dirigida de `workflow.yml`, filtro created entre
2026-09-13T00:00:00Z e 2026-09-14T14:06:38Z, coletada às 14:18:43Z:
página 1, per_page=100, total_count=23, recebidos 23. **Todos attempt 1**.
Ancestralidade Git local confirma 15 revisões contendo a implementação
`654359c231241615baf09f046e4bd175bce30deb`, integrada pelo PR #55 em
`e3ed68259f66af41e8054a4c0ac29a54082ddd60`.
Isso significa “nenhum retry encontrado nesta janela”, não “nunca executado”.

Principal: [run 34852458933](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34852458933),
attempt 1, push/main, commit `8ed8260eba75d4f8b5d856cd1fba37a404a5129a`.
Jobs 55/55 e artifacts 47/47, cada consulta em uma página de 100.
Logs de attempt 1 completos e ZIPs pertinentes disponíveis. Foram usados
o código dessa revisão e os reports realmente preservados, não o resumo health.

### Caminho normal comprovado, sem reutilização

| Etapa | Identidade / resultado observado |
| --- | --- |
| Contrato go1-26 | Job 104005247750, 14:02:06Z–14:06:06Z, SUCCESS; download dos OCI aprovados e teste nas duas arquiteturas |
| Reports | Artifact 10351870297, runtime-go1-26-1, arquivos runtime-go1-26-amd64.json e runtime-go1-26-arm64.json, ambos status=passed |
| Publicação | Job 104006720016, 14:06:09Z–14:07:08Z, SUCCESS |
| Evidence de publicação | Artifact 10352725729, publication-go1-26-1; runtime-gate-result.json, validated-index.json, published-index.json e publication-evidence.json |

Extrato do gate preservado: `passed=true`, `run_attempt=1`,
`selected_attempt=1`, `reused=false`, `selected_artifact_id=10351870297`,
`latest_producer_job_id=104005247750`, `latest_producer_attempt=1`.
Repository, revisão, run e framework correspondem nos dois reports e no gate.

| Identidade | Digest completo |
| --- | --- |
| OCI index go1-26 | `sha256:b647a115bac41c6e21d0dce3f06a7631e452debe1fcbe6210ef6285d8d7ddd60` |
| Manifest linux/amd64 | `sha256:907a3d84e4a0829f1be51afb4b2b87d5de5f46bd2235a524198580f15fc74461` |
| Manifest linux/arm64 | `sha256:608b0bcb805acbe7c8df88663757d0d135be2678b2438a595d19be30060bffa2` |
| OCI index go1-26-dev | `sha256:80ccc9668150585214f25990dc293a91b3dc7e94cd9566f2eb6b43a983e64850` |
| Dev manifest linux/amd64 | `sha256:9bcbcd56e750a18f1fb5d1d8848d2bcb65f959636d98acb36cb3dc661052cece` |
| Dev manifest linux/arm64 | `sha256:6ccc7d9f24ac10eda4eafa378586602960d2c9ad49045e6da67f4c10fe5aeab4` |

Comparação local dos arquivos baixados: hashes dos dois reports conferem com
report_sha256 do gate; índices/manifests runtime/dev e contexto conferem.
SHA-256 dos bytes de published-index.json corresponde ao índice acima;
publication-evidence registra validated_digest=copied_digest=remote_digest.
O job executou Skopeo copy --all --preserve-digests, signing, SBOM e
provenance com SUCCESS. São provas do primeiro attempt, não de retry.
O contrato constrói aplicação de teste; isso não é rebuild da imagem base.
Sem attempt 2, não há como comparar jobs herdados/reexecutados nem demonstrar
ausência de rebuild/repack durante retry.

### Busca de candidato existente

Além do principal, foram examinados jobs dos runs 34738421104 (55/55),
34796737880 (55/55) e 34813257692 (19/19), uma página de 100 por consulta.
Os dois primeiros publicaram go1-26 e go1-26-dev com SUCCESS; os publishers
falhos dependiam de artifacts validados ausentes ou do par dev ausente.
O terceiro contém promoção, sem os publishers/contratos de build procurados.
Não foram baixados todos os artifacts/logs desses candidatos descartados;
a exclusão usa os jobs/steps, sem reinterpretar runs antigos pela main atual.

No run principal, 13 outros publishers falham em Require validated artifact;
go1-25 falha ao baixar o par dev, assim como seu producer funcional.
Os 13 scans anteriores falharam; o exemplo nodejs22 e sua CVE atual estão
na [evidence Wolfi](../2026-09-13-wolfi-signing-key/evidence.md#reconciliação-hospedada--2026-09-14).
Não se encontrou, nesses candidatos dirigidos, falha downstream após um
contrato válido que justifique recomendar rerun para esse aceite.
A conclusão não cobre todos os possíveis candidatos fora da janela ou todos
os logs dos 23 runs. Os jobs do PR são contexto PR, não publicação main.

O lote principal é inadequado como ensaio mínimo: rerun failed jobs pode
reexecutar builds/scans falhos e dependentes, com escritas de publicação.
Não presumir que jobs bem-sucedidos nunca serão reexecutados por dependências.
A falha global do lote não constitui a falha downstream exigida pelo P1-02.

### Retenção e integridade dos materiais

Na coleta, os artifacts abaixo estavam não expirados:

| Material | ID | expires_at UTC |
| --- | --- | --- |
| validated-oci-go1-26 | 10350984493 | 2026-09-17T13:58:15Z |
| validated-oci-go1-26-dev | 10351009609 | 2026-09-17T13:58:43Z |
| runtime-go1-26-1 | 10351870297 | 2026-10-14T14:06:02Z |
| publication-go1-26-1 | 10352725729 | 2026-10-14T14:07:03Z |

OCI não foi baixado; sua retenção não prova elegibilidade de um rerun.
ZIP runtime SHA-256:
`f905c02b46cd06e44dd650ed2b85a36236aa9f662c991c3c4eeff318f37a1908`.
ZIP publication:
`272e62321cb1be959c9ad6b3aa78cfb226fa39b2828e96813de8ea23bde28519`.
Hashes identificam os downloads, não substituem assinatura/procedência.

### Conclusão e única execução futura recomendada

**HOSTED ACCEPTANCE = PENDING**. A01 tem observação hosted do primeiro
attempt; A03 tem binding comprovado nessa execução. A02 e a seleção/reuso
entre attempts continuam sem prova hosted. A04–A08 mantêm a cobertura local
anterior, sem exigir reprodução hospedada de cada negativo de fixture.
A nova reconciliação precisa de revisão independente.

Recomenda-se obter autorização para preparar e revisar o **workflow de aceite
isolado já previsto no [plan.md](plan.md#hosted-acceptance)**, antes de executá-lo.
Não há run existente recomendado para rerun nesta coleta.

- Alvo: sandbox, role/repositórios ECR de teste separados, identificados e
  autorizados pelo responsável; nenhuma criação ou alteração IAM implícita.
- Revisão: futuro SHA real integrado do laboratório, contendo P1-02, a ser
  registrado antes da execução; rerun executa esse SHA, não uma main posterior.
- Escopo mínimo: go1-26 e par go1-26-dev, ambos amd64/arm64.
  Attempt 1 valida OCI/contrato e para numa barreira revisada **antes de escrita
  de publicação no ECR**; attempt 2 usa Re-run failed jobs do mesmo run.
- Leituras previstas: GitHub artifacts/jobs, origens normais de build e ECR.
  Escritas previstas: artifacts GitHub, tags de teste, assinaturas/attestations
  e provenance no destino aprovado. Proibir stable/promoção/recovery no laboratório.
- Evidence: IDs/timestamps/steps dos dois attempts; OCI ainda retido e sem
  overwrite por rebuild; reports anteriores; gate selected_attempt=1,
  reused=true, passed=true; digests runtime/dev iguais; publicação verificada;
  confirmação de que build/contrato foram herdados e não reexecutados.
- Interromper se scan/contrato falhar, artifact expirar, identidade/digest
  divergir, destino não estiver isolado ou surgir necessidade de privilégios
  adicionais. Não provocar falha em assinatura/publicação produtiva.
- Autorização separada necessária para implementação do laboratório, revisão
  e execução/escritas nesses alvos. Nenhuma dessas ações ocorreu nesta sessão.

Verificações locais desta rodada: seis testes documentais, lint-local,
check_ai_context, links dos documentos alterados e diff check PASS.
Registro consolidado em [evidence da reconciliação](../2026-09-14-shared-origin-portability/evidence.md#verificações-locais-desta-reconciliação).
Nenhum teste local é apresentado como execução de retry hospedado.


## Implementação local do laboratório isolado — 2026-09-14

Registro posterior à reconciliação acima; nenhum resultado histórico foi substituído.
PR #63 consultado em leitura: MERGED em 2026-09-14T17:19:41Z;
head `83b364610d4e4235e738d480051b9efa0a476a4e`, merge
`62af489234e29f7f731a7b9c6266143229087129`. Após fetch do sandbox confirmado e
fast-forward com árvore limpa, main/HEAD/origin/main correspondem a esse merge.
Remote: alric-corp/alric-containers-image-base; checkout na raiz do repositório.
Nenhuma reconciliação destrutiva, staging, commit, push ou PR nesta rodada.

A biblioteca canônica permaneceu limpa em
`b574bd487e7c598c12ab6c6e584a523e03caaa45`; checkout consumido limpo em
`7a9b055a462eeb8552d3404c26538b44e8ccd83f`, composite preservada em
`eea2d2f4c4102ded74204e4131c1417f444ae3fc`. Não foi necessário novo release.

### Rastreabilidade da implementação

- Novo `.github/workflows/partial-retry-lab.yml`: dispatch dedicado,
  callers locais validate-base-images/test-runtime-images, gate real,
  baseline retida, comparação e barreira; nenhum caminho ECR.
- Novo `scripts/pipeline/runtime/retry_lab.py`: guard e comparação da evidência
  já aprovada por runtime_images --gate. Não fabrica PASS de contrato.
- Novo `tests/unit/pipeline/runtime/test_retry_lab.py`: 25 testes locais,
  layouts OCI com blobs reais de fixture, reports e APIs paginadas sintéticas.
- Os seis documentos desta spec receberam somente acréscimos desta rodada.
  Total: nove arquivos, três novos e seis Markdown modificados.
- Runtime/dev partilham os reports funcionais por arquitetura; o gate atual
  vincula índices/manifests de ambos. Os workflows e o gate produtivos não mudaram.

A aptidão observada do par Go é o snapshot já reconciliado do run
34852458933/1, revisão 8ed8260eba75d4f8b5d856cd1fba37a404a5129a.
Não houve novo build nem consulta operacional para alegar aptidão atual das
fontes remotas. O ensaio futuro só chega à barreira se os gates reais passarem.
O caller preserva também os cinco probes de image-trust existentes; não é
uma execução do lote de publicação dos 16 frameworks.

### Verificação realmente executada nesta rodada

| Check | Resultado |
| --- | --- |
| make test-unit | PASS: 375 testes, incluindo 25 novos do laboratório |
| make test-integration | PASS: 24 testes, incluindo contratos dos adaptadores |
| unittest test_retry_lab + test_contract_evidence + test_runtime_images | PASS: 63 testes; subconjunto dos unitários, não somar |
| make lint-local | PASS; 60 pins em 51 arquivos; catálogo/lote preservados |
| make lint-shared | PASS; origem/SHA/contratos e retenção verificados |
| make lint-workflows | PASS; inclui workflow novo e os dois reusables consumidos |
| actionlint .github/workflows/partial-retry-lab.yml | PASS |
| python3 -B tools/check_ai_context.py | PASS |
| git diff --check | PASS |

Negativos executados: contexto/input/evento/revisão/attempt inválidos;
contrato ausente ou falho; dev ausente; OCI adulterado e JSON inválido;
producer failure mais recente; outro run/framework; seleção ou reutilização
incorreta; execução de producer diferente mesmo com digests iguais; troca de
artifact; baseline ausente/expirada/ambígua/tardia; falha fora da barreira;
metadados incompletos ou producer posterior ao início do consumer.
Testes de wiring verificam ordem gate→manifest→upload→barreira, ausência de
publicação/credenciais adicionais e ausência da instrumentação em workflows normais.
A CLI real do gate é exercitada antes da CLI do laboratório nas fixtures.
O código não usa mocks como prova de autorização AWS ou execução hospedada.

### Fontes e limites

Fontes oficiais consultadas nesta implementação:
[rerun de workflows/jobs](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)
(SHA/ref originais) e [API de jobs](https://docs.github.com/en/rest/actions/workflow-jobs)
(metadados de execução). O plan registra paginação, retenção e checklist futura.
Nenhuma coleta de runs de build, download de artifact, chamada AWS, assinatura,
scan real ou operação de publicação foi executada nesta sessão.

A comparação local não comprova como o GitHub apresentará todos os jobs herdados
num rerun real. Dados ausentes/divergentes falham fechado, sem inferir ausência
de rebuild por ausência de logs. A conclusão final do consumer exige leitura
posterior do job: seu manifest é produzido enquanto está in_progress.

LAB_IMPLEMENTATION=IMPLEMENTED (ensaio sem publicação); LOCAL_VERIFICATION=PASS;
INDEPENDENT_REVIEW=PENDING; EXECUTION_AUTHORIZED=NO;
ATTEMPT_1_EXECUTED=NOT RUN; ATTEMPT_2_EXECUTED=NOT RUN;
P1-02 HOSTED_ACCEPTANCE=PENDING. A publicação real prevista pelo aceite original
não foi implementada neste workflow e requer extensão e autorização separadas.
A aprovação desta rodada ainda será feita por revisão independente.

## Resultado hospedado do laboratório — 2026-09-14

Registro incremental posterior à implementação local; os snapshots anteriores
não foram reescritos. Coleta somente leitura concluída após o attempt 2 do run
`34889507318`, na revisão `13b50102d29fab89509c5d539e72659529686a37`.
Operação realizada: `Re-run failed jobs`; não houve novo dispatch, attempt 3,
AWS ou publicação.

### Attempt 1

O workflow terminou FAILURE esperado. Jobs: `request` SUCCESS (`104128348177`),
`lab-build` SUCCESS em todos os producers, `lab-contract` SUCCESS
(`104129684652`) e `lab-retry` FAILURE (`104130985194`). A única falha foi o
step `Controlled attempt-1 barrier`, exit code 42, marker
`EXPECTED_LAB_FAILURE`. Gate e baseline foram concluídos antes da barreira;
upload da evidência terminou SUCCESS.

Gate real (`runtime-gate-result.json`): `passed=true`, `run_attempt=1`,
`selected_attempt=1`, `reused=false`, framework `go1-26`, artifact
`runtime-go1-26-1`, ID `10365489260`.

Artifacts de baseline/produção: `validated-oci-go1-26` ID `10365723347`,
`validated-oci-go1-26-dev` ID `10366560899`, baseline
`runtime-lab-p1-02-baseline-34889507318` ID `10366571924`, evidence attempt 1
ID `10366556964`. Todos estavam `expired=false` durante a coleta.

### Attempt 2

O mesmo run terminou SUCCESS no attempt 2. O consumer `Lab retry gate`
(`104141878086`) baixou a baseline, executou o gate real e registrou:

```text
passed=true
run_id=34889507318
run_attempt=2
revision=13b50102d29fab89509c5d539e72659529686a37
framework=go1-26
selected_attempt=1
reused=true
selected_artifact=runtime-go1-26-1
selected_artifact_id=10365489260
latest_producer_job_id=104141878260
latest_producer_attempt=2
```

`latest_producer_attempt=2` é a representação do job herdado/copiado pelo
GitHub. Os 12 producers observados no attempt 2 conservaram exatamente os
timestamps e steps do attempt 1; seus novos IDs não representam nova execução.
Os artifacts produtores mantiveram IDs, criação, tamanho e digest; não surgiu
`runtime-go1-26-2` nem artifact OCI substituto. O artifact de evidência do
attempt 2 é `runtime-lab-p1-02-attempt-34889507318-2`, ID `10368037207`.

O barrier registrou `LAB_BARRIER_PASSED`, exit code 0. Nenhum step do consumer
falhou. A evidência do attempt 2 declara `publication=NOT_IMPLEMENTED`.

### Digests e reports revalidados

Os hashes dos ZIPs foram conferidos contra os digests do GitHub. Os layouts
OCI foram re-hasheados, incluindo blobs, índice e manifests de ambas as
plataformas:

```text
runtime index   sha256:78d52b14e6d10befbffd5d8144f8b1d75ccd3bfbd98ee7f66c2a18e897115208
runtime amd64   sha256:7da4cb558944fa44050706d4f12106509400b7b1527c4ed2de6d592e42977ef0
runtime arm64   sha256:de503854a670e0112c7e2516a142e2a6332799389e7e0e11a5e9744178a9dd90
dev index       sha256:1b7ac732011843ad9a19a2dfd58fab6233d8012b9b466926cfef59410f34ca97
dev amd64       sha256:751bfe2db1fb313842c0229ee8aef95624deeeb6e5773b44bbeda6e2e0de64be
dev arm64       sha256:7f4d8e0f455e3bd04dcf1e3a18d7f86acbf1c685df0eeb2ff53c80a9ec09274b
report amd64    a76f5f5ae6cc7987688278acb64735b7d08a62129395cb999c7e4a5a6f7498fc
report arm64    54757284c4072cc52b5e86ec4487657b76324e9abe4e4131461fe6fb5787fd91
```

Os bytes dos reports foram idênticos no artifact funcional original e nas
evidências dos attempts 1 e 2. A baseline permaneceu única, íntegra e ligada
ao mesmo run/SHA/framework. A coleta consultou uma página completa de jobs
(26 registros dos dois attempts) e uma página completa de artifacts (17).

### Estados e limite

```text
LAB_IMPLEMENTATION = IMPLEMENTED
LOCAL_VERIFICATION = PASS
INDEPENDENT_REVIEW = APPROVE
ATTEMPT_1_EXECUTED = VALIDATED
ATTEMPT_2_EXECUTED = VALIDATED
RETRY_REUSE_HOSTED = PASS
PUBLICATION_CONTINUATION = PENDING
P1-02 HOSTED_ACCEPTANCE = PENDING
```

O ensaio comprova retry/reuse hospedado sem rebuild. Não comprova publicação
por digest, ECR, Cosign, provenance, SBOM attestation, read-back remoto ou
stable promotion. Reports, baseline e evidence expiram em 30 dias; OCI expira
em 3 dias. A revisão independente re-hasheou os OCI enquanto disponíveis.
Próxima fase única: **P1-02 — Publication continuation after reused evidence**,
com destino de teste isolado, stable proibida, inputs externos, revisão e
autorização próprios. Nenhuma implementação ou execução dessa fase ocorreu.

## Investigação sandbox read-only para infraestrutura de publicação — 2026-09-15

Coleta somente leitura na conta sandbox, sem criar/alterar recurso AWS, sem
assumir a role de execução do laboratório e sem publicar imagem. Nenhum
workflow foi despachado. Substitui `UNKNOWN`/`EXTERNAL_INPUT_REQUIRED` do
desenho anterior por fatos observados; não decide nem aplica nada.

### Identidade da sessão de investigação

`aws sts get-caller-identity`: Account `712107929769` (confere com o
esperado), Arn `arn:aws:iam::712107929769:user/Tomas-Instructor`, UserId
`AIDA2LTHQWCUSKYQ7WQ6S`. Usuário humano do operador, não uma role de workflow;
usado só para leitura IAM/ECR nesta investigação.

### Role existente `github-actions-image-base`

ARN `arn:aws:iam::712107929769:role/github-actions-image-base`, path `/`,
RoleId `AROA2LTHQWCUZEZTDLWPR`, criada em `2026-09-08T00:35:13Z`,
`MaxSessionDuration=3600`, sem tags, sem permissions boundary
(`PermissionsBoundary` ausente na resposta de `get-role` = `OBSERVED_NONE`).
`RoleLastUsed`: `2026-09-15T01:32:52Z` em `us-east-1`.

Trust (`AssumeRolePolicyDocument`), Sid `GitHubOIDCImageBase`:

```json
"Condition": {
  "StringEquals": {
    "token.actions.githubusercontent.com:sub":
      "repo:alric-corp@178685987/alric-containers-image-base@1360616627:ref:refs/heads/main",
    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
  }
}
```

Somente `StringEquals` (nenhum `StringLike`/wildcard). Não há condições
separadas para `repository`, `repository_id`, `repository_owner_id`, `ref`
ou `job_workflow_ref` — toda a restrição de repositório/branch está embutida
na única string `sub`. Respostas às perguntas do desenho:

- A. Aceita somente `refs/heads/main`? **Sim**, embutido no `sub`.
- B. Aceita o repository correto? **Sim**, owner ID 178685987 e repository ID
  1360616627 conferem com os já documentados em
  [ADR-0002](../../docs/adr/0002-sigstore-trust-model.md) e
  [contrato de consumo](../../docs/consumer-verification-contract.md).
- C. Vinculada a um workflow específico? **Não** — `job_workflow_ref` não é
  usado; qualquer workflow deste repositório despachado em `main` produz o
  mesmo `sub` e passaria nesta trust.
- D. Contém wildcard? **Não** neste statement.
- E. Um `partial-retry-lab.yml` em `main` seria estruturalmente elegível?
  **Sim**, pela mesma razão do item C.

Classificação da trust: **STRUCTURALLY_COMPATIBLE** — compatibilidade
estrutural, não autorização de execução; a role nunca foi assumida nesta
investigação.

### Policies efetivas anexadas

Um managed policy anexado, `github-actions-image-base-ecr`
(`arn:aws:iam::712107929769:policy/github-actions-image-base-ecr`), versão
única `v1` (default). Zero inline policies. Zero tags na policy.

Documento completo (`get-policy-version`):

```json
{
  "Statement": [
    {"Sid": "EcrAuth", "Effect": "Allow",
     "Action": "ecr:GetAuthorizationToken", "Resource": "*"},
    {"Sid": "EcrImageBaseRepos", "Effect": "Allow",
     "Action": ["ecr:CreateRepository", "ecr:DescribeRepositories",
       "ecr:DescribeImages", "ecr:BatchGetImage",
       "ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer",
       "ecr:InitiateLayerUpload", "ecr:UploadLayerPart",
       "ecr:CompleteLayerUpload", "ecr:PutImage",
       "ecr:PutImageTagMutability", "ecr:PutImageScanningConfiguration",
       "ecr:TagResource", "ecr:ListTagsForResource"],
     "Resource": "arn:aws:ecr:us-east-1:712107929769:repository/image-base-*"}
  ]
}
```

Nenhum `sts:*`, `kms:*`, `s3:*`, `secretsmanager:*` ou `iam:*` nesta policy.

**Achado central desta investigação**: o `Resource` do segundo statement é
`arn:aws:ecr:us-east-1:712107929769:repository/image-base-*` — um prefixo
wildcard, não uma lista explícita de ARNs e não `Resource: "*"` irrestrito.
Esse prefixo cobre **todo o catálogo de frameworks atual** (`image-base-<
qualquer nome>`) e, por coincidência de nomenclatura, cobre também
`image-base-p102-lab-go1-26` e `image-base-p102-lab-go1-26-dev` — os dois
repositórios propostos para o laboratório de publicação, que ainda não
existem. A role atual, sem nenhuma mudança, já teria `ecr:CreateRepository`,
`ecr:PutImage`, `ecr:PutImageTagMutability` etc. sobre nomes futuros que
comecem com `image-base-`. Isso não é isolamento por recurso: a mesma
credencial que publicaria no laboratório também alcança
`image-base-go1-26`/`image-base-go1-26-dev` e qualquer outro repositório do
catálogo com esse prefixo, hoje ou no futuro.

Grants não previamente inventariados em
[docs/iam-permission-contract.md](../../docs/iam-permission-contract.md):
`ecr:PutImageScanningConfiguration`, `ecr:TagResource` e
`ecr:ListTagsForResource` estão presentes na policy real e não constavam da
tabela O01–O18 daquele documento.

### Escopo ECR observado da role atual

A role não alcança "qualquer ECR da conta" (não há `Resource: "*"` nas
actions de escrita) nem usa lista explícita de ARNs individuais — o alcance
real é o prefixo `image-base-*`. Sob esse prefixo, a role já consegue
escrever hoje em `image-base-go1-26`/`image-base-go1-26-dev` (é a role de
produção) e escreveria igualmente em qualquer repositório futuro com esse
prefixo, lab incluído. Isso é informação de risco (blast radius), não uma
autorização concedida por esta investigação.

### ECRs de produção — configuração observada

| Campo | `image-base-go1-26` | `image-base-go1-26-dev` |
| --- | --- | --- |
| repositoryArn | `arn:aws:ecr:us-east-1:712107929769:repository/image-base-go1-26` | `.../image-base-go1-26-dev` |
| createdAt | 2026-09-07T22:02:44-03:00 | 2026-09-09T16:58:16-03:00 |
| imageTagMutability | IMMUTABLE_WITH_EXCLUSION | IMMUTABLE_WITH_EXCLUSION |
| exclusionFilters | WILDCARD `stable` | WILDCARD `stable` |
| encryption | AES256 | AES256 |
| scanOnPush | true | true |
| repository policy | `AllowCrossAccountPull` (Principal `*`, condição `aws:PrincipalOrgID=o-5gqr9v3h2q`, ações `BatchGetImage`/`GetDownloadUrlForLayer`) | OBSERVED_NONE (`RepositoryPolicyNotFoundException`) |
| lifecycle policy | expira só imagens untagged após 30 dias; tagged (inclusive `stable`) preservado | idêntica |
| tags | nenhuma | nenhuma |

`IMMUTABLE_WITH_EXCLUSION` com exclusão `stable` significa: toda tag é
imutável (não pode ser sobrescrita), **exceto** a tag literal `stable`, que
permanece mutável para permitir a promoção mover o ponteiro. Isso não impede
a role atual de escrever `stable` — é só uma trava de mutabilidade de tag,
não de identidade/principal; confirma o risco já registrado em
[docs/iam-permission-contract.md](../../docs/iam-permission-contract.md#limitação-publisher--promoter--stable):
"Imutável + Exclusões" não protege `stable` contra a própria role.

O escaneamento contínuo (`ecr:get-registry-scanning-configuration`) é
`ENHANCED`/`CONTINUOUS_SCAN` sobre `*` no nível do registry — aplica-se
igualmente a qualquer repositório futuro, lab incluído, sem exigir grant
adicional na role.

### Repositórios de laboratório

`image-base-p102-lab-go1-26` e `image-base-p102-lab-go1-26-dev`: ambos
**NOT_FOUND** (`RepositoryNotFoundException` em `describe-repositories`,
confirmado individualmente para os dois nomes). Nenhum recurso a inspecionar,
nenhum consumidor possível ainda.

### Camadas adicionais (SCP / boundary / registry policy / session policy)

| Camada | Estado |
| --- | --- |
| Permissions boundary da role | OBSERVED_NONE (`PermissionsBoundary` ausente em `get-role`) |
| SCP / Organizations | OBSERVED — única policy anexada à conta é `FullAWSAccess` (AWS managed, padrão), sem restrição adicional visível; org `o-5gqr9v3h2q` confere com a condição do repository policy de `image-base-go1-26` |
| Registry policy ECR (nível de conta) | OBSERVED_NONE (`RegistryPolicyNotFoundException`) |
| Session policy do step `configure-aws-credentials` | OBSERVED_NONE — o publicador (`build-base-images.yml`) não declara `inline-session-policy`/`managed-session-policies`, conforme código-fonte já revisado |
| VPC endpoint policy | NOT_VISIBLE_FROM_CURRENT_IDENTITY — sem VPC/endpoint ID relevante identificado; execução via GitHub-hosted runner não passa por VPC endpoint da conta |

Ausência de uma camada não é tratada como prova de ausência de restrição
onde não há visibilidade (VPC endpoint); onde há visibilidade real
(permissions boundary, registry policy, session policy do step), o estado é
`OBSERVED_NONE` porque a chamada de leitura respondeu "não existe", não
porque a camada é inacessível.

Provider OIDC (`token.actions.githubusercontent.com`): client ID
`sts.amazonaws.com`, thumbprint `2b18947a6a9fc7764fd8b5fb18a863b0c6dac24f`,
criado em `2025-08-12`, sem tags — consistente com o principal federado
referenciado na trust da role.

## Verificação local do job de publicação — 2026-09-15

Somente execução local; nenhum workflow foi despachado, nenhuma chamada AWS
foi feita nesta seção. Detalhes da arquitetura implementada em
[plan.md](plan.md#implementação-local-do-job-de-publicação--2026-09-15).

```text
python3 -B -m unittest tests.unit.pipeline.runtime.test_retry_lab_publish -v
  → 36 testes, OK
python3 -B -m unittest tests.unit.pipeline.runtime.test_retry_lab -v
  → 31 testes, OK (inclui os novos testes do job lab-publish)
make test-unit    → 437 testes, OK
make test-integration → 24 testes, OK
make lint-local   → OK
make lint-shared  → OK
make lint-workflows (actionlint) → OK
python3 -B tools/check_ai_context.py → OK
git diff --check  → sem erros
```

`renovate.json` ganhou `partial-retry-lab.yml` no gerenciador do pin do
Skopeo (o job novo introduz uma terceira ocorrência de
`quay.io/skopeo/stable`, já coberta pelo mesmo padrão usado em
`build-base-images.yml`).

## Verificação local da correção F1/F2 — 2026-09-15

Somente execução local; nenhum workflow foi despachado, nenhuma chamada AWS
foi feita. Detalhes em
[plan.md](plan.md#correção-f1f2-da-revisão-adversarial-do-job-de-publicação--2026-09-15).

```text
python3 -B -m unittest tests.unit.pipeline.runtime.test_retry_lab_publish -v
  → 48 testes, OK (12 novos: GateLayoutBindingTests, DigestFormatTests,
    mais extensões em FinalizeTests)
python3 -B -m unittest tests.unit.pipeline.runtime.test_retry_lab -v
  → 34 testes, OK (3 novos: posição exata do step de binding, uso de env:,
    finalize consumindo layout-binding)
make test-unit    → 453 testes, OK
make test-integration → 24 testes, OK
make lint-local   → OK
make lint-shared  → OK (o novo step inicialmente interpolava
  ${{ steps.verified.outputs.* }} direto em run:; corrigido para env: antes
  de reexecutar — a lint de hardening pegou isso na primeira passada)
make lint-workflows (actionlint) → OK
python3 -B tools/check_ai_context.py → OK
git diff --check  → sem erros
```

## Run hospedado 34976226951 e correção do `job_inventory` — 2026-09-15

Attempt 1 (`workflow_dispatch` explícito, `confirmation=P1-02-evidence-only`,
`reviewed-sha=25b33b279e4e5a64b3f0fc26595f9afdfb9a2ecc`) executou e concluiu
**PASS**: gate real, barreira controlada (`exit 42`), `Lab publish`
corretamente `skipped` (attempt 1), zero atividade AWS.

Attempt 2 (`gh run rerun 34976226951 --failed`) **FALHOU ANTES DE QUALQUER
PUBLICAÇÃO** — não no gate de retry/reuse em si, mas no step anterior a
ele:

```json
{"status": "INVALID_SCENARIO", "error": "unexpected job in laboratory run"}
```

### Causa raiz

`scripts/pipeline/runtime/retry_lab.py::job_inventory()` só reconhecia
`Lab request` e nomes iniciados por `PRODUCER_PREFIXES` (`'Lab build / '`,
`'Lab contract / '`), além do tratamento dedicado do consumidor
(`Lab retry gate`). O job `Lab publish`, introduzido pela implementação da
continuação de publicação (seção acima), nunca foi adicionado a esse
allowlist. A API `jobs?filter=all` do GitHub inclui a entrada de
`Lab publish` mesmo quando ele ainda vai ser `skipped` (o registro do job
já existe assim que o grafo do run é criado), então `job_inventory()`
rejeitava deterministicamente **todo** attempt 2 a partir desse ponto —
um defeito estrutural, não um evento pontual do run 34976226951.

Reproduzido isoladamente antes de qualquer alteração: um documento de jobs
sintético contendo `Lab request`, um `Lab build / ...`, um
`Lab contract / ...`, o consumidor `Lab retry gate` e um `Lab publish`
gera exatamente o mesmo erro (`unexpected job in laboratory run`) fora do
contexto hospedado, confirmando que a causa é unicamente essa função.

### Efeitos AWS confirmados (nenhum)

```text
Lab publish: skipped, steps: []
RoleLastUsed da role isolada do laboratório: {} (nunca assumida)
p102-lab-go1-26:     imageIds = []
p102-lab-go1-26-dev: imageIds = []
```

### Correção aplicada (somente local nesta sessão)

Nova constante `PUBLISHER = 'Lab publish'` em `retry_lab.py`; dentro do
laço de `job_inventory()`, uma segunda ramificação explícita (`if name ==
PUBLISHER: continue`), simétrica ao tratamento já existente do consumidor,
mas sem capturar o job em nenhuma estrutura: `Lab publish` nunca entra em
`by_name`/`latest` (o dicionário de producers), então sua presença — em
qualquer estado (`queued`, `in_progress`, `completed/success`,
`completed/skipped`, `completed/failure`, com ou sem `steps`) — não pode
alterar `latest_producer_attempt`, `selected_attempt`, `reused` ou a
detecção de rebuild/nova falha. Nomes não reconhecidos continuam rejeitados
(`'Lab unknown'`, `'Lab publisher'`, `'Lab publish unexpected'`, `'Random
job'`, `'Build go1-26'`, `'Lab security bypass'` etc.) — a correção não
introduziu um `startswith('Lab ')` permissivo.

`scripts/pipeline/runtime/retry_lab_publish.py`, a lógica de publicação
AWS/ECR/Cosign/SBOM/provenance, os guards de stable e a proposta IAM **não
foram alterados** — o achado é anterior à publicação em si e nenhum teste
demonstrou dependência inevitável dessas áreas.

```text
python3 -B -m unittest tests.unit.pipeline.runtime.test_retry_lab -v
  → 39 testes, OK (4 novos: presença de Lab publish em qualquer estado não
    altera o manifesto/producers; reuse válido com Lab publish presente;
    newer-producer-failure continua invalidando reuse com Lab publish
    presente; nomes desconhecidos continuam fail-closed) + 1 teste de
    drift (nomes de job do workflow ↔ constantes de job_inventory)
python3 -B -m unittest tests.unit.pipeline.runtime.test_retry_lab_publish -v
  → 48 testes, OK (inalterado — retry_lab_publish.py não foi tocado)
make test-unit    → 458 testes, OK
make test-integration → 24 testes, OK
make lint-local   → OK
make lint-shared  → OK
make lint-workflows (actionlint) → OK
python3 -B tools/check_ai_context.py → OK
git diff --check  → sem erros
```

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

Nenhuma nova execução hospedada, rerun, dispatch, alteração de IAM/ECR/vars
ou commit/push/PR foi feita nesta sessão. Pendente: revisão independente
desta correção antes de qualquer novo attempt hospedado.
