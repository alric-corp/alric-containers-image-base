# ACCEPTANCE — P1-02

| ID | Critério | Verificação prevista |
| --- | --- | --- |
| A01 | Primeiro attempt publica com contrato válido | Gate/CLI com índice OCI real em fixture |
| A02 | Attempt2 reutiliza report1 aprovado sem rebuild | Fixture de retry, success herdado e comandos do publicador |
| A03 | Índice/manifests correspondem ao candidato atual e par -dev | Digests reais e negativos de mismatch |
| A04 | Somente mesmo repository/run/revisão | API e reports cross-run rejeitados |
| A05 | Maior attempt numérico compatível é escolhido | Attempts1/2/10 e candidatos anteriores |
| A06 | Ausência não aprova | Zero artifacts, plataforma ausente, report legado, download parcial |
| A07 | Corrupção, conflito ou formato inválido falham | JSON inválido/duplicado, nome ambíguo, framework/plataforma errados |
| A08 | Gates existentes preservados | Diff, checks e publisher sem build/repack |

Producer mais novo falho/incompleto, mesmo sem artifact novo, deve bloquear
somente seu framework. Outra falha na matriz não invalida um contrato aprovado.
Dois reports nunca podem ser combinados de artifacts/attempts diferentes.
Falha de scan continua impedindo upload de OCI aprovado; não criar artifacts
falsos ou reduzir CVEs para testar retry.

Resultados A01–A08: **PASS local**, conforme testes e limites registrados em
[evidence.md](evidence.md). Não equivalem a aceite hospedado. Actionlint amplo
tem três diagnósticos preexistentes no workflow gerado, reproduzidos na HEAD;
o lint canônico e o workflow modificado passaram.
Revisão independente: NOT RUN. HOSTED ACCEPTANCE = NOT RUN.

## Estado corrente observado — 2026-09-14

