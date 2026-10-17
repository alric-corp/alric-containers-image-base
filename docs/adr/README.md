# Registros de decisão de arquitetura (ADR)

Decisões que não são código, mas mudam o que o pipeline pede ou aceita,
ficam registradas aqui — uma por arquivo, numeradas: uma decisão substituída
recebe um ADR novo que aponta para o anterior. A RFC-013 descreve a
plataforma; os ADRs registram cada decisão pontual com contexto, alternativas
e critério de revisão, para que a política executável que a aplica (em
`policies/`) tenha uma origem revisável.

| ADR | Decisão | Estado | Aplicada por |
| --- | --- | --- | --- |
| [0002](0002-sigstore-trust-model.md) | Modelo de confiança Sigstore e decisão de uso corporativo | PROPOSED — decisão corporativa EXTERNAL / PENDING | Documenta signing/verification existentes; não altera controles |
| [0003](0003-controles-seguranca-workflows-federados.md) | Controles de segurança da fábrica em workflows federados | Premissa de autoria definida; PROPOSED para requisitos/aceites externos | Documenta controles e responsabilidades; nenhuma mudança de gates |
| [0004](0004-v1-referencia-go126.md) | V1 de referência: Go 1.26 como primeiro fluxo completo, catálogo preservado | Proposto; motivação de prazo substituída pelo [ADR-0008](0008-modelo-operacional-lab-golden-path.md) | `policies/operations/health.json` → `execution_scope` (visibilidade); `default_batch.py`/`P0_04_BATCH` (execução, já em produção) |
| [0005](0005-stable-lifecycle-realinhamento-rfc013.md) | `stable` e lifecycle de 7 dias: realinhamento à RFC-013 (reverte a parte `STABLE = OUT_OF_SCOPE` do ADR-0004) | Aceito | `infra/ecr/main.tf` (mutability exclusion) e `infra/ecr/locals.tf` (lifecycle), image-base; `validate_ecr_repository.py` (preflight); `promote-stable.yml` (kill switch + pair binding) |
| [0008](0008-modelo-operacional-lab-golden-path.md) | Modelo operacional do LAB: golden path Go, FULL_VALIDATION fail-safe e FULL_CERTIFICATION sob demanda | Proposto | `policies/operations/health.json` → `execution_scope`; `default_batch.py`/`P0_04_BATCH`; `pr_execution_scope.py`; `catalog-certification.yml` |
| [0010](0010-release-unit-membership-canonica.md) | Fonte canônica de membership das release units (9 units: 7 pares runtime/`-dev` + 2 singletons Python) | Proposto — membership de 9 units aprovado pelo owner (D1, 2026-10-16); aceitação formal e implementação (invariantes I1–I4) pendentes | Aplicação proposta em `release_manifest.py`/`consumer_apps/model.py`; **ainda não implementada** |
| [0011](0011-release-unit-lifecycle-contract.md) | Contrato de lifecycle das release units: identidade operacional, autoridade terminal v2 e arquitetura de transição (lock global + isolamento lógico) | Proposto — arquitetura de transição aprovada pelo owner (D1 membership + D2 autoridade terminal T1, 2026-10-16); paralelismo DEV futuro OPEN; implementação não autorizada | Documental; anexo técnico em [`annexes/0011-release-unit-lifecycle-annex.md`](annexes/0011-release-unit-lifecycle-annex.md); nenhum código/workflow/policy alterado |

**ADR-0001** (`dotnet8` fora do lote padrão), **ADR-0006** (bloqueio zlib do
Java 21) e **ADR-0007** (multi-source Alpine recusado) foram removidos na
minimização final do LAB (17/09/2026): as três decisões chegaram a estado
terminal — `dotnet8` saiu do catálogo, o bloqueio zlib foi resolvido
upstream, a adoção do Alpine foi recusada — e nenhum current-state document
mais depende deles. A conclusão de cada um está consolidada em
[RFC-013](../../RFC-013-Image-Base-Completa-com-Mermaid.md) e em
[Corporate Production Readiness](../corporate-production-readiness.md)
("Não reabrir POCs encerrados"); o texto original de cada ADR permanece no
histórico Git.

Estado: **Proposto** enquanto o PR que introduz o ADR aguarda revisão de code
owner; **Aceito** com a aprovação e o merge; **Substituído** quando outro ADR
o revoga. Um ADR com `review_by` na política vencido gera alerta no job de
saúde até ser revisado (renovado com nova data ou revogado).

Para um ADR que dependa de **decisão externa**, como o ADR-0002, aprovação e
merge documental não concedem aceite corporativo. Seu estado PROPOSED
permanece até registro explícito do owner externo indicado no próprio ADR.

Convenção: um arquivo `docs/adr/NNNN-titulo-em-minusculas.md` (quatro dígitos,
kebab-case, direto neste diretório), cuja primeira linha é o título
`# ADR-NNNN — …` com o mesmo número, seguido de contexto, decisão,
consequências, alternativas rejeitadas e critério de revisão, e uma linha na
tabela acima. Uma política que exige ADR (hoje `exceptions` em
`policies/operations/health.json`) referencia-o por esse caminho relativo; o
lint [`default_batch.py`](../../scripts/pipeline/catalog/default_batch.py)
recusa qualquer outra coisa — caminho absoluto, `..`, arquivo fora deste
diretório, link simbólico em qualquer componente do caminho (`docs`,
`docs/adr` ou o arquivo), arquivo que não resolva fisicamente para dentro
deste diretório na raiz canônica do repositório, ou arquivo sem esse título.

Decisões previstas pelo roadmap consolidado e ainda sem ADR: destino e SLA
de alerta (Containers Products). Requisitos de segurança/scanner da fábrica
federada permanecem a confirmar no ADR-0003.
A aceitação corporativa do Sigstore público permanece pendente no ADR-0002.