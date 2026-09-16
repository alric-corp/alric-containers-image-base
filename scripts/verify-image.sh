#!/bin/bash
#
# Verificação externa de consumo — transforma em script o que
# docs/consumer-verification-contract.md descreve em comandos manuais.
# Roda de fora do CI: nenhuma etapa depende de contexto interno do GitHub
# Actions (job outputs, secrets do pipeline, artifacts do run). As únicas
# entradas são o que qualquer consumidor autorizado já tem: credenciais AWS
# próprias com permissão de leitura no ECR de destino, e as três CLIs
# abaixo.
#
# O que este script prova, e o que NÃO prova:
#   - Prova que o digest consumido tem uma assinatura Cosign keyless válida
#     emitida pela identidade exata do workflow de build na main, uma
#     attestation SBOM SPDX válida sobre esse mesmo digest, e uma provenance
#     SLSA v1 verificável vinculada ao mesmo subject digest.
#   - NÃO prova ausência de vulnerabilidades, aprovação humana, ou que o
#     scan atual (Trivy) passaria se rodasse de novo agora. Assinatura e
#     provenance atestam origem e processo de build, não conteúdo seguro.
#   - NÃO decide "estável"/"aprovado para produção" por si só — isso é uma
#     decisão de quem consome, documentada em docs/consumer-verification-contract.md.
#
# V1_REFERENCE_IDENTITY = OCI_DIGEST: a forma suportada de referenciar uma
# release nesta V1 de referência é por digest do índice OCI multiarch
# (repository@sha256:<digest>), não pela tag "stable" -- que está fora de
# escopo (STABLE = OUT_OF_SCOPE). Uma tag de build imutável também é
# aceita; o script resolve a tag para o digest antes de verificar.
#
# Uso:
#   scripts/verify-image.sh <framework> <tag-ou-digest> \
#     --account <aws-account-id> [--region <aws-region>] \
#     [--repo <owner/repositorio-fonte>] [--ref <branch-do-assinador>]
#
# Exemplo (Go 1.26, digest já comprovado em execução real no sandbox):
#   scripts/verify-image.sh go1-26 \
#     sha256:6582880f48e9374df03b241c28242c28772086fef50ebcaf87e03662f95916bc \
#     --account 712107929769 --region us-east-1
#
# Dependências: aws, docker (login), cosign, gh (autenticado com
# `read:packages`/attestations públicas do repositório fonte).
# O preflight abaixo falha cedo e com mensagem clara se alguma faltar.
#
# Saída: 0 se as três verificações passarem; != 0 na primeira que falhar.
# Nenhuma etapa modifica o registry, o repositório fonte ou qualquer estado
# remoto -- leitura e verificação apenas.

set -euo pipefail

FRAMEWORK=""
REF="tag-ou-digest-nao-informado"
AWS_ACCOUNT_ID=""
AWS_REGION="us-east-1"
SOURCE_REPO="alric-corp/alric-containers-image-base"
SIGNER_REF="refs/heads/main"

usage() {
  echo "Uso: $0 <framework> <tag-ou-digest> --account <aws-account-id> [--region <aws-region>] [--repo <owner/repositorio>] [--ref <ref-do-assinador>]" >&2
  exit 2
}

[[ $# -ge 2 ]] || usage
FRAMEWORK="$1"; shift
REF="$1"; shift

while [[ $# -gt 0 ]]; do
  case "$1" in
    --account) AWS_ACCOUNT_ID="$2"; shift 2 ;;
    --region) AWS_REGION="$2"; shift 2 ;;
    --repo) SOURCE_REPO="$2"; shift 2 ;;
    --ref) SIGNER_REF="$2"; shift 2 ;;
    *) echo "argumento desconhecido: $1" >&2; usage ;;
  esac
done

