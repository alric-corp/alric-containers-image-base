# Consumer Verification Contract

Contrato de consumo da fábrica `alric-corp/alric-containers-image-base`.
Revisão documental: 13/09/2026, baseline main
`e3ed68259f66af41e8054a4c0ac29a54082ddd60`. Este documento descreve o projeto
no sandbox e os requisitos de adoção corporativa; não declara produção liberada.

## Três identidades, três usos

| Identidade | Significado | Limite |
| --- | --- | --- |
| `stable` | Ponteiro mutável de conveniência, atualizado pela promoção | Não é identidade permanente nem aprovação de uma aplicação consumidora |
| build tag | Identificador versionado/imutável da release, `ddmmaa-hhmm-r<run_id>-a<attempt>` | A tag pode existir antes de assinatura/attestations concluírem; imutabilidade não garante retenção eterna |
| OCI index digest | Identidade exata do artifact multiarch, `sha256:<64 hex>` | Identifica conteúdo; isoladamente não autentica quem o produziu nem sua segurança |

A unidade suportada para assinatura de imagem e provenance é o **OCI index
digest**. O índice referencia exatamente `linux/amd64` e `linux/arm64`; o
runtime seleciona o manifest da plataforma. O pipeline não publica assinaturas
de imagem ou provenance independentes para esses manifests. Os SBOMs das
plataformas possuem attestations próprias, o que é uma propriedade diferente.
Não use pin de manifest individual como substituto do fluxo oficial por índice.

### Convenience

`<registry>/image-base-<framework>:stable` acompanha promoções. Serve para
exploração e fluxos que aceitam mudança de conteúdo. Dois pulls da mesma tag
em momentos diferentes podem obter índices diferentes.

### Reproducible deployment

`<registry>/image-base-<framework>@sha256:<index-digest>` fixa o artifact exato.
Registre esse índice no Dockerfile/lock de bases do consumidor. Em builds
multi-stage, fixe separadamente os índices do runtime e do `-dev`.

O pin da base não torna a aplicação inteira reproduzível: código, dependências,
ferramentas, configuração e imagem final também precisam de identidade própria.
Atualizações da base exigem nova decisão e validação do consumidor; um pin
não acompanha automaticamente correções futuras.

### Audited / verified consumption

Antes de confiar na base, obtenha o índice de uma release selecionada, confira
assinatura Cosign, provenance GitHub e, quando exigido pela policy consumidora,
SBOM attestation. Fixe e use **o mesmo digest** após a verificação; não volte
a usar `stable` no build/deploy, pois isso permitiria resolver outro conteúdo.

Evidence disponível no registry/GitHub não é enforcement no runtime. A fábrica
não instala admission controller nem faz todos os consumidores executarem
essas verificações automaticamente. Cabe ao time consumidor integrar o gate
à sua esteira conforme a política corporativa aprovada.

## Identidade vigente e ferramentas

| Campo | Sandbox atual |
| --- | --- |
| Registry | `712107929769.dkr.ecr.us-east-1.amazonaws.com` |
| Repository de origem | `alric-corp/alric-containers-image-base` |
| Repository ID | `1360616627` |
| Owner ID | `178685987` |
| Workflow assinante | `alric-corp/alric-containers-image-base/.github/workflows/build-base-images.yml` |
| Certificate identity Cosign | `https://github.com/alric-corp/alric-containers-image-base/.github/workflows/build-base-images.yml@refs/heads/main` |
| OIDC issuer Cosign | `https://token.actions.githubusercontent.com` |
| Source ref | `refs/heads/main` |

Fontes canônicas: [signing-identities.json](../policies/release/signing-identities.json),
[verify_promotion.py](../scripts/pipeline/release/verify_promotion.py) e
[publicador](../.github/workflows/build-base-images.yml). A identidade do
assinante continua no produto, não no executor compartilhado de validação.

Pré-requisitos: acesso de leitura ao ECR, AWS CLI, Docker com Buildx, Cosign,
GitHub CLI autenticado para leitura das attestations e Python 3 para o
verificador do projeto. `jq` é necessário apenas para extrair os SPDX abaixo.
O installer fixado no workflow instala Cosign v3.0.6; a CLI `gh` vem do runner
e sua versão é registrada em evidence. As flags foram conferidas nas fontes
oficiais indicadas ao final. Não desabilite verificações TLS, de assinatura,
certificado, transparência ou subject para contornar falhas.

