# Marco 06 — OIDC, Octo STS, identidade de workload e Renovate

> **Origem:** V6, seções **124–141**.
>
> O conteúdo abaixo foi preservado da V6; a divisão em marcos não altera o conteúdo técnico original.

---
# 124. Octo STS: removendo PATs da software supply chain

Até aqui, falamos bastante sobre:

```text
artifact identity
package signatures
SBOM
provenance
image signing
admission
```

Mas existe outro ponto crítico:

```text
Como a automação autentica?
```

Um pipeline seguro perde boa parte do valor se depender de:

```text
PAT
static token
long-lived secret
shared credential
```

armazenado em CI/CD.

O Octo STS introduz um modelo diferente:

```text
Workload Identity
      │
      ▼
OIDC Token
      │
      ▼
Octo STS
      │
      ▼
Short-lived GitHub Token
```

O objetivo é eliminar credenciais persistentes sempre que possível.

---
# 125. PAT vs OIDC federation

## Modelo tradicional

```text
CI Job
  │
  ▼
PAT stored as secret
  │
  ▼
GitHub API
```

Problemas:

```text
long lifetime
possible overprivilege
secret rotation
secret leakage
credential reuse
poor workload binding
```

## Modelo federado

```text
CI Job
  │
  ▼
OIDC identity
  │
  ▼
Trust Policy
  │
  ▼
Short-lived credential
  │
  ▼
GitHub API
```

A principal mudança é sair de **credential possession** para:

```text
workload identity
+
policy
+
short lifetime
```

---
# 126. "You can't leak what you don't have"

Esse princípio resume bem a ideia.

Em vez de apenas proteger melhor um PAT:

```text
store securely
rotate periodically
limit scopes
monitor usage
```

o modelo federado pergunta:

> Podemos deixar de ter esse PAT?

Se sim:

```text
No long-lived PAT
       │
       ▼
No PAT to exfiltrate
```

Isso reduz uma classe inteira de riscos.

---
# 127. Octo STS como Security Token Service

O Octo STS atua como um STS para a API do GitHub.

```text
OIDC Provider
     │
     ▼
OIDC Token
     │
     ▼
Octo STS
     │
     ├── validates issuer
     ├── validates subject
     ├── reads trust policy
     └── evaluates permissions
            │
            ▼
      GitHub short-lived token
```

Esse padrão é semelhante ao conceito utilizado por serviços como AWS STS, GCP Workload Identity e identidades federadas do Azure.

---
# 128. Trust policies como código

No Octo STS, a confiança é declarada em arquivos como:

```text
.github/chainguard/{identity}.sts.yaml
```

Exemplos:

```text
renovate.sts.yaml
deploy.sts.yaml
ci.sts.yaml
```

Cada policy pode declarar:

```text
issuer
subject
permissions
repositories
```

Isso transforma autorização em:

```text
versioned policy
+
reviewable diff
+
Git history
```

---
# 129. Identity binding

Uma policy pode restringir o token a algo como:

```text
issuer = GitHub Actions
repository = org/repo
branch = main
```

Conceitualmente:

```text
ALLOW IF

issuer == trusted OIDC issuer
AND
repo == expected repo
AND
ref == refs/heads/main
```

Isso é mais forte do que:

```text
"quem tiver o segredo pode usar"
```

---
# 130. Exact subject > broad pattern

A documentação recomenda preferir subject exato quando possível.

Melhor:

```text
repo exato
+
owner ID imutável
+
repository ID imutável
+
branch exata
```

Mais flexível:

```text
subject_pattern / regex
```

O princípio geral é:

```text
least privilege
+
least identity scope
```

---
# 131. IDs imutáveis importam

Nomes podem mudar:

```text
org/repo
```

IDs numéricos representam uma identidade mais estável.

Subjects modernos podem incorporar identificadores como:

```text
org@123456
repo@654321
```

Isso reduz riscos relacionados a:

```text
rename
repository transfer
name reuse
```

---
# 132. Tokens curtos reduzem blast radius

Os tokens emitidos pelo Octo STS são de curta duração.

```text
PAT
────────────── potentially weeks/months

STS token
──── roughly one automation window
```

Se um token curto vazar, a janela de abuso é reduzida.

Além disso, o modelo exige nova federação quando a credencial expira.

---
# 133. GITHUB_TOKEN vs Octo STS

O `GITHUB_TOKEN` nativo do GitHub Actions continua sendo útil e deve ser preferido quando resolve o caso.

Octo STS entra principalmente quando precisamos de:

```text
cross-repository automation
organization-level actions
workflow updates
triggering additional workflows
external workloads
custom trust policies
```

O princípio continua:

> Use a credencial mais simples e menos privilegiada que resolva o caso.

---
# 134. Federation fora do GitHub Actions

O modelo não precisa ficar restrito ao GitHub Actions.

Qualquer workload capaz de produzir identidade OIDC pode, em princípio, participar:

```text
GitHub Actions
AWS
GCP
Azure
Kubernetes
Jenkins
GitLab CI
CircleCI
other OIDC providers
```

Arquitetura:

```text
External Workload
      │
      ▼
OIDC
      │
      ▼
Octo STS
      │
      ▼
GitHub API
```

---
# 135. Identity-based CI/CD

Com Sigstore e Octo STS juntos, surge uma convergência:

```text
Authentication to APIs
        │
        ▼
OIDC workload identity

Signing artifacts
        │
        ▼
OIDC workload identity
```

O mesmo pipeline pode provar:

```text
quem sou eu para acessar GitHub?
```

e:

```text
quem sou eu para assinar este artefato?
```

sem depender de chaves permanentes.

---
# 136. Renovate como controle de freshness

A V5 também incorpora freshness automatizado.

```text
Registry / dependency source
        │
        ▼
Renovate
        │
        ▼
Pull Request
        │
        ├── new image version
        ├── new digest
        ├── new GitHub Action
        └── dependency update
```

Não basta afirmar que imagens devem ser reconstruídas regularmente: o processo precisa detectar mudanças e gerar trabalho revisável.

---
# 137. Pequenos updates frequentes > grandes saltos raros

```text
frequent small updates
      >
rare large upgrades
```

Benefícios:

```text
smaller review surface
smaller compatibility delta
lower migration risk
faster security patching
less accumulated technical debt
```

---
# 138. Pinning de digest

Renovate pode adicionar ou atualizar digests.

```dockerfile
FROM image:1.2.3@sha256:...
```

A tag comunica intenção humana:

```text
1.2.3
```

O digest identifica o conteúdo:

```text
sha256:...
```

Isso combina:

```text
readability
+
content identity
```

---
# 139. Tag pinning vs digest pinning

## Apenas tag

```text
my-image:1.2.3
```

É uma referência potencialmente mutável.

## Digest

```text
my-image@sha256:abc...
```

É uma referência baseada no conteúdo.

## Combinação

```text
my-image:1.2.3@sha256:abc...
```

Entrega:

```text
human version
+
exact bytes
```

---
# 140. Renovate + digest = freshness sem perder reprodutibilidade

```text
Pin current digest
      │
      ▼
Renovate detects update
      │
      ▼
PR changes digest
      │
      ▼
review + tests
      │
      ▼
merge
```

Assim combinamos:

```text
reproducibility
+
controlled freshness
```

---
# 141. Supply chain identity flow completo

```text
GitHub Actions
     │
     ├── OIDC
     │     │
     │     ├── Octo STS → GitHub API token
     │     │
     │     └── Sigstore → signing identity
     │
     ▼
Build
     │
     ▼
Artifact
```

O mesmo workload pode possuir identidades verificáveis para API access, registry access e artifact signing.

---
