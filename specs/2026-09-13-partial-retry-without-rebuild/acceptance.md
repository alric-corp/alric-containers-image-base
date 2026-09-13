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