## Selecionar uma identidade uma única vez

O exemplo usa Java 21 no sandbox. Ele requer acesso já autorizado; não cria
roles, policies ou repositórios. Troque o framework por um disponível no
[catálogo](../README.md#imagens-disponíveis).

Em uma sessão Bash, use o índice registrado na evidence de release aprovada.
Se a escolha for a stable atual, resolva-a uma vez, valide a resposta e preserve
esse valor. Esta consulta por si só ainda não verifica origem ou promoção:

```bash
set -euo pipefail
AWS_ACCOUNT_ID=712107929769
AWS_REGION=us-east-1
REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_REPOSITORY=image-base-java21
SOURCE_REPO=alric-corp/alric-containers-image-base
SIGNER_WORKFLOW="${SOURCE_REPO}/.github/workflows/build-base-images.yml"
CERT_IDENTITY="https://github.com/${SIGNER_WORKFLOW}@refs/heads/main"
OIDC_ISSUER=https://token.actions.githubusercontent.com

aws ecr get-login-password --region "$AWS_REGION" |
  docker login --username AWS --password-stdin "$REGISTRY"

INDEX_DIGEST=$(aws ecr describe-images \
  --region "$AWS_REGION" \
  --registry-id "$AWS_ACCOUNT_ID" \
  --repository-name "$IMAGE_REPOSITORY" \
  --image-ids imageTag=stable \
  --query 'imageDetails[].imageDigest' --output text)
[[ "$INDEX_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]]
IMAGE_REF="${REGISTRY}/${IMAGE_REPOSITORY}@${INDEX_DIGEST}"
```

Tag ausente, erro ou múltiplos digests não satisfazem a validação. Para usar
um digest aprovado previamente, substitua somente a atribuição de
`INDEX_DIGEST` pelo valor da release, mantendo a validação e `IMAGE_REF`.

## Verificar assinatura

Para releases assinadas com o nome atual:

```bash
cosign verify \
  --certificate-identity "$CERT_IDENTITY" \
  --certificate-oidc-issuer "$OIDC_ISSUER" \
  "$IMAGE_REF" > signature.json
```

Esse comando vincula a assinatura ao digest, à identidade exata do workflow
na main e ao issuer esperado. Uma assinatura válida não prova que o pacote
é seguro, que o scan atual passaria ou que houve aprovação humana.

## Verificar provenance

```bash
gh attestation verify "oci://${IMAGE_REF}" \
  --repo "$SOURCE_REPO" \
  --signer-workflow "$SIGNER_WORKFLOW" \
  --source-ref refs/heads/main \
  --predicate-type https://slsa.dev/provenance/v1 \
  --format json > provenance.json
```

O comando autentica a declaração vinculada ao **subject digest** e à identidade
de build: repository, workflow, commit/ref e execução de origem. Consulte a
saída verificada e compare o commit/run com a release que sua organização
aprovou; aceitar main não fixa um commit específico. O matching de
`--signer-workflow` é o mecanismo da CLI GitHub; não é a comparação literal
de SAN feita pelo `--certificate-identity` do Cosign.

Provenance não prova imagem livre de vulnerabilidades, aprovação humana,
segurança do código ou execução bem-sucedida de todos os gates. O workflow
produz a declaração; a confiança nele depende de governança da origem.
O formato SLSA v1 não atribui um **SLSA level formal** à plataforma.

### Script único (sem checkout do repositório)

[`scripts/verify-image.sh`](../scripts/verify-image.sh) executa exatamente
os três comandos acima (assinatura, SBOM attestation, provenance) em
sequência, contra uma tag ou um digest, sem depender de contexto interno
do CI — apenas `aws`, `docker`, `cosign` e `gh` na máquina de quem consome.
Copie o arquivo (não precisa clonar o repositório) e rode:

```bash
verify-image.sh go1-26 "$INDEX_DIGEST" \
  --account "$AWS_ACCOUNT_ID" --region "$AWS_REGION"
```

Sai `0` só se as três verificações passarem; reporta cada falha
individualmente e continua as demais (uma falha de assinatura não impede
ver se SBOM/provenance também falham). Não confere os IDs numéricos da
policy do projeto — para isso, use o módulo abaixo com um checkout revisado.

### Aplicar a política completa do projeto

Os comandos diretos acima não conferem sozinhos os IDs numéricos da policy.
Para reproduzir a verificação usada pela promoção/recovery, execute da raiz
de um checkout revisado deste repositório:

```bash
python3 -B -m scripts.pipeline.release.verify_promotion \
  "$IMAGE_REF" "$SOURCE_REPO"
```

O módulo exige índice com as duas plataformas, assinatura e provenance da
mesma identidade/digest e IDs certificados de repository/owner. Gera em `reports/` os arquivos `candidate-index.json`, `signature.json`,
`provenance.json` e `verified-identity.json`. Ele não executa soak, scan, promoção ou escrita no ECR,
nem verifica SBOM attestations; esses controles não são inferidos do sucesso.

A policy também admite o nome histórico `alric-corp/itau-xj7-containers-image-base`
somente com os mesmos IDs assinados. Para uma release histórica, use o módulo
e obtenha `signer_repository` da decisão verificada antes de construir a
identidade de verificação do SBOM. Não amplie regex nem aceite o alias por
nome apenas. O alias histórico aceito está em
`policies/release/signing-identities.json`.

## Verificar e consumir SBOM

Há quatro operações distintas:

| Operação | Implementação / responsabilidade |
| --- | --- |
| SBOM generation | Apko gera SPDX originais para índice, amd64 e arm64; validação registra subject e SHA-256 |
| SBOM attestation | Publicador usa Cosign `attest --type spdxjson` em cada digest correspondente, sem regenerar SPDX |
| SBOM verification | Consumidor verifica assinatura, identidade, tipo e subject antes de aceitar o documento |
| SBOM consumption | AppSec/consumidor importa o SPDX verificado em inventário/scanner e decide sua política |

Após a política completa acima retornar sucesso, use a identidade que ela
verificou, incluindo compatibilidade histórica aprovada:

```bash
VERIFIED_SIGNER=$(jq -er '.signer_repository' reports/verified-identity.json)
SBOM_CERT_IDENTITY="https://github.com/${VERIFIED_SIGNER}/.github/workflows/build-base-images.yml@refs/heads/main"
cosign verify-attestation \
  --certificate-identity "$SBOM_CERT_IDENTITY" \
  --certificate-oidc-issuer "$OIDC_ISSUER" \
  --type spdxjson \
  "$IMAGE_REF" > sbom-index.attestations.jsonl

jq '.payload | @base64d | fromjson | .predicate' \
  sbom-index.attestations.jsonl > sbom-index.verified.spdx.json
```

Execute a extração somente após exit 0 da verificação; baixar/decodificar um
payload não verifica sua autenticidade. Cosign pode retornar vários envelopes
válidos; nesse caso o arquivo extraído é uma sequência JSON. A ingestão precisa
tratar cada SPDX, sem escolher silenciosamente um documento conflitante.

Para inventário por arquitetura, obtenha o manifest da plataforma em
`reports/candidate-index.json`, já vinculado ao índice verificado, e repita
`cosign verify-attestation --type spdxjson` sobre esse digest de plataforma.
Isso verifica o SBOM daquele manifest; a identidade oficial de consumo da
imagem permanece o índice. Não use o SPDX do índice como prova de inventário
completo de cada arquitetura. SBOM não é provenance nem prova completude,
ausência de CVEs ou licença de distribuição aprovada.

## Garantias e limites da fábrica

- **Build Once / Promote Many:** publicação copia o OCI aprovado preservando
  digests; promoção/recovery movem referência. Replay de build com lock é
  outra operação e depende da retenção de packages/inputs na origem.
- **Stable (P1-01):** candidato verificado → re-scan → stable escrita → ECR
  read-back pela tag → observed digest == candidate digest → promoted=true.
  O read-back confirma o estado observado naquele instante. Não impede
  alterações administrativas externas futuras, e falha após escrita não
  desfaz a tag automaticamente.
- **Retry (P1-02):** mesmo run, framework/revisão, índice/plataformas (e par
  -dev quando aplicável), PASS válido e ausência de falha mais recente do
  producer relevante permitem reuso. Não há rebuild, repack ou novo digest.
  Evidence ausente, inválida ou conflitante não aprova publicação.
- **Cobertura funcional:** 11 contratos diretos, seis interpretados e cinco
  compilados, conforme lote/plano. Os cinco -dev compilados são exercitados
  no único contrato do respectivo runtime. Publicar qualquer membro exige
  esse contrato aprovado, do mesmo run e revisão, vinculado aos índices e
  manifests de ambas as plataformas dos dois candidatos atuais. Par
  incompleto ou evidência ausente, falha ou incompatível bloqueia publicação.
  O `not_required`/`passed:null` do planejamento/gate genérico descreve
  cobertura; não autoriza publicação. Assinatura não substitui o contrato.
- **Wolfi (P1-03):** chave local versionada + SHA pin + rotação humana + drift
  detect-only. Apko pode acrescentar chaves por repository discovery/JWKS;
  não há trust anchor exclusiva. Ver [risco e rotação](wolfi-signing-key.md).
- **Scan:** Trivy por arquitetura usa a policy vigente e os dados daquele
  instante. Vulnerabilidades sem correção são reportadas separadamente;
  assinatura/SBOM/provenance não significam imagem livre de vulnerabilidades.

O consumidor deve testar sua aplicação, manter non-root/read-only e áreas
graváveis conforme necessidade, acompanhar atualizações e controlar o deploy.
Promover/reverter a base não reconstrói nem reverte aplicações já publicadas.

## Adoção corporativa: aceites externos

Os valores concretos acima são do sandbox. Antes de uso corporativo, substituir
registry/conta/região, repository e owner IDs, workflow e identidade certificados
pelos valores aprovados da fábrica corporativa. Aprovar issuer/serviços Sigstore
conforme a decisão de Security, sem copiar a policy do sandbox como autorização.

O [ADR-0002 — Modelo de confiança Sigstore](adr/0002-sigstore-trust-model.md)
formaliza essa decisão ainda PROPOSED, as raízes e os metadados expostos.
Repository GitHub privado muda o serviço de GitHub attestations, mas não
reconfigura automaticamente o Cosign direto. A avaliação inclui o envio do
predicate SPDX ao serviço Rekor, distinto do conteúdo persistido no log.

Permanecem **EXTERNAL — pendentes**: Corporate CA anchors; Corporate GitHub
protections; Corporate OIDC/IAM; Corporate ECR; Corporate egress/mirror;
Sigstore decision; Scanner/Veracode decision; external alert destination;
corporate SLA; first corporate E2E run. Owners e critérios estão na
[RFC-013](../RFC-013-Image-Base-Completa-com-Mermaid.md#prontidão-para-produção).

O isolamento Wolfi completo, quando exigido, é decisão corporativa com
Cloud/Network/Security (ver [readiness corporativo](corporate-production-readiness.md)).
Nenhum mirror, PKI, IAM ou enforcement de consumo é implementado por este
contrato. Aceites hospedados específicos não são inferidos de aprovação
local; consulte a tabela atual da RFC.

## Referências oficiais dos comandos

- [Cosign installer fixado: versão padrão](https://github.com/sigstore/cosign-installer/blob/6f9f17788090df1f26f669e9d70d6ae9567deba6/action.yml).
- [Cosign v3.0.6: verificação de attestations](https://github.com/sigstore/cosign/blob/v3.0.6/cmd/cosign/cli/verify/verify_attestation.go).
- [GitHub CLI: gh attestation verify e modelo de confiança](https://cli.github.com/manual/gh_attestation_verify).
- [GitHub CLI v2.96.0: política de identidade](https://github.com/cli/cli/blob/v2.96.0/pkg/cmd/attestation/verify/policy.go).
- [AWS CLI: autenticação ECR](https://docs.aws.amazon.com/cli/latest/reference/ecr/get-login-password.html).
- [AWS CLI: consulta de imagem/tag](https://docs.aws.amazon.com/cli/latest/reference/ecr/describe-images.html).
