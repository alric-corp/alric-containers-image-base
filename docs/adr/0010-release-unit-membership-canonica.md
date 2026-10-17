# ADR-0010 — Fonte canônica de membership das release units

| Informação | Valor |
| --- | --- |
| Estado | **Proposto** — o **membership de 9 units foi APROVADO pelo owner (D1, 2026-10-16)** como decisão documental; o ADR permanece Proposto porque a aceitação formal ainda requer a linha na tabela de `docs/adr/README.md` e o PR (ação de revisão humana), e as invariantes I1–I4 são critério de implementação ainda não cumprido |
| Data | 2026-10-16 |
| Base auditada | `develop` em `3ac900b4db4d0e3fe7e60945c3b828d6dd7532a4` |
| Owners | Containers Products (`@alric-corp/github_xj7_maintainer`) + Infra (`alric-containers-image-base/infra`) |
| Relação | Complementa o [ADR-0008](0008-modelo-operacional-lab-golden-path.md) e o [ADR-0005](0005-stable-lifecycle-realinhamento-rfc013.md); não substitui nenhum ADR |
| Aplicação proposta | `scripts/pipeline/release/release_manifest.py` (`release_units()`), `scripts/pipeline/consumer_apps/model.py` (`SCENARIOS`/`CATALOG`) — **ainda não implementada** |

> **Natureza deste documento.** Este ADR registra uma **decisão de arquitetura
> proposta**. As seções "Decisão" e "Invariantes-alvo" descrevem o estado que
> a arquitetura pretende atingir, **não** o que a implementação em `develop`
> garante hoje. O que o código atual efetivamente garante está isolado na
> seção "Estado atual comprovado (develop @ 3ac900b)" e é a única parte deste
> ADR sustentada por evidência de implementação. Nenhuma linha abaixo deve ser
> lida como invariante já aplicada salvo onde essa seção o afirma
> explicitamente.

## Contexto

O catálogo de frameworks (`frameworks/*.yaml`) define os artifacts que a
fábrica conhece. Dois conceitos distintos consomem esse catálogo e **hoje não
têm uma única fonte de membership**:

1. **Release units** — o agrupamento runtime/`-dev` que o lifecycle usa para
   decidir o que é promovido junto (um par incompleto não pode deixar meia
   escrita de `stable`).
2. **Consumer scenarios** — os cenários de teste de aplicações consumidoras,
   que carregam metadados próprios (família, versão esperada) e governam as
   execuções de consumers por arquitetura.

### O acoplamento observado

Na base auditada, `release_manifest.release_units()` deriva seus grupos da
tupla `SCENARIOS` definida em `consumer_apps/model.py`:

- `scripts/pipeline/release/release_manifest.py:10` —
  `from scripts.pipeline.consumer_apps.model import CATALOG, SCENARIOS`
- `scripts/pipeline/release/release_manifest.py:38-47` — `release_units()`
  itera `SCENARIOS` e monta os pares a partir de `scenario['framework']` +
  `scenario['dev_framework']`.

Ou seja: a definição do que é uma **release unit** (um conceito de
*publicação/promoção*) está estruturalmente contida no modelo de **testes de
consumers** (um conceito de *validação de aplicação*). O próprio
`consumer_apps/model.py:1` reconhece a tensão no docstring —
`"""Versioned consumer scenarios; these do not define release promotion units."""`
— mas a dependência de importação continua existindo na direção
`release_manifest → consumer_apps`.

### Por que isto é uma decisão de arquitetura, não um bug

O comportamento atual está **correto e testado**: a derivação produz as 9
release units esperadas (7 pares runtime/`-dev` + 2 singletons Python) e o
lifecycle as consome sem divergência conhecida. O problema não é um defeito de
runtime; é um **acoplamento de domínio** que:

- faz uma mudança no modelo de testes de consumers (ex.: adicionar um cenário,
  mudar um `dev_framework`) alterar silenciosamente o que a fábrica considera
  uma release unit;
- impede que o domínio de release seja raciocinado, versionado e testado
  independentemente do domínio de testes de aplicação;
- deixa a cobertura/disjunção das units como propriedade emergente de
  `SCENARIOS`, não como um contrato verificado explicitamente.

## Decisão

> Estado-alvo. Ver nota de natureza no topo.

Estabelecer uma **fonte canônica única de membership das release units**,
separada do modelo de consumers, com a dependência invertida para
`consumer_apps → <fonte canônica>` e `release_manifest → <fonte canônica>`.

1. **Um módulo de domínio puro** define as release units do catálogo: para
   cada unit, exatamente um runtime e no máximo um `-dev` companion, com ID
   igual ao runtime e ordem canônica runtime-antes-de-dev. Sem I/O, sem estado
   operacional, sem dependência de consumers, release/lifecycle ou workflows.
2. **`release_manifest.release_units()` passa a adapter** sobre essa fonte,
   preservando: assinatura de entrada, mensagens de erro de entrada, ordem de
   saída, **schema v1 do manifesto**, as mesmas keys, `units`, tags e checksum.
   Nenhum objeto de domínio novo é persistido no manifesto.
