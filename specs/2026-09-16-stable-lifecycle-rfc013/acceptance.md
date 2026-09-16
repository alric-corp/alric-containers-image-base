# ACCEPTANCE — 2026-09-16: `stable` + lifecycle de 7 dias

| ID | Requisito | Critério observável | Comando ou inspeção |
| --- | --- | --- | --- |
| A01 | R3 | Preflight aceita só `IMMUTABLE_WITH_EXCLUSION` + `[{filterType:WILDCARD, filter:stable}]`; rejeita MUTABLE, IMMUTABLE puro, `latest`, `*`, `stable`+outro filtro | `python3 -B -m unittest tests.unit.pipeline.release.test_validate_ecr_repository` |
| A02 | R1 | `main.tf` declara a exclusion filter exata nos dois módulos | `terraform validate`; leitura de `main.tf` |
| A03 | R6 | Lifecycle: 2 regras, prioridade 1 protege `stable` (nunca expira), prioridade 2 expira `*` >7 dias | `python3 -B -m unittest tests.test_lifecycle_policy` (registry) |
| A04 | R5 | Promoção runtime/dev falha se run_id/attempt não coincidirem | `python3 -B -m unittest tests.unit.pipeline.release.test_verify_promotion_pair(s)` |
| A05 | — | Documentação reflete o estado real, sem alegar aceite corporativo | `check_ai_context.py`; leitura do ADR-0005 |
| A06 | R7 | Reconciliação one-time sem permissão permanente nova | `aws iam list-attached-role-policies` antes/depois — mesmo conjunto |
| A07 | R4 | Build normal nunca escreve `stable` | `promote-stable` job = `skipped` no run de build normal |
| A08 | R5 | Promoção real escreve `stable` só via `promote-stable.yml`, sem rebuild | Evidência hospedada do run de promoção |
| A09 | — | Read-back confirma `stable` == candidato para os dois | `promotion-evidence.json` de cada leg |
| A10 | — | Recovery move `stable` para digest histórico sem rebuild | Evidência hospedada do run de `recover-stable.yml` |
| A11 | R8 | Preview: `stable` NOT_SELECTED_FOR_EXPIRATION | `aws ecr get-lifecycle-policy-preview` |
| A12 | R8 | Preview: builds >7d SELECTED, <=7d NOT_SELECTED | idem |
| A13 | R2 | `terraform plan` final = `No changes` | Run hospedado de `terraform-apply.yml` (job `plan`) |

## Negativos e limites

- **A01 negativo:** os 5 exemplos exatos da seção 4 do pedido (MUTABLE,
  IMMUTABLE puro, sem `stable`, com `latest`, `stable`+outra exclusão) têm
  teste dedicado, um a um — não um teste genérico "algo errado falha".
- **A06 limite:** a reconciliação depende de execução manual, reviewved,
  fora do CI normal (attach → plan → apply → verify → detach). Este
  documento registra o procedimento e, em `evidence.md`, o resultado real;
  não é um controle automatizado recorrente.
- **A11 crítico:** se o preview selecionar `stable` para expiração, a
  aplicação da lifecycle **para** — não há correção automática nem
  contorno; volta para investigação manual do porquê (ex.: erro na regra 1).
- **A13 limite:** "no changes" depende de nenhuma execução concorrente
  alterar o estado dos dois repositórios entre a reconciliação e esta
  verificação final — não é uma garantia perene, é uma confirmação pontual.

## Aceite externo

Nenhum aceite corporativo é reivindicado por esta spec. Sandbox
`alric-corp` + conta AWS pessoal, como em toda a série P0-04. A revisão dos
PRs segue o fluxo normal de CODEOWNERS de cada repositório.
