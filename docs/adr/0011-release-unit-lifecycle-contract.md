# ADR-0011 — Contrato de lifecycle das release units

| Informação | Valor |
| --- | --- |
| Estado | **Proposto** — a arquitetura de transição foi **aprovada pelo owner (D1 membership + D2 autoridade terminal, 2026-10-16)** como decisão documental; o ADR permanece Proposto porque a **aceitação formal** exige a linha na tabela de `docs/adr/README.md` e o merge do PR (ação de code owner). A aprovação D1/D2 é distinta da aceitação formal deste ADR e da implementação futura (`IMPLEMENTATION_AUTHORIZED: NO`) |
| Data | 2026-10-16 |
| Base auditada | `develop` em `3ac900b4db4d0e3fe7e60945c3b828d6dd7532a4` |
| Relação | Complementa [ADR-0010](0010-release-unit-membership-canonica.md) (membership canônico); não substitui nenhum ADR |
| Anexo técnico | [`docs/adr/annexes/0011-release-unit-lifecycle-annex.md`](annexes/0011-release-unit-lifecycle-annex.md) — matrizes, estados, layouts de persistência, aceite offline, migração |

> **Natureza deste documento.** Registra uma **decisão de arquitetura proposta**.
> As seções **Contexto — estado atual comprovado** são a única parte sustentada
> por evidência de implementação em `develop @ 3ac900b`. As seções **Decisão**,
> **Invariantes** e o anexo descrevem o estado-alvo e **não** o que o código
> garante hoje. Nenhuma linha deve ser lida como invariante já aplicada salvo
> onde o estado comprovado o afirma. `IMPLEMENTATION_AUTHORIZED: NO`.

---

## 1. Contexto — estado atual comprovado (`develop @ 3ac900b`)

Estes são os fatos verificados diretamente no código e nos workflows. Tudo o
mais neste ADR é alvo proposto.

**F1 — O caminho operacional hospedado é `lifecycle.py`, não `promotion_batch.py`.**
Os workflows de promoção invocam exclusivamente `scripts.pipeline.release.lifecycle`:
`promote-stable.yml` → `promote-hom`; `dev-stable.yml` → `approve-dev` e
`promote-dev`; `recover-stable.yml` → `recover-hom`. **Nenhum workflow invoca
`promotion_batch.py`** (verificado por varredura de `.github/workflows/`).

**F2 — `promotion_batch.py` existe mas não é invocado.** Esse script implementa
isolamento de falha genuíno por unit (`fail()` escopa a falha à unit atômica; a
barreira pré-escrita global e units não relacionadas prosseguem). Porém é uma
**ferramenta auxiliar não invocada pelo caminho atual**. Seu isolamento lógico
**não demonstra** isolamento no caminho de `lifecycle.py`.

**F3 — O caminho invocado opera sobre o manifesto inteiro, sob um lock global.**
`lifecycle.publish_states()` itera `manifest['images']` (todos os frameworks da
release) e grava holds, tags `stable` e read-backs para o conjunto inteiro. O
docstring de `lifecycle.py` declara: *"One destination-wide Actions concurrency
lock surrounds each invocation."* **Não há fronteira de falha por unit no caminho
operacional atual.** A granularidade de estado por framework (`state/<fw>.json`)
é por imagem, mas a operação de promoção é all-or-nothing sobre o manifesto.

**F4 — Autoridade terminal atual é o recibo de nível manifesto.** A verdade de
uma operação é `events/r<GITHUB_RUN_ID>-a<GITHUB_RUN_ATTEMPT>/completed.json`
(`status: PASS`), imutável; `failed.json` registra a falha; `promoted/<rid>.json`
é escrito **somente em HOM, não-recovery**, como recibo agregado da release
inteira. O `attempt` **faz parte** da chave de evento (`r<run>-a<attempt>`). **Não
existe `outcome.json` nem layout `releases/<rid>/units/<unit_id>/ops/<op_id>/` no
código** — são construções propostas, não fato.