3. **`consumer_apps/model.py` deriva `CATALOG` e o membership/ordem** da fonte
   canônica; família e versão esperada permanecem metadados do consumer. As
   execuções de consumers e seus valores públicos permanecem idênticos.
4. **Cobertura exata e disjunta** do catálogo pelas units passa a ser um
   contrato verificado explicitamente, não uma propriedade emergente.

### Invariantes-alvo (a serem garantidas pela implementação, não hoje)

- I1. Toda mudança de catálogo exige atualizar a definição canônica revisada e
  demonstrar cobertura exata; uma receita nova não vira unit silenciosamente.
- I2. O manifesto permanece byte-equivalente em schema v1 para toda seleção de
  catálogo (equivalência de adapter demonstrável por teste).
- I3. A dependência é acíclica: o domínio de units não importa consumers,
  release, lifecycle nem workflows.
- I4. As decomposições com outra finalidade — fixtures de runtime/trust e os
  grupos de promoção legados derivados de `publication_contract()` — **não**
  são redefinidas por esta decisão e continuam coexistindo.

Nenhuma dessas invariantes é afirmada como existente na base atual; são o
critério de aceite da implementação proposta.

## Estado atual comprovado (develop @ 3ac900b)

Esta é a única seção sustentada por evidência de implementação. O que o código
**hoje** garante:

- **A fonte de membership é `SCENARIOS`**, não um domínio dedicado
  (`release_manifest.py:10,38-47`). Um módulo `catalog/release_units.py` **não
  existe** em `develop`.
- **A atomicidade de autorização por unit no batch de promoção já existe** e é
  testada: `scripts/pipeline/release/promotion_batch.py` resolve units
  (`promotion_units()`), aplica uma barreira pré-escrita global
  (`prewrite_barrier_complete`) e falha uma unit sem derrubar units não
  relacionadas (`fail()` é escopado à unit). **Isto já é verdade hoje** e não
  depende desta decisão. **Precisão operacional (fato):** `promotion_batch.py`
  **não é invocado por nenhum workflow** — os workflows de promoção
  (`promote-stable.yml`, `dev-stable.yml`, `recover-stable.yml`) chamam
  `scripts.pipeline.release.lifecycle`, cujo `publish_states()` opera sobre o
  **manifesto inteiro sob um lock global por destino**. A atomicidade por unit do
  `promotion_batch` é uma ferramenta auxiliar existente mas **não demonstra**
  isolamento no caminho operacional atual.
- **O binding runtime/`-dev` por `r<run>-a<attempt>`** é verificado antes de
  qualquer escrita de `stable` (`verify_promotion_pair.py:verify_pair`) e
  repetido após as escritas/read-backs (`verify_promotion_pairs.py`). Também
  já é verdade hoje.
- **A imutabilidade dos registros de release** é garantida server-side por
  `--if-none-match` no S3 (`release_store.py:put(..., immutable=True)`), com
  reconciliação de conteúdo idêntico em `PreconditionFailed`. Já é verdade hoje.
- **Escrita de `stable` fail-closed**: holds persistidos antes de qualquer
  `put-image`/`imagetools create`, read-back obrigatório, `promoted=true`
  somente com digest observado == candidato (`lifecycle.py:publish_states`,
  `promotion_batch.py:record_outcome`). Já é verdade hoje.

O que **não** é garantido hoje e esta decisão pretende estabelecer: a
separação de domínio (I3), o contrato explícito de cobertura/disjunção (I1) e a
prova de equivalência de adapter (I2). O acoplamento
`release_manifest → consumer_apps` permanece literal na base atual.

## Consequências

- Membership de lifecycle deixa de ser definido incidentalmente por consumers.
- Mudanças de catálogo passam a exigir atualização de uma definição revisada
  com cobertura exata demonstrada.
- As decomposições de runtime/trust (fixtures) e de promoção legada
  (`publication_contract()`) continuam existindo explicitamente e sem
  alteração — esta decisão não as unifica.
- O acoplamento operacional atual permanece até a implementação; este ADR
  **não** habilita HOM, não remove soak, não altera gates, policies, infra,
  trust, concorrência ou o golden path GO_PAIR.

## Alternativas rejeitadas

- **Manter o membership derivado de `SCENARIOS`**: rejeitada — mantém o modelo
  de release dentro do modelo de testes e permite divergência silenciosa a
  cada mudança de cenário de consumer.
- **Duas implementações de membership (uma em consumers, outra em release)**:
  rejeitada — permite divergência entre o que é testado e o que é promovido,
  exatamente o risco que o docstring de `model.py` já sinaliza.
- **Descobrir units por varredura de filesystem no domínio**: rejeitada —
  mistura I/O e estado operacional no domínio e abre caminho para dependência
  circular; a descoberta de arquivos deve ficar fora do domínio puro.
