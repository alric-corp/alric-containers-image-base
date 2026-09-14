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
