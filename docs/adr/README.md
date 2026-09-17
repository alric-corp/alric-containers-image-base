# Registros de decisão de arquitetura (ADR)

Decisões que não são código, mas mudam o que o pipeline pede ou aceita,
ficam registradas aqui — uma por arquivo, numeradas, nunca reescritas: uma
decisão substituída recebe um ADR novo que aponta para o anterior. A RFC-013
descreve a plataforma; os ADRs registram cada decisão pontual com contexto,
alternativas e critério de revisão, para que a política executável que a
aplica (em `policies/`) tenha uma origem revisável.

| ADR | Decisão | Estado | Aplicada por |
| --- | --- | --- | --- |
| [0001](0001-dotnet8-fora-do-lote-padrao.md) | `dotnet8` fora do lote padrão, sem sair do catálogo (12/09/2026); adendos registram a adoção recusada (ADR-0007) e a remoção do catálogo em 17/09/2026 | Proposto | `policies/operations/health.json` → `exceptions` (vazio); lint `scripts/pipeline/catalog/default_batch.py` |
| [0002](0002-sigstore-trust-model.md) | Modelo de confiança Sigstore e decisão de uso corporativo | PROPOSED — decisão corporativa EXTERNAL / PENDING | Documenta signing/verification existentes; não altera controles |
| [0003](0003-controles-seguranca-workflows-federados.md) | Controles de segurança da fábrica em workflows federados | Premissa de autoria definida; PROPOSED para requisitos/aceites externos | Documenta controles e responsabilidades; nenhuma mudança de gates |
| [0004](0004-v1-referencia-go126.md) | V1 de referência: Go 1.26 como primeiro fluxo completo, catálogo preservado | Proposto | `policies/operations/health.json` → `execution_scope` (visibilidade); `default_batch.py`/`P0_04_BATCH` (execução, já em produção) |
| [0005](0005-stable-lifecycle-realinhamento-rfc013.md) | `stable` e lifecycle de 7 dias: realinhamento à RFC-013 (reverte a parte `STABLE = OUT_OF_SCOPE` do ADR-0004) | Proposto | `alric-containers-registry/main.tf` (mutability exclusion + lifecycle); `validate_ecr_repository.py` (preflight); `promote-stable.yml` (kill switch + pair binding) |
| [0006](0006-java21-zlib-blocker-remediation-options.md) | Java 21: opções de remediação para o bloqueio zlib (`CVE-2026-85091`) | RESOLVED — superseded pelo fix upstream do Wolfi (Addendum 17/09/2026) | Nenhuma — o pacote próprio via Melange nunca foi construído; o Wolfi publicou a correção antes da decisão do Tech Lead |
| [0007](0007-multi-source-alpine-recusado.md) | Multi-source com Alpine v3.24 para `dotnet8`: tecnicamente aprovado, adoção recusada; `dotnet8` removido do catálogo em 17/09/2026 | Proposto | Decisão negativa sobre multi-source (nenhuma mudança direta); a remoção do catálogo é aplicada em PR próprio (ver ADR-0001, adendo) |

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