- **Introduzir, nesta decisão, receipts/schema v2/isolamento de publicação por
  unit**: rejeitada para este ADR — ultrapassa a canonicalização de membership,
  impede validar a equivalência v1 e transforma uma refatoração de domínio em
  uma migração operacional. Essas evoluções, se desejadas, pertencem a ADRs
  próprios com seus próprios aceites (ver "Questões em aberto").

## Questões em aberto

1. **Numeração.** Existe trabalho experimental local (fora de `develop`) que
   usou o número **0009** para um ADR relacionado. Como esse trabalho não é
   fonte de verdade e não foi merged, este ADR reserva **0010** para evitar
   colisão de identidade. Se o 0009 experimental nunca for promovido, a
   numeração pode ser reconciliada em revisão — decisão de owner.
2. **Escopo de isolamento futuro.** Se a organização quiser evoluir para
   publicação/stable/promoção/recovery/health **por unit** (além da
   atomicidade de autorização que já existe no batch), isso exige ADRs
   dedicados por fase, cada um com aceite próprio. Este ADR deliberadamente
   não decide esse roadmap.
3. **Node como par.** A derivação atual trata `nodejs22`/`nodejs24` como pares
   runtime/`-dev`. A definição canônica deve preservar exatamente o membership
   atual (7 pares + 2 singletons Python) — a confirmar contra
   `frameworks/*.yaml` na implementação, não apenas repetir a lista do desenho.
   **Reconciliação 9 × 11 (fato, verificado offline).** As funções **não**
   convergem — produzem resultados diferentes por desenho, e ambos são corretos:
   - `release_manifest.release_units()` = **9 unidades canônicas**: 7 pares
     runtime/`-dev` (incl. `nodejs22`/`nodejs24` como pares, via metadados de
     `SCENARIOS`) + 2 singletons Python. Este é o **membership canônico de
     release**.
   - `promotion_batch.promotion_units()` = **11 agrupamentos auxiliares**: 5 pares
     compilados (`dotnet10`, `go1-25`, `go1-26`, `java21`, `java25`), **4
     singletons Node** (`nodejs22`, `nodejs22-dev`, `nodejs24`, `nodejs24-dev`) e
     2 singletons Python. A divergência vem de `runtime_images.publication_contract()`,
     que classifica **Node como interpretado** e retorna `runtime_framework=framework`
     **sem** `dev_framework`; o dedup de `promotion_units()` é por esse `runtime`, de
     modo que cada artifact Node vira um agrupamento próprio.
   - `consumer_apps.model.SCENARIOS` = 9 cenários; `frameworks/*.yaml` = 16 artifacts.

   **Esses 11 são agrupamentos auxiliares de testes/publicação, não membership de
   release.** A classificação interpreted/compiled de `publication_contract()`
   resolve contratos de runtime e **não** redefine release units. O membership
   canônico permanece **9** (diretriz do owner: 7 pares incl. Node 22/24 + 2
   Python), e a confirmação formal do owner continua **pendente**.
   **APROVADO (D1, owner 2026-10-16):** membership canônico = **9 units** (7 pares
   runtime/`-dev` incl. Node 22/24 + 2 singletons Python); os **11 agrupamentos
   auxiliares** de `promotion_batch.py` permanecem independentes e **não** definem
   membership de release. A confirmação contra `frameworks/*.yaml` permanece como
   critério de implementação (não reaberto por esta aprovação documental).
4. **Linha na tabela do README.** `docs/adr/README.md` não foi alterado por
   esta entrega (restrição da tarefa). Adicionar a linha de ADR-0010 é ação de
   revisão humana no PR que aceitar este ADR.

## Critério de revisão

Aceitar somente com: separação de domínio sem dependência circular (I3),
contrato explícito de cobertura 16 artifacts / 9 units / 7 pares / 2 singletons
(I1), prova de equivalência de manifesto v1 para toda seleção de catálogo (I2),
GO_PAIR e FULL preservados, e as decomposições de runtime/trust e promoção
legada intactas (I4). Revisar diante de novos tipos de artifact, mudança de
membership, ou antes de qualquer fase que introduza mutação por unit.

## Evidência

- `scripts/pipeline/release/release_manifest.py:10,38-47` — acoplamento atual.
- `scripts/pipeline/consumer_apps/model.py:1,6-30` — docstring que nega o papel
  de definição de release e a tupla `SCENARIOS` que hoje o define de fato.
- `scripts/pipeline/release/promotion_batch.py` — atomicidade de autorização
  por unit já existente (barreira pré-escrita, falha escopada à unit).
- `scripts/pipeline/release/verify_promotion_pair.py` /
  `verify_promotion_pairs.py` — binding runtime/`-dev` pré e pós-escrita.
- `scripts/pipeline/release/release_store.py` — imutabilidade server-side via
  `--if-none-match`.
- `scripts/pipeline/release/lifecycle.py:publish_states` — escrita de `stable`
  fail-closed com holds e read-back.
