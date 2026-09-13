# Registros de decisão de arquitetura (ADR)

Decisões que não são código, mas mudam o que o pipeline pede ou aceita,
ficam registradas aqui — uma por arquivo, numeradas, nunca reescritas: uma
decisão substituída recebe um ADR novo que aponta para o anterior. A RFC-013
descreve a plataforma; os ADRs registram cada decisão pontual com contexto,
alternativas e critério de revisão, para que a política executável que a
aplica (em `policies/`) tenha uma origem revisável.

| ADR | Decisão | Estado | Aplicada por |
| --- | --- | --- | --- |
| [0001](0001-dotnet8-fora-do-lote-padrao.md) | `dotnet8` fora do lote padrão, sem sair do catálogo | Proposto | `policies/operations/health.json` → `exceptions`; lint `scripts/pipeline/catalog/default_batch.py` |
| [0002](0002-sigstore-trust-model.md) | Modelo de confiança Sigstore e decisão de uso corporativo | PROPOSED — decisão corporativa EXTERNAL / PENDING | Documenta signing/verification existentes; não altera controles |

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

Decisões previstas pelo roadmap consolidado e ainda sem ADR: papel do scanner
corporativo (AppSec), destino e SLA de alerta (Containers Products).
A aceitação corporativa do Sigstore público permanece pendente no ADR-0002.