**F5 — Imutabilidade recusa conteúdo divergente.** `release_store.Store.put(key,
doc, immutable=True)` usa `--if-none-match '*'` e, em `PreconditionFailed`,
**re-lê e exige igualdade** (`require(self.get(key)==document, ...)`). Uma chave
imutável nunca aceita dois conteúdos diferentes. A imutabilidade server-side vale
sob `releases/*`, `promoted/*`, `events/*` (`infra/lifecycle/main.tf`,
`ImmutableReleaseRecords`, Deny prefix-scoped).

**F6 — Membership canônico = 9 release units; agrupamentos auxiliares = 11
(verificado offline).** As duas funções de agrupamento **não** convergem, por
desenho:
- `release_manifest.release_units()` = **9 unidades canônicas** (7 pares
  runtime/`-dev` incl. `nodejs22`/`nodejs24` + 2 singletons Python), derivadas de
  `SCENARIOS`. **É o membership de release.**
- `promotion_batch.promotion_units()` = **11 agrupamentos auxiliares**: 5 pares
  compilados (`dotnet10`, `go1-25`, `go1-26`, `java21`, `java25`), **4 singletons
  Node** (`nodejs22`, `nodejs22-dev`, `nodejs24`, `nodejs24-dev`) e 2 singletons
  Python. Causa (fato): `runtime_images.publication_contract()` classifica **Node
  como interpretado** → `runtime_framework=framework`, **sem** `dev_framework`; o
  dedup de `promotion_units()` é por esse runtime, então cada artifact Node é um
  agrupamento próprio.
- `consumer_apps.model.SCENARIOS` = 9 cenários; `frameworks/*.yaml` = **16
  artifacts** (14 pareados + 2 singletons).

Os 11 são **agrupamentos auxiliares de testes/publicação**, não membership de
release (§2, ADR-0010). O membership canônico permanece **9**; confirmação do
owner **pendente**.

**F7 — Concorrência GitHub.** `stable` usa `cancel-in-progress:false`; por grupo
de concorrência o Actions mantém um em execução + no máximo um pendente, sem FIFO,
substituindo o pendente. DEV e HOM usam **lock global** por destino hoje.

---

## 2. Decisão (alvo proposto)

**D-MEMBERSHIP.** Preservar **9 release units canônicas**: sete pares
runtime/`-dev` (dotnet10, go1-25, go1-26, java21, java25, **nodejs22**,
**nodejs24**) e **dois singletons Python** (python3-13, python3-14). A
classificação interpreted/compiled de `publication_contract()` **não** redefine
membership de release; os contratos de runtime permanecem responsabilidade
independente. **APROVADO pelo owner (D1, 2026-10-16):** membership canônico =
9 release units; os 11 agrupamentos auxiliares de `promotion_batch.py`
permanecem independentes e **não** definem membership de release. Ver ADR-0010.

**D-IDENTITY.** Três identidades distintas e não confundíveis:
- `release_id` = identidade de build = `r<RUN_ID>-a<ATTEMPT>` (fato, `RELEASE_ID`).
- `unit_id` = identidade canônica da unit (= runtime da unit).
- `op_id` = identidade da operação concreta, serializada como
  **`op-<action>-r<run>-a<attempt>`**, incluindo run operacional, attempt e action.
  Validação sintática obrigatória; o identificador **não** pode ser interpretável
  como `release_id` (`r<run>-a<attempt>`) nem como build tag
  (`DDMMAA-HHMM-r<run>-a<attempt>`) — o prefixo `op-<action>-` garante disjunção.
- **Rerun do GitHub com novo attempt = nova identidade operacional.** **Recovery =
  operação nova e explícita** (nova `action`, novo `op_id`). Nenhuma retomada
  automática contorna holds ou autorizações existentes.
- **As chaves v1 existentes são integralmente preservadas** (§5, anexo).