[Coleta pós-integração](evidence.md#reconciliação-hospedada--2026-09-14):
23 runs na janela dirigida, todos attempt 1; 15 revisões contêm P1-02.
A01 e o binding de A03 foram observados em 34852458933/1, mas o gate registra
selected_attempt=1 e reused=false. **HOSTED ACCEPTANCE = PENDING**:
A02 exige o retry real, não apenas publicação normal ou igualdade de digest.
Não há novo encerramento independente; negativos/seleção mantêm PASS local.


## Aceite incremental do laboratório — 2026-09-14

Este complemento não substitui os critérios originais nem seu requisito de
continuação da publicação. HOSTED_ACCEPTANCE do P1-02 permanece **PENDING**.
Os resultados locais abaixo são fixtures/estrutura, não execução hospedada.

| ID local | Critério | Verificação local / limite hospedado |
| --- | --- | --- |
| L01 | Somente dispatch explícito no workflow/main sandbox e SHA autorizado | guard/CLI; inputs/eventos/revisões inválidos falham; execução NOT RUN |
| L02 | Produtores reais e gate existente, par Go multiarch completo | wiring e gate real sobre fixtures OCI; builds hospedados NOT RUN |
| L03 | Barreira 42 somente após gate/manifest/upload no attempt 1; 0 no 2 validado | testes de ordem, CLI e failure exclusiva; observação GitHub NOT RUN |
| L04 | Mesmo run/revision, artifact selecionado 1, runtime/dev e reports íntegros | gate e comparação real; negativos de identidade, adulteração e missing dev |
| L05 | Producer mais recente válido, execução herdada e artifacts não substituídos | IDs/timestamps/steps/API fixtures; confirmar metadados e logs hospedados NOT RUN |
| L06 | Sem publicação, credencial extra, stable/promotion/recovery ou efeito produtivo | testes estruturais, fluxo dedicado e adaptadores preservados |
| L07 | Retenção entre attempts e evidência suficiente para comparação | OCI 3 dias/reports 30; expiração/missing baseline falham; retenção efetiva NOT VERIFIED |
| L08 | Não confundir reuse pré-publicação com aceite integral | publicação futura não implementada; revisão e execução separadas pendentes |

Um scan bloqueado ou falha antes da barreira não satisfaz L03. Campos de fixture
não encerram qualquer critério hospedado. A coleta posterior deverá seguir a
checklist do plan, inclusive conclusão final do consumer após o snapshot.

## Resultado hospedado do laboratório — 2026-09-14

O run `34889507318`, na revisão `13b50102d29fab89509c5d539e72659529686a37`,
foi executado uma vez e depois submetido a **Re-run failed jobs**. A revisão
independente do Claude Code retornou **APPROVE**.

O attempt 1 terminou em FAILURE esperado: `request`, `lab-build` e
`lab-contract` foram SUCCESS; `lab-retry` falhou exclusivamente em
`Controlled attempt-1 barrier`, com exit 42 e `EXPECTED_LAB_FAILURE`, após o
gate e o upload da baseline.

O attempt 2 terminou SUCCESS. O gate real registrou `passed=true`,
`run_attempt=2`, `selected_attempt=1`, `reused=true` e selecionou
`runtime-go1-26-1` (artifact `10365489260`). O consumer terminou sem falhas e
a barreira registrou `LAB_BARRIER_PASSED`, exit 0.

### Matriz hospedada

| Critério | Estado observado |
| --- | --- |
| mesmo run, revisão e framework/par runtime-dev | PASS |
| evidence funcional anterior reutilizada | PASS |
| selected_attempt=1 / reused=true / passed=true | PASS |
| producers não reconstruídos | PASS — jobs herdados conservaram timestamps/steps; artifacts originais permaneceram |
| índices, manifests e hashes de reports | PASS — revalidados por hash |
| ausência de falha relevante mais recente | PASS |
| consumer do attempt 2 concluído | PASS |
| publicação, ECR, assinatura, provenance, SBOM, read-back ou stable | OBSERVED: NO PUBLICATION PERFORMED |

Assim, `RETRY_REUSE_HOSTED = PASS`, mas a ausência de publicação não satisfaz
a continuação exigida pelo contrato original. `PUBLICATION_CONTINUATION =
PENDING` e `P1-02 HOSTED_ACCEPTANCE = PENDING` permaneceram deliberadamente
até a seção abaixo.

## Hosted Acceptance Final — 2026-09-15

Este resultado **supera** o parágrafo anterior. A continuação de publicação
foi implementada, revisada (APPROVE) e provisionada em sandbox isolado.
Uma execução real (run `34976226951`) encontrou um defeito estrutural em
`job_inventory()` (não reconhecia o job `Lab publish`) e falhou **antes**
de qualquer escrita AWS — corrigido, revisado (APPROVE) e integrado via
PR #68. Um novo ciclo completo, run `34986578076`
(revisão `b910bd076021fc349615ee7dd191c7da9f3a009e`), executou attempt 1
(PASS, barreira controlada) e attempt 2 via `Re-run failed jobs` (PASS),
com publicação real nos dois repositórios ECR isolados. Detalhes completos
em [evidence.md](evidence.md#hosted-acceptance-final--2026-09-15).

### Mapeamento R1–R8 (spec.md)

| Req | Critério | Evidência do run `34986578076` |
| --- | --- | --- |
| R1 | Fronteira repository+run_id; run_attempt só identifica tentativas | Mesmo `run_id=34986578076` e `repository` em attempt 1 e 2; attempt 2 via rerun do mesmo run, não novo dispatch |
| R2 | Reports amd64/arm64 do mesmo artifact/attempt/framework, run/attempt/repository/revisão coerentes | `report_sha256` amd64/arm64 idênticos entre attempts; `revision=b910bd0...` em ambos |
| R3 | Selecionar maior attempt compatível; aprovar só com ambos reports passed | `selected_attempt=1` escolhido corretamente; `passed=true` em ambos attempts |
| R4 | Ausência/corrupção/formato inválido/identidade divergente falham | Não exercitado negativamente nesta execução de sucesso; comprovado por `test_retry_lab.py`/`test_contract_evidence.py` (PASS local, inalterado) |
| R5 | Falha do producer mais recente bloqueia; success herdado permite reutilizar report anterior | `latest_producer_attempt=2` (job herdado com sucesso), `reused=true`, report do attempt 1 reutilizado |
| R6 | Não esconder falha mais recente buscando PASS antigo | Não exercitado negativamente nesta execução; comprovado por testes locais (PASS local, inalterado) |
| R7 | Preservar scan, trust gate, publicação por digest, Cosign, provenance, SBOM, stable read-back, isolamento M13 | Scan/trust gate executados normalmente; Cosign/provenance/SBOM `VERIFIED`; `stable_touched=false`; framework único `go1-26` |
| R8 | Guardar decisão do gate/artifact/digests com a evidência; hosted acceptance só após rerun real | `gate.json`/`bind.json`/`layout-binding.json`/`final-result.json` preservados em `runtime-lab-p1-02-publication-34986578076-2` (ID `10405325731`); aceite via `gh run rerun --failed` real |

### Mapeamento A01–A08

| ID | Critério | Evidência hospedada |
| --- | --- | --- |
| A01 | Primeiro attempt publica com contrato válido | Attempt 1: gate `passed=true`, `Runtime go1-26 (both architectures)` success |
| A02 | Attempt2 reutiliza report1 aprovado sem rebuild | Attempt 2: `selected_attempt=1`, `reused=true`; `producer_comparison` (12/12 `execution_metadata_equal=true`); nenhum `runtime-go1-26-2` criado |
| A03 | Índice/manifests correspondem ao candidato atual e par -dev | `index_digest`/`platforms`/`dev_index_digest`/`dev_platforms` idênticos entre attempts e confirmados no ECR real |
| A04 | Somente mesmo repository/run/revisão | `run_id=34986578076`, `repository=alric-corp/alric-containers-image-base`, `revision=b910bd0...` em ambos attempts |
| A05 | Maior attempt numérico compatível é escolhido | `selected_attempt=1` (único compatível disponível) |
| A06 | Ausência não aprova | Não exercitado negativamente nesta execução de sucesso; comprovado por testes locais (PASS local, inalterado por esta rodada) |
| A07 | Corrupção/conflito/formato inválido falham | Não exercitado negativamente nesta execução; comprovado por testes locais (PASS local, inalterado) |
| A08 | Gates existentes preservados | Scan, trust gate e publisher productivo (`scripts.pipeline.release.verify_publication`/`publish_sboms`) executados sem bypass, diff/checks normais |

A06/A07 permanecem comprovados exclusivamente por evidência local/unitária,
como já registrado na abertura deste documento — uma execução hospedada de
sucesso não exercita, por definição, os caminhos de rejeição. Isso não é
lacuna: os testes correspondentes continuam no `make test-unit` e não foram
alterados nesta rodada.

### Veredito final

```text
P1-02 HOSTED ACCEPTANCE = PASS
```

Referência: run `34986578076`, artifact de evidência de publicação
`runtime-lab-p1-02-publication-34986578076-2` (ID `10405325731`), tag
publicada `p1-02-lab-34986578076-2` em `p102-lab-go1-26`/
`p102-lab-go1-26-dev`. Isto encerra o P1-02 dentro do escopo desta spec
(sandbox isolado, revisão independente por Claude Code). Não constitui
aceite corporativo, homologação AppSec, promoção de stable em produção ou
conclusão de P1-04 — ver
[handoff.md](handoff.md#handoff--encerramento-hospedado-do-p1-02--2026-09-15),
seção "Explicit non-claims".
