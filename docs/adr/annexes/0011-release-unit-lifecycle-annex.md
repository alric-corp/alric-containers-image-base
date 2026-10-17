# Anexo técnico — Lifecycle das release units (ADR-0011)

Companion de [ADR-0011 — Contrato de lifecycle das release units](../0011-release-unit-lifecycle-contract.md).
Base: `develop @ 3ac900b4db4d0e3fe7e60945c3b828d6dd7532a4`. **(fato)** = verificado
no código; o resto é alvo proposto. `IMPLEMENTATION_AUTHORIZED: NO` ·
`REMOTE_WRITES: 0`.

---

## A.0 — Tabela de reconciliação factual (afirmação anterior × evidência)

| # | Afirmação anterior do DRAFT | Evidência no código / workflows | Veredito |
|---|---|---|---|
| 1 | `promotion_batch.py` fornece isolamento operacional hospedado | Nenhum workflow invoca `promotion_batch`; `promote-stable.yml`/`dev-stable.yml`/`recover-stable.yml` chamam `scripts.pipeline.release.lifecycle` | **FALSO** — é ferramenta existente mas não invocada |
| 2 | Isolamento de falha por unit no caminho operacional | `lifecycle.publish_states()` itera o manifesto inteiro sob um lock global por destino | **CORRIGIDO** — all-or-nothing hoje; isolamento por unit é alvo |
| 3 | Resultado terminal arbitrado por `outcome.json` create-once em `releases/<rid>/units/<unit_id>/ops/<op_id>/` | Não existe `outcome.json` nem layout `ops/<op_id>/` no código; o terminal é `events/r<run>-a<attempt>/completed.json` de nível manifesto | **CORRIGIDO** — layout era proposto, não fato |
| 4 | `op_id` = `r<run>` + action, sem attempt | Chave de evento real é `events/r<run>-a<attempt>/...`: o attempt **faz parte** da chave de operação no código | **CORRIGIDO** — `op_id` alvo = `op-<action>-r<run>-a<attempt>` (attempt incluído) |
| 5 | Autoridade terminal por unit (recibo por unit) já estabelecida | Autoridade atual = recibo agregado de nível manifesto; `promoted/<rid>.json` só HOM/não-recovery | **CORRIGIDO + APROVADO (D2)** — era alvo; owner aprovou T1 ajustada (recibo canônico único por unit/op v2 como autoridade); agregado v1 segue autoritativo p/ recovery v1 |
| 6 | `Store.put(immutable=True)` reconciliaria documentos divergentes | `require(self.get(key)==document, ...)` em `PreconditionFailed`: recusa divergente (levanta erro) | **CORRIGIDO** — nunca aceita divergente |
| 7 | Membership poderia divergir entre 9 e 11 agrupamentos | `release_units()`=**9** (membership canônico: 7 pares incl. Node 22/24 + 2 Python); `promotion_units()`=**11** (auxiliar: 5 pares compilados + 4 singletons Node + 2 singletons Python, pois `publication_contract()` classifica Node como interpretado → `runtime_framework=framework` sem `dev_framework`); `SCENARIOS`=9; `frameworks/*.yaml`=16 | **CONFIRMADO (divergência real por desenho)** — 9 canônicas × 11 auxiliares são conceitos distintos; os 11 são agrupamentos de testes/publicação, não membership de release |
| 8 | Fencing S3 por geração via If-Match no objeto `state` resolve perda de posse | CAS no objeto `state/<fw>.json` valida o ETag daquele objeto, não a posse da geração do lease (objeto distinto) | **CORRIGIDO** — fencing efetivo `OPEN` |
| 9 | ECR put-image fencível na fronteira | `aws ecr put-image` sem CAS/If-Match/fencing (`lifecycle.write_stable`) | **CONFIRMADO** — só serialização protege a escrita em voo |

---

## A.1 — Estados, transições e matriz de não-colisão

**Estados de seleção (fato, dispersos em `find_promotion_candidate.py`):**
`CANDIDATE` (elegível), `WAITING` (dentro do soak — `approve_dev` grava
`status: WAITING`), `SKIPPED` (sem candidato, com `skip_reason`), e proposto
`NOT_SELECTED` (elegível mas preterido por ordering/high-watermark).

**Prefixos atuais (fato):** `releases/<rid>/manifest.json`,
`releases/<rid>/candidate.json`, `state/<framework>.json`,
`events/r<run>-a<attempt>/{started,completed,failed}.json`, `promoted/<rid>.json`,
`releases/<rid>/evidence/...`.

**Matriz de autoridade e não-colisão** (**A** = fonte de verdade; **D** =
derivado; **P** = proposto, não fato):