**D-TERMINAL.** **APROVADO pelo owner (D2 — T1 ajustada, 2026-10-16):** um
**único recibo terminal canônico create-once por unidade e operação v2**,
`status ∈ {PROMOTED, FAILED}`, como autoridade terminal v2. Eventos
`completed`/`failed` são **evidência derivada**; **não** há segundo árbitro
independente. O **recibo agregado histórico v1 permanece autoritativo para
recovery v1**; o **agregado v2 é all-or-nothing**, sujeito à comprovação completa
da release. Contrato detalhado e ordem de falha parcial no anexo A.3. Um
**rerun nativo do GitHub (attempt +1)** é um **`op_id` novo** (o attempt faz parte
do `op_id`): ao observar uma operação anterior terminada em `FAILED`, **não** a
reabre nem grava sucesso — segue o **caminho explícito de recovery** (operação
nova, novo `op_id`). Uma reescrita divergente da **mesma** operação (retry interno
ou replay do mesmo `op_id`) é recusada por create-once. Ordenação e autoridade de
operações históricas para recovery individual definidas no anexo.

**D-PERSISTENCE.** Chaves imutáveis v1 preservadas; novos caminhos por
unidade/operação sob um segmento `/units/<unit_id>/` que o schema v1 nunca emite
(sem colisão); create-once aplicável apenas sob `releases/*`, `promoted/*`,
`events/*`; distinção explícita entre **retry interno da mesma tentativa** (mesmo
`op_id` = mesmo run+attempt, só conteúdo idêntico) e **nova operação** (rerun com
novo attempt, promoção ou recovery → novo `op_id`); persistência determinística de
evidências; reconciliação de registros existentes por igualdade de conteúdo;
tratamento de falha parcial entre resultado terminal e evidências derivadas
(anexo A.1/A.2). **`Store.put(immutable=True)` não aceita documentos divergentes
(F5)** — nenhuma reconciliação pode presumir o contrário.

**D-LEASE (transição).** Preservar a decisão de transição: **DEV com lock global,
HOM com lock global, isolamento lógico por unidade, paralelismo DEV futuro não
autorizado.** O mecanismo futuro por unit permanece **OPEN** (§3, anexo A.4).

---

## 3. Invariantes (alvo, salvo onde marcado fato)

- **INV1** Membership: cobertura exata e disjunta do catálogo (16 artifacts) pelas
  9 units (ADR-0010).
- **INV2** Isolamento de falha por unit **no caminho operacional** é **alvo**, não
  fato (F2/F3): hoje `publish_states` é all-or-nothing sobre o manifesto.
- **INV3** Gates globais aprovados antes de qualquer escrita (fato — trust+scan
  antes do primeiro `put-image`).
- **INV4** Compatibilidade v1 fail-closed: manifesto/recovery v1 sem sidecar
  continuam lidos; um sidecar v2 ausente/incompleto/inválido **bloqueia**, nunca
  degrada silenciosamente (alvo).
- **INV5** High-watermark monotônico: job obsoleto não regride `stable` (fato —
  `choose()`/`ordering()`).
- **INV6** HOM permanece global em todas as fases.
- **INV7** Não-colisão: toda chave imutável por unit contém `op_id` sob
  `/units/<unit_id>/`; nenhuma coincide com chave v1. Autoridade terminal única
  por `op_id` (D-TERMINAL). Verificável offline.
- **INV8** Coordenação futura por unit (lease com identidade de owner, geração
  monotônica, prazo, renovação condicional, fencing na fronteira de mutação)
  permanece **OPEN** enquanto não houver mecanismo efetivo escolhido e
  demonstrável (§anexo A.4). **Não** se declara resolvida por "embutir generation
  no JSON de estado + If-Match": CAS no objeto de estado valida o ETag daquele
  objeto, não a posse da geração do lease (objeto distinto).

Estados e transições completos: anexo A.1.

---

## 4. Atomicidade lógica × tags ECR (limite honesto)

ECR `put-image` **não** oferece CAS, `If-Match` ou fencing token (fato). Logo:
- A escrita de estado S3 (`state/<fw>.json`) **pode** ser protegida por um
  mecanismo de fencing atômico **a definir** (geração ligada à própria escrita) —
  **OPEN**.
- A escrita de tag ECR **em voo não é fencível** na própria fronteira. A única
  exclusão mútua efetiva sobre a escrita ECR é **serialização** (lock global DEV
  atual, ou executor exclusivo por unit). Enquanto não houver mecanismo
  demonstrável, `ECR_MUTATION_SAFETY` permanece **OPEN** e o lock global é o
  fallback operacional (anexo A.4, cenário offline 19).

