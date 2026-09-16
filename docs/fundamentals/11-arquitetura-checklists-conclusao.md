# Marco 11 — Arquitetura final, checklists e conclusão V6

> **Origem:** V6, seções **264–272**.
>
> O conteúdo abaixo foi preservado da V6; a divisão em marcos não altera o conteúdo técnico original.

---
# 264. Security control hierarchy

Podemos organizar os controles em camadas:

```text
Layer 1 — Build
source integrity
dependencies
reproducibility

Layer 2 — Artifact
SBOM
provenance
signature
scan

Layer 3 — Distribution
registry
digest
metadata preservation

Layer 4 — Admission
identity verification
attestation policies
vulnerability policies

Layer 5 — Workload
non-root
capabilities
seccomp
sysctls

Layer 6 — Runtime
network
IAM
runtime detection
observability
```

Nenhuma camada substitui as demais.

---
# 265. V6 architecture

```text
                         SOURCE
                           │
                           ▼
                    TRUSTED WORKFLOW
                           │
                 ┌─────────┼─────────┐
                 │         │         │
                 ▼         ▼         ▼
               OIDC      OIDC      OIDC
                 │         │         │
                 ▼         ▼         ▼
            Octo STS   Cloud STS   Fulcio
                 │         │         │
                 └─────────┼─────────┘
                           ▼
                      BUILD SYSTEM
                           │
                     ┌─────┴─────┐
                     ▼           ▼
                  MELANGE       APKO
                     │           │
                     ▼           ▼
                  PACKAGES     OCI IMAGE
                                 │
                 ┌───────────────┼────────────────┐
                 ▼               ▼                ▼
               SBOM         PROVENANCE       VULN REPORT
                 │               │                │
                 └───────────────┼────────────────┘
                                 ▼
                         SIGN / ATTEST
                                 │
                                 ▼
                              REGISTRY
                                 │
                                 ▼
                      KUBERNETES API REQUEST
                                 │
                                 ▼
                    SIGSTORE POLICY CONTROLLER
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
                SIGNATURE      SBOM       PROVENANCE
                    │            │            │
                    └────────────┼────────────┘
                                 ▼
                       VULNERABILITY POLICY
                                 │
                                 ▼
                        WORKLOAD SPEC POLICY
                                 │
                              ┌──┴──┐
                              │     │
                            PASS   FAIL
                              │     │
                              ▼     ▼
                            ADMIT  DENY
```

---
# 266. Checklist V6 — Admission

```text
[ ] Namespaces de enforcement estão explicitamente definidos
[ ] No-match behavior é conhecido e testado
[ ] Policies usam escopos de imagem deliberados
[ ] Tags são verificadas como digests
[ ] Signed-image policy valida signer identity
[ ] OIDC issuer esperado está restrito
[ ] Subject esperado está restrito
[ ] Policies foram testadas com casos positivos e negativos
[ ] Warn precede enforce quando necessário
```

---
# 267. Checklist V6 — Attestations

```text
[ ] SBOM attestation é exigida onde necessário
[ ] Predicate type é explícito
[ ] Signer da attestation é confiável
[ ] Attestation está ligada ao digest correto
[ ] Provenance é validada
[ ] Vulnerability report é assinado
[ ] Freshness do scan é considerada
[ ] VEX pode influenciar decisões de risco
```

---
# 268. Checklist V6 — Workload security

```text
[ ] Containers não executam privileged sem exceção aprovada
[ ] Non-root é obrigatório quando aplicável
[ ] Capabilities são minimizadas
[ ] ALL é dropado quando possível
[ ] Unsafe sysctls são bloqueados
[ ] Host namespaces são controlados
[ ] Seccomp é aplicado
[ ] Responsabilidade entre Policy Controller e outros policy engines é clara
```

---
# 269. Checklist V6 — Policy engineering

```text
[ ] Policy possui owner
[ ] Policy possui versionamento
[ ] Policy possui testes
[ ] Policy possui documentação
[ ] Policy possui modo warn/enforce definido
[ ] Policy possui mensagens úteis
[ ] Exceções possuem processo formal
[ ] Métricas de rejection são observadas
[ ] Mudanças passam por revisão
```

---
# 270. Modelo mental V6

A V6 adiciona o último elemento que faltava:

```text
TRUST
  is not only
EVIDENCE
```

Trust operacional precisa de:

```text
Evidence
   +
Identity
   +
Verification
   +
Policy
   +
Enforcement
```

Assim:

```text
Signed
```

não basta.

```text
Attested
```

não basta.

```text
Scanned
```

não basta.

Precisamos também responder:

> O sistema impede o deploy quando a garantia esperada não está presente?

---
# 271. Conclusão V6: verifiable → enforceable

A evolução completa agora é:

```text
Dockerfile
   │
   ▼
Minimal Image
   │
   ▼
Known Packages
   │
   ▼
SBOM
   │
   ▼
Provenance
   │
   ▼
Signed Artifact
   │
   ▼
Verifiable Identity
   │
   ▼
Attestations
   │
   ▼
Admission Policy
   │
   ▼
Enforcement
```

A supply chain deixa de ser apenas:

```text
verifiable
```

e passa a ser:

```text
enforceable
```

Esse é o principal avanço da V6.

---
# 272. Conclusão

O vídeo apresenta uma mudança de mentalidade importante.

A pergunta deixa de ser:

> Qual é a menor imagem que conseguimos construir?

e passa a ser:

> Qual é a menor imagem que conseguimos construir mantendo rastreabilidade, segurança, observabilidade da supply chain e conhecimento completo dos componentes utilizados?

Nesse modelo, tamanho é apenas uma consequência.

O objetivo real é conseguir olhar para uma imagem de produção e responder:

```text
Eu sei exatamente o que existe aqui.

Eu sei de onde veio.

Eu sei qual versão está sendo utilizada.

Eu sei como foi construído.

Eu consigo verificar sua integridade.

Eu consigo escanear seus componentes.

Eu consigo validar quem produziu o artefato.
```

Essa é a base de uma **software supply chain segura**.

---