| Registro | Chave | Mutável | Create-once | Autoridade | Múltiplas operações |
|---|---|---|---|---|---|
| Manifesto release (v1, fato) | `releases/<rid>/manifest.json` | não | sim | A (conteúdo do build) | 1 por `rid` |
| Candidate (v1, fato) | `releases/<rid>/candidate.json` | não | sim | A (candidato DEV) | 1 por `rid` |
| Estado por framework (fato) | `state/<framework>.json` | **sim** | não | **A** (hold/high-watermark) | reescrito a cada transição |
| Evento agregado (fato) | `events/r<run>-a<attempt>/{started,completed,failed}.json` | não | sim | A (operação inteira, nível manifesto) | 1 terminal por run-attempt |
| Recibo agregado (fato) | `promoted/<rid>.json` | não | sim | A all-or-nothing (release) | só se TODAS as units PROMOTED; só HOM/não-recovery |
| Recibo terminal canônico por unit (v2) | `releases/<rid>/units/<unit_id>/ops/<op_id>/receipt.json` com `status ∈ {PROMOTED, FAILED}` | não | **sim (árbitro único)** | **A (aprovado D2, 2026-10-16)** — ver A.3 | 1 por `op_id`; `--if-none-match '*'` escolhe atomicamente; divergente recusado |
| Evento por unit (**P**) | `events/<op_id>/units/<unit_id>/{started,completed,failed}.json` | não | sim | **D** (auditoria consistente com o recibo terminal) | operações distintas = `op_id` distinto; um rerun (attempt +1) é um `op_id` novo, não um `started` extra sob o mesmo |
| Visão corrente por unit (**P**) | derivada de `state/<fw>.json` + recibo terminal canônico | — | — | **D** | n/a |

**INV7 (não-colisão):** toda chave proposta por unit vive sob `/units/<unit_id>/`,
segmento que o schema v1 nunca emite; nenhuma coincide com chave v1. Verificável
offline (A.2, cenários 1 e 20).

---

## A.2 — Matriz de aceite offline (20 cenários; nenhum teste executado nesta fase)

Cada cenário declara: Pré-condição · Falha injetada · Resultado esperado ·
Invariante · Fail-closed.

| # | Cenário | Invariante | Resultado esperado |
|---|---|---|---|
| 1 | Identidade composta e não-colisão entre operações | INV7/D-IDENTITY | **retry interno da mesma tentativa** (mesmo run+attempt) → **mesmo `op_id`**, só reescreve conteúdo idêntico; **rerun nativo do GitHub (attempt +1)**, **nova promoção** e **recovery** → **`op_id` novo** (o attempt faz parte do `op_id = op-<action>-r<run>-a<attempt>`), chaves distintas; nenhuma sobrescreve registro anterior |
| 2 | Membership exato das 9 units | INV1/ADR-0010 | cobertura exata e disjunta 7 pares + 2 singletons |
| 3 | Equivalência de manifestos v1 | INV4 | manifesto v1 lido/recovery OK sem sidecar |
| 4 | Sidecar v2 ausente/incompleto/inválido/corrompido | INV4 | bloqueia cada variante; nunca degrada v1 |
| 5 | Falha ao persistir o 2º hold de um par | A.1/§4 | holds mantidos; unit não autorizada; sem recibo |
| 6 | Falha após a 1ª escrita ECR | §4 | FAILED; ambos re-held; sem promoted/agregado |
| 7 | Falha durante read-back | INV | sem PROMOTED; `read_back_status=failed`; hold |
| 8 | Falha de persistência do recibo | A.3 | sem agregado; holds; fail-closed |
| 9 | Retry **interno da mesma tentativa** após interrupção | A.1/INV7 | mesmo `op_id` (mesmo run+attempt) reescreve só conteúdo idêntico; divergente recusado por create-once |
| 10 | Execuções concorrentes sobre a mesma unit | INV8 | **transição:** serialização global DEV garante nunca dois na seção crítica; lease por unit só garante **após** fencing S3 (A.4) + serialização ECR |
| 11 | Units independentes: isolamento de falha × execução concorrente | INV2 | **transição:** falha isolada logicamente, execução **serializada** pelo lock global (sem concorrência física); **futuro:** concorrência real só após A.4 |
| 12 | High-watermark monotônico | INV5 | job obsoleto não regride stable |
| 13 | Gate global reprovado × gate local reprovado | INV3 | global reprova tudo; local reprova só a unit (alvo) |
| 14 | Preservação cosign/SLSA/SPDX/digests | INV | binding e assinaturas intactos; sem rebuild |
| 15 | Recovery histórico v1 | INV4/`recover_hom` | baseado no agregado v1; preservado |
| 16 | Recovery individual v2 | A.3 | exige recibo terminal por unit válido + trust/scan/read-back |
| 17 | Autoridade do agregado | INV6 | agregado só com re-comprovação simultânea de todas as units |
| 18 | Cutover lock global → lock por unit | INV8 | sem janela de sobreposição desprotegida; rollback seguro |
| 19 | Expiração de TTL em operação em andamento + retomada de escritor obsoleto (S3 e ECR) | INV8/§4 | **(a)** A pausa, lease expira, B toma `generation=11`; A retoma e tenta escrever `state` com `generation=10` → prova de rejeição pelo fencing atômico **escolhido** (A.4) **ou**, na ausência dele, que a serialização impediu B de tomar o lease durante a seção crítica de A; CAS no objeto `state` sozinho **não** satisfaz (não valida posse de geração). **(b)** A perde autoridade com `put-image` ECR **em voo** → ECR sem fencing (fato); exige que nenhum 2º `put-image` da unit inicie concorrentemente (serialização). Aceite reproduz a corrida **durante** a chamada ECR. Fail-closed: holds persistem |
| 20 | Dois resultados terminais contraditórios sob o mesmo `op_id` | INV7/A.3 | Pré: recibo terminal `FAILED` gravado para `(unit_id,op_id)`. Falha injetada: uma **reescrita da mesma operação** (retry interno da mesma tentativa, ou replay da mesma `op_id`) tenta gravar `PROMOTED` → **recusada por create-once** (`--if-none-match '*'`, conteúdo divergente). Único árbitro permanece o recibo terminal. Um **rerun nativo do GitHub (attempt +1)** é um **`op_id` novo** — não reabre o terminal anterior: ao observar `FAILED` na operação anterior, **roteia para recovery** (operação explícita, novo `op_id`), nunca para um sucesso concorrente. Variante: `completed.json` e `failed.json` ambos presentes para o mesmo `op_id` → a visão autoritativa deriva **só** do recibo terminal canônico (duas chaves de auditoria distintas não decidem o terminal) |

Aceite offline é **obrigatório antes de qualquer execução hospedada**. Critérios
de aceite hospedado (não executar): matriz 100% verde; janela DEV sob
dupla-proteção sem sobreposição observada; HOM global; G07 e golden path Go 1.26
preservados; FULL semanal permanece alternativa não aprovada.

---

## A.3 — Autoridade terminal e recibos (T1 ajustada **APROVADA**, D2 2026-10-16)

**Decisão original do owner:** autoridade de promoção no **recibo individual**.
**Estado atual (fato):** autoridade de nível manifesto (`events/r<run>-a<attempt>/
completed.json`, `promoted/<rid>.json` agregado). Não há `outcome.json`.

**Proposta preferencial:** um único recibo terminal canônico por `op_id`
(`releases/<rid>/units/<unit_id>/ops/<op_id>/receipt.json`, `status ∈ {PROMOTED,
FAILED}`, create-once) que **é** o árbitro — eliminando um segundo registro
independente. Create-once sobre uma **única** chave canônica arbitra atomicamente;
dois registros em chaves distintas (`completed.json`/`failed.json`) **não**
estabelecem exclusão mútua entre si (são chaves diferentes), por isso são apenas
auditoria derivada.

**Decisão aprovada (D2, owner 2026-10-16): T1 ajustada.** A autoridade terminal v2
passa a ser o recibo terminal canônico único por unidade/operação. Isto **altera
deliberadamente** a granularidade da autoridade original (de recibo de nível
manifesto para recibo por unit em v2), com aprovação explícita do owner.

- **T1 (APROVADA) — recibo terminal canônico único por unidade/operação v2:**
  1. Um **único** recibo terminal canônico create-once por `(unit_id, op_id)` v2,
     `status ∈ {PROMOTED, FAILED}`, árbitro atômico via `--if-none-match '*'`.
  2. `completed.json`/`failed.json` existem **apenas como auditoria derivada**,
     escritos após e consistentes com o recibo terminal.
  3. **Nenhum segundo árbitro independente** (sem `outcome.json` nem qualquer
     registro paralelo que possa divergir).
  4. O **recibo agregado histórico v1** (`promoted/<rid>.json`) permanece
     **autoritativo para recovery v1** — não é reescrito nem rebaixado.
  5. O **agregado v2 é all-or-nothing**: só afirmado quando a **release inteira**
     foi validada (todas as units PROMOTED).
  6. **Recovery individual v2** requer recibo terminal válido **+** trust **+**
     read-back — nunca promove a partir de evidência derivada isolada.
  7. **Estados históricos não são reescritos**; a nova autoridade vale só para
     operações v2 novas.

**Alternativas não escolhidas (registradas):**
- **T2** — manter o recibo agregado de nível manifesto como autoridade; preservaria
  a granularidade antiga mas adiaria o isolamento por unit. **Não escolhida.**
- **T3** — híbrido (agregado em HOM, canônico por unit em DEV). **Não escolhida.**

Autorização **documental**; implementação não autorizada.