---

## 5. Compatibilidade e migração (sem autorizar execução)

Chaves v1 (`releases/<rid>/{manifest,candidate}.json`, `state/<framework>.json`,
`events/r<run>-a<attempt>/{started,completed,failed}.json`, `promoted/<rid>.json`)
**preservadas sem alteração**. Releases históricas não são reescritas. A migração
(anexo A.5) é faseada e **preserva o lock global DEV** durante o isolamento
lógico; a remoção do global depende de aprovação futura do mecanismo de
serialização ECR e proteção S3 efetiva. Nenhuma fase autoriza implementação,
dispatch, build ou comando AWS. Golden path Go 1.26 preservado; G07 inalterado.

---

## 6. Consequências

- O ADR separa o que o caminho invocado garante hoje (manifesto inteiro, lock
  global, recibo agregado de nível manifesto) do que a arquitetura por unit
  pretende atingir.
- Corrige a premissa anterior de que `promotion_batch.py` demonstrava isolamento
  hospedado: ele não é invocado (F1/F2).
- A autoridade terminal v2 é o recibo terminal canônico único por unidade/operação
  (`RECEIPT_AUTHORITY: APPROVED` — D2/T1 ajustada, owner 2026-10-16); agregado v1
  autoritativo para recovery v1, agregado v2 all-or-nothing. Anexo A.3.
- O mecanismo de concorrência futuro por unit permanece não decidido
  (`FUTURE_PARALLELISM: OPEN`); a transição serializada é a única arquitetura
  pronta para aceite documental.

---

## 7. Alternativas

- **Membership derivado de `SCENARIOS` (atual)** × **fonte canônica dedicada**
  (ADR-0010). Trade-offs em ADR-0010.
- **Concorrência DEV:** A (lock global + isolamento lógico, atual) × B (lock por
  `unit_id` via `concurrency.group`) × C (executor exclusivo por unit). Garantias,
  limitações e pré-condições no anexo A.4. B não satisfaz exclusão sobre a escrita
  ECR em voo; C introduz infraestrutura nova e exige decisão do owner.
- **Autoridade terminal:** recibo individual canônico único × recibo + registro
  de resultado separado. Anexo A.3.

---

## 8. Critério de revisão

Aceitar a **arquitetura de transição** (lock global + isolamento lógico,
membership 9) somente com: membership confirmado pelo owner (ADR-0010); identidade
`op-<action>-r<run>-a<attempt>` validada sintaticamente e disjunta de
`release_id`/build tag; chaves v1 preservadas (F5); matriz de aceite offline
integralmente especificada (anexo A.2). As **evoluções futuras** (fencing S3
atômico, serialização ECR por unit, autoridade terminal se alterar a decisão do
owner) permanecem `OPEN` e **não** são pré-requisito para o aceite documental da
transição. Revisar diante de novo tipo de artifact, mudança de membership, ou
antes de qualquer fase que introduza mutação por unit.

---

## Decisões do owner

**Aprovadas (2026-10-16, documentais):**
1. **CANONICAL_MEMBERSHIP: APPROVED (D1)** — 9 release units canônicas (7 pares
   incl. Node 22/24 + 2 Python); os 11 agrupamentos auxiliares de
   `promotion_batch.py` são independentes e não definem membership.
2. **RECEIPT_AUTHORITY: APPROVED (D2 — T1 ajustada)** — recibo terminal canônico
   único create-once por unidade/operação v2 (`PROMOTED`/`FAILED`); `completed`/
   `failed` derivados; agregado v1 autoritativo p/ recovery v1; agregado v2
   all-or-nothing. Anexo A.3.

**Ainda aberta:**
3. **FUTURE_PARALLELISM: OPEN** — mecanismo de fencing S3 atômico (anexo A.4) +
   serialização ECR por unit. Paralelismo DEV permanece OPEN; locks globais
   DEV/HOM preservados.

Distinção mantida em todo o documento: **estado atual comprovado** (§1) ·
**arquitetura de transição aprovada** (§2–§5) · **evoluções futuras não
aprovadas** (`OPEN`).