[[ "$FRAMEWORK" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || { echo "framework inválido: $FRAMEWORK" >&2; exit 2; }
[[ -n "$AWS_ACCOUNT_ID" ]] || { echo "--account é obrigatório: nenhuma conta é assumida por padrão" >&2; exit 2; }
[[ "$AWS_ACCOUNT_ID" =~ ^[0-9]{12}$ ]] || { echo "--account deve ter 12 dígitos: '$AWS_ACCOUNT_ID'" >&2; exit 2; }

check_dependencies() {
  local missing=""
  for cmd in aws docker cosign gh; do
    command -v "$cmd" >/dev/null 2>&1 || missing="$missing $cmd"
  done
  if [[ -n "$missing" ]]; then
    echo "dependências ausentes:$missing" >&2
    exit 3
  fi
}
check_dependencies

REPOSITORY="image-base-${FRAMEWORK}"
REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
SIGNER_WORKFLOW="${SOURCE_REPO}/.github/workflows/build-base-images.yml"
CERT_IDENTITY="https://github.com/${SIGNER_WORKFLOW}@${SIGNER_REF}"
OIDC_ISSUER="https://token.actions.githubusercontent.com"

echo "== Resolvendo digest =="
if [[ "$REF" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  DIGEST="$REF"
  echo "referência já é um digest: $DIGEST"
else
  # Mesma validação do contrato de consumo: tag ausente, erro, ou múltiplos
  # digests não satisfazem -- `--output text` de um único digest, ou falha.
  DIGEST=$(aws ecr describe-images \
    --region "$AWS_REGION" \
    --registry-id "$AWS_ACCOUNT_ID" \
    --repository-name "$REPOSITORY" \
    --image-ids "imageTag=${REF}" \
    --query 'imageDetails[].imageDigest' --output text)
  [[ "$DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]] || {
    echo "tag '$REF' não resolveu para exatamente um digest válido (obtido: '$DIGEST')" >&2
    exit 4
  }
  echo "tag '$REF' -> $DIGEST"
fi

IMAGE_REF="${REGISTRY}/${REPOSITORY}@${DIGEST}"
echo "referência completa: $IMAGE_REF"

echo
echo "== Login no ECR (necessário para cosign/gh lerem o registry) =="
aws ecr get-login-password --region "$AWS_REGION" |
  docker login --username AWS --password-stdin "$REGISTRY" >/dev/null

FAILED=""

echo
echo "== 1/3 Verificando assinatura Cosign keyless =="
if cosign verify \
  --certificate-identity "$CERT_IDENTITY" \
  --certificate-oidc-issuer "$OIDC_ISSUER" \
  "$IMAGE_REF" >/tmp/verify-image-signature.json 2>&1; then
  echo "PASS: assinatura válida (identidade ${CERT_IDENTITY})"
else
  echo "FAIL: assinatura -- ver /tmp/verify-image-signature.json"
  FAILED="${FAILED}signature "
fi

echo
echo "== 2/3 Verificando attestation SBOM (SPDX) =="
if cosign verify-attestation \
  --type spdxjson \
  --certificate-identity "$CERT_IDENTITY" \
  --certificate-oidc-issuer "$OIDC_ISSUER" \
  "$IMAGE_REF" >/tmp/verify-image-sbom.json 2>&1; then
  echo "PASS: attestation SBOM (spdxjson) válida"
else
  echo "FAIL: attestation SBOM -- ver /tmp/verify-image-sbom.json"
  FAILED="${FAILED}sbom "
fi

echo
echo "== 3/3 Verificando provenance SLSA (build attestation) =="
if gh attestation verify "oci://${IMAGE_REF}" \
  --repo "$SOURCE_REPO" \
  --signer-workflow "$SIGNER_WORKFLOW" \
  --source-ref "$SIGNER_REF" \
  --predicate-type https://slsa.dev/provenance/v1 \
  --format json >/tmp/verify-image-provenance.json 2>/tmp/verify-image-provenance.err; then
  echo "PASS: provenance SLSA v1 válida (repo=${SOURCE_REPO}, ref=${SIGNER_REF})"
else
  echo "FAIL: provenance -- ver /tmp/verify-image-provenance.err"
  FAILED="${FAILED}provenance "
fi

echo
if [[ -z "$FAILED" ]]; then
  echo "RESULTADO: PASS -- ${IMAGE_REF}"
  echo "Assinatura, SBOM attestation e provenance verificados. Isto não é"
  echo "aprovação de segurança nem declaração de nível SLSA formal -- ver"
  echo "docs/consumer-verification-contract.md para o que cada verificação"
  echo "cobre e o que continua sendo decisão de quem consome."
  exit 0
else
  echo "RESULTADO: FAIL -- verificações reprovadas: ${FAILED}"
  echo "Não use esta imagem como base até identificar e corrigir a causa."
  exit 1
fi