**Idempotência e falha parcial (ordem de persistência, fail-closed).** A sequência
por unit v2 é: **(1)** hold persistido → **(2)** mutação ECR (`put-image`, sem CAS)
→ **(3)** read-back obrigatório do digest → **(4)** persistência do recibo terminal
canônico → **(5)** evidências derivadas (`completed`/`failed`). Comportamento exigido:
- Falha entre (2) e (3): sem recibo `PROMOTED`; hold mantido; `read_back_status`
  registra a falha. Um retry interno da mesma tentativa (mesmo `op_id`) é
  idempotente — reescreve só conteúdo idêntico; divergente recusado.
- Falha entre (3) e (4): o read-back pode ter confirmado, mas **sem o recibo
  terminal persistido a operação não é PROMOTED** (o recibo é o árbitro). Um retry
  interno regrava o recibo idempotentemente; se a autoridade anterior já gravou
  `FAILED`, create-once recusa um `PROMOTED` divergente.
- Falha entre (4) e (5): o recibo terminal é a verdade; evidências derivadas
  ausentes/inconsistentes **bloqueiam** a visão corrente (fail-closed), nunca a
  promovem — a reconciliação só aceita evidência derivada consistente com o recibo.
- Em nenhum ponto uma segunda identidade operacional (rerun attempt +1 = novo
  `op_id`) reabre um recibo terminal anterior; ela roteia para recovery explícito.

---

## A.4 — Lease e concorrência futura (OPEN)

Transição aprovada: DEV global, HOM global, isolamento lógico por unit,
paralelismo DEV futuro não autorizado. Para o mecanismo futuro por unit,
identificar antes de qualquer aprovação:

- **Prefixo mutável do lease**, separado dos registros create-once: um objeto de
  lease sob um prefixo **mutável** (ex.: `leases/<unit_id>.json`), nunca sob
  `releases/*`/`promoted/*`/`events/*` (que são Deny-on-overwrite).
- **Contrato de aquisição/renovação/expiração/liberação:** identidade de owner,
  geração monotônica, prazo de validade; renovação condicional à posse;
  liberação que não pode liberar o lease de outra operação.
- **Primitiva concreta de CAS:** S3 condicional (`If-Match` no ETag do **objeto
  de lease**) é a única primitiva disponível — e protege apenas a mutação **daquele
  objeto**, não a escrita de `state/<fw>.json` (objeto distinto) nem a tag ECR.
- **Evolução de `release_store.py` e do modelo offline S3:** `Store` hoje não tem
  um `put` condicional por ETag arbitrário (só `--if-none-match '*'`); um lease
  renovável exige `If-Match: <etag>`, ainda não implementado.
- **Limitação de fencing entre objetos distintos:** validar a geração no objeto de
  lease **não** torna atômica a escrita de `state`/ECR; o fencing precisa estar na
  **fronteira da mutação** do objeto efetivamente escrito.
- **Limitação ECR sem CAS:** `put-image` não é fencível; só serialização exclui
  um 2º escritor em voo.

Enquanto não houver mecanismo **escolhido e demonstrável**, `ECR_MUTATION_SAFETY`
e o fencing S3 atômico permanecem **OPEN**; o lock global é o fallback.

**Alternativas de concorrência DEV:**
- **A — lock global + isolamento lógico (atual):** garante exclusão sobre a seção
  crítica inteira; sem concorrência física; nenhuma infra nova. Pré-condição de
  remoção: A.4 resolvido.
- **B — lock por `unit_id` via `concurrency.group`:** concorrência entre units,
  mas o Actions não é FIFO e substitui o pendente; **não** exclui um `put-image`
  ECR em voo de um runner obsoleto. Limitação decisiva.
- **C — executor exclusivo por unit:** serializa as mutações ECR por unit;
  introduz **infraestrutura nova** (fila/executor durável) e exige decisão
  explícita do owner.

---

## A.5 — Migração (faseada, sem autorizar execução)

- **F1** Introduzir a fonte canônica de membership (ADR-0010) como adapter, com
  equivalência v1 byte-a-byte demonstrada por teste. Sem mudança de schema.
- **F2** Introduzir evidência por unit (`/units/<unit_id>/`) **aditiva**, sem tocar
  chaves v1; leitura degrada para o caminho agregado v1 quando o sidecar ausenta —
  exceto onde INV4 exige bloqueio para operações novas.
- **F3** Barreira **lógica** por unit em `lifecycle` DEV **sob o lock global DEV
  preservado** (isolamento de falha, não paralelismo). A substituição do lock
  global por lock por unit **não** faz parte da transição aprovada: é arquitetura
  futura (A.4), condicionada a fencing S3 atômico + serialização ECR por unit.

Nenhuma fase altera releases históricas, habilita HOM, remove soak, ou toca
gates/policies/infra/trust/G07/golden path Go 1.26.
