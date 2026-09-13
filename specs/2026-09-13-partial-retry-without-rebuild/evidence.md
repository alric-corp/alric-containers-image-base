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
