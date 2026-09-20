Faça uma simplificação cirúrgica do fluxo de certificados da hardened-image factory.

OBJETIVO

Remover do `scripts/certificates/certificados.sh` a responsabilidade de baixar
e incorporar um bundle público Mozilla/curl que já é fornecido pela base Wolfi.

A factory deve continuar separando claramente:

PUBLIC TRUST
→ Wolfi `ca-certificates-bundle`

CORPORATE TRUST
→ certificados corporativos baixados/validados
→ `prepare_anchors.py`
→ Melange custom package
→ Apko composition

NÃO alterar a arquitetura geral de certificados além disso.

==================================================
CONTEXTO ATUAL
==================================================

Hoje o fluxo contém:

certificados.sh
→ baixa certificados corporativos de S3
→ baixa também `https://curl.se/ca/cacert.pem`
→ salva como `mozilla.crt`
→ inclui `mozilla.crt` em `EXPECTED_FILES`
→ valida/hash/pin
→ gera:
   - ca_bundle_interna.crt
   - ca_bundle_externa.crt

Depois:

prepare_anchors.py
→ recebe `ca_bundle_interna.crt`

Melange:
`melange/image-base-ca-certificates.yaml`
→ empacota somente os anchors corporativos

Apko:
`distroless/image-base.yaml`
→ instala:
   - `ca-certificates-bundle`
   - `image-base-ca-certificates`

E usa:

certificates:
  providers:
    - custom-ca-certificates

Portanto, o trust público já vem do Wolfi.

==================================================
DECISÃO
==================================================

Para a hardened-image factory:

MANUAL_MOZILLA_BUNDLE = REMOVE
WOLFI_CA_CERTIFICATES_BUNDLE = KEEP
CORPORATE_CA_PACKAGE = KEEP

O script deve passar a governar somente as CAs corporativas adicionais.

==================================================
1. AUDITAR ANTES DE ALTERAR
==================================================

Antes de modificar:

buscar no repo inteiro por:

- mozilla.crt
- ca_bundle_externa.crt
- curl.se/ca/cacert.pem
- ca_bundle_interna.crt
- certificados.sh
- prepare_anchors.py

Classificar cada referência como:

ACTIVE
TEST
DOC
HISTORICAL

STOP se `ca_bundle_externa.crt` tiver algum consumidor ativo real fora desse
fluxo.

Se não houver consumidor ativo:
prosseguir.

==================================================
2. ALTERAR certificados.sh
==================================================

Remover:

- download de `https://curl.se/ca/cacert.pem`
- criação de `mozilla.crt`
- `mozilla.crt` de `EXPECTED_FILES`
- inclusão de `mozilla.crt` no lockfile
- qualquer validação/hash específica dele
- geração de `ca_bundle_externa.crt`

Manter:

- download dos certificados corporativos de S3
- validação PEM
- notBefore/notAfter
- SHA-256 lockfile
- metadata revisável
- fail-closed
- `--pin`
- `ca_bundle_interna.crt`

==================================================
3. OUTPUT ESPERADO DO SCRIPT
==================================================

Após a mudança, o modo normal deve gerar apenas o bundle corporativo necessário:

ca_bundle_interna.crt

e manter o JSON/output necessário ao fluxo vigente, se ainda utilizado.

Não gerar:

mozilla.crt
ca_bundle_externa.crt

==================================================
4. PREPARE_ANCHORS
==================================================

Revisar:

scripts/certificates/prepare_anchors.py

Confirmar que ele já recebe somente:

ca_bundle_interna.crt

e que não depende de Mozilla/public bundle.

Esperado:

PREPARE_ANCHORS_CHANGE_REQUIRED = NO

Se houver comentário/documentação dizendo que o script externo ainda gera
bundle público, atualizar somente wording necessário.

==================================================
5. MELANGE
==================================================

Não alterar comportamento de:

melange/image-base-ca-certificates.yaml

