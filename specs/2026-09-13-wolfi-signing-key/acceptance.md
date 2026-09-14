# ACCEPTANCE — P1-03 Wolfi signing-key defense-in-depth

| ID | Requisito | Critério observável | Verificação |
| --- | --- | --- | --- |
| A01 | R1/R4 | Apko/Melange configuram explicitamente a mesma chave local versionada | Configs, preflight e lock/build mínimo com verificação APK normal |
| A02 | R7 | Nenhum keyring do projeto aponta diretamente para a chave remota Wolfi | Lint e regressões nos dois consumidores e receitas novas |
| A03 | R2 | Chave local confere com SHA-256 versionado; mismatch falha | pin_inventory trust/lint, alteração de chave e pin incorreto |
| A04 | R2 | Chave ausente/corrompida ou formato inválido falha antes do build | Fixtures negativas e preflight anterior a lock/replay |
| A05 | R3 | Adoção inicial registra duas fontes oficiais com bytes e hashes iguais | Endpoint Wolfi e wolfi-dev/os em commit fixado na evidence |
| A06 | R5 | Rotação exige revisão; upstream não substitui chave/pin locais | Runbook, inspeção de código/workflows e negativos sem escrita |
| A07 | R6 | Drift gera falha operacional, sem escrita da chave/pin | Monitor same/divergent/unavailable e independência do preflight offline |
| A08 | R8 | Discovery permanece documentado como known tooling limitation | Evidência adversarial preservada, sem alegar exclusividade |
| A09 | R8 | Estado atual Wolfi registrado com data, opcionalmente | HTTP observado; 404 não é invariant, gate ou garantia futura |
| A10 | Invariantes | Repositories, Trivy, Cosign, provenance, SBOM, stable/read-back e IAM/OIDC preservados | Diff e checks existentes |

## Negativos e limites

Manter testes de pin incorreto, key alterada/ausente/inválida, outra RSA e URL remota inclusive
em outra receita e formato YAML inline. Divergência e indisponibilidade do
monitor falham health e não escrevem chave/pin. Testes locais não demonstram
execução hospedada ou legitimidade de futuras rotações. Discovery adversarial
fica em evidence como **EXPECTED TOOLING LIMITATION REPRODUCED**, com os
exits originais. Não convertê-lo em security control passed, expectedFailure
ou regressão falsa do novo requisito; nenhuma mudança no Apko é exigida.

## Aceite externo

Revisor independente avalia diff/spec/evidência antes da integração.
Após autorização e merge, provar `hosted build → local versioned key configured
→ preflight passes → normal package verification/build continues`; não exigir
exclusividade de confiança. Registrar
PARTIAL / BLOCKED_UPSTREAM caso o scan do lote pare pelo incidente zlib.

## Estado da reformulação

| Critério | Estado | Limite |
| --- | --- | --- |
| A01–A04 | PASS local | Preflight, negativos, keyrings e lock/build real repetidos; sem exclusividade implícita |
| A05 | PASS observado na adoção | Downloads oficiais byte a byte e hashes preservados |
| A06–A07 | PASS local/documental | Runbook de revisão, testes sem escrita e monitor real same com bytes intactos |
| A08 | Documentado | EXPECTED TOOLING LIMITATION REPRODUCED na execução anterior preservada |
| A09 | OBSERVED | Endpoint oficial HTTP 404 em 2026-09-13T03:07:44Z; não condiciona aceite futuro |
| A10 | PASS no diff local | Gates preservados; ressalva preexistente do actionlint amplo registrada na evidence |

A revisão arquitetural independente autorizou a reformulação; a nova revisão
da entrega e hosted acceptance permanecem **NOT RUN**. Resultados efetivos
da repetição dos checks estão registrados em [evidence.md](evidence.md).

## Estado corrente observado — 2026-09-14

O estado NOT RUN acima descreve a preparação histórica. A nova
[coleta](evidence.md#reconciliação-hospedada--2026-09-14) comprova o caminho
mínimo hospedado A01/A02/A03 e ordem do preflight de A04 na main:
run 34852458933/1, Melange e Apko go1-26/go1-26-dev, amd64/arm64.
**PASS observado nesse mínimo; HOSTED ACCEPTANCE = PARTIAL /
BLOCKED_UPSTREAM no lote**. O scan bloqueado permanece fail-closed.

A05–A09 conservam seus tipos de evidência local/documental/operacional e
limites, incluindo discovery. Não exigir nova prova online dos negativos
locais. A10 foi observado nos gates dos Go, sem converter isso em aceite
de todo o catálogo. Conclusão nova sujeita a revisão independente;
CORPORATE_ACCEPTANCE = EXTERNAL_PENDING.