Esperado:

Melange continua empacotando somente:

certificates/anchors/*.crt
manifest.json

e continua declarando:

provides:
  - custom-ca-certificates

Registrar:

MELANGE_CORPORATE_CA_ONLY = YES

==================================================
6. APKO
==================================================

Não remover:

ca-certificates-bundle

de:

distroless/image-base.yaml

Confirmar que continua:

packages:
  - ca-certificates-bundle
  - image-base-ca-certificates
  - tzdata

e:

certificates:
  providers:
    - custom-ca-certificates

Registrar:

PUBLIC_TRUST_SOURCE = WOLFI_CA_CERTIFICATES_BUNDLE
CORPORATE_TRUST_SOURCE = IMAGE_BASE_CA_CERTIFICATES

==================================================
7. TESTES
==================================================

Atualizar apenas os testes que validam o comportamento antigo do script.

Adicionar/ajustar testes para provar:

- `mozilla.crt` não é mais esperado
- `ca_bundle_externa.crt` não é mais gerado
- certificados corporativos continuam sendo baixados
- lockfile cobre exatamente os arquivos corporativos esperados
- alteração de bytes continua falhando
- PEM inválido continua falhando
- certificado expirado continua falhando
- certificado futuro continua falhando
- metadata continua consistente
- `prepare_anchors.py` continua aceitando o bundle corporativo
- mock/test CA continua bloqueada em release
- CA:TRUE/keyUsage continuam validados

==================================================
8. DOCS
==================================================

Atualizar documentação vigente que descreva:

Mozilla download manual
ou
ca_bundle_externa.crt

Explicar claramente:

Public CA trust is provided by Wolfi's `ca-certificates-bundle`.

The custom Melange package contains only reviewed corporate CA anchors.

Não mexer em evidência histórica/ADRs datados só para reescrever o passado.

==================================================
9. SEGURANÇA
==================================================

Garantir:

SECURITY_GATE_RELAXED = NO

A remoção do Mozilla manual NÃO significa reduzir validação.

Ela apenas remove duplicação de responsabilidade.

Separação final:

Wolfi
→ public roots

Corporate S3
→ corporate roots

==================================================
10. TESTES COMPLETOS
==================================================

Executar:

make test-unit
make test-integration
make lint-local
make lint-workflows
git diff --check

e broken-link check.

Se houver testes específicos de certificates, executar também diretamente.

==================================================
11. NÃO FAZER
==================================================

NÃO:

- remover `ca-certificates-bundle`
- mover trust público para o pacote Melange
- instalar certificados em runtime
- adicionar `update-ca-certificates` no runtime
- adicionar shell/package manager na imagem distroless
- alterar frameworks
- alterar publisher
- alterar ECR
- alterar IAM
- alterar Trivy
- alterar promotion/recovery

==================================================
12. RESULTADO ESPERADO
==================================================

MANUAL_MOZILLA_BUNDLE = REMOVED

MOZILLA_CRT = ABSENT

CA_BUNDLE_EXTERNA = ABSENT

CA_BUNDLE_INTERNA = PRESENT

PUBLIC_TRUST_SOURCE =
WOLFI_CA_CERTIFICATES_BUNDLE

CORPORATE_TRUST_SOURCE =
MELANGE_IMAGE_BASE_CA_CERTIFICATES

PREPARE_ANCHORS = PRESERVED

MELANGE_PACKAGING = PRESERVED

APKO_TRUST_INTEGRATION = PRESERVED

SECURITY_GATE_RELAXED = NO

BROKEN_DOC_LINKS = 0
TESTS = PASS

==================================================
13. GIT DELIVERY
==================================================

Branch:

refactor/remove-redundant-public-ca-bundle

Commit:

refactor: remove redundant public CA bundle

PR:

refactor: remove redundant public CA bundle

Não mergear automaticamente.

Quero revisar o diff antes.