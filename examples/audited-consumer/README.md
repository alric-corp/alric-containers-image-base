# Consumo auditado das imagens base — exemplo para times consumidores

Este diretório é um exemplo **copiável** de como uma esteira consumidora aplica
o [contrato de consumo](../../docs/consumer-verification-contract.md) antes do
`FROM`: resolve a referência uma única vez, verifica assinatura, identidade e
provenance com os verificadores da Factory, fixa **o mesmo índice OCI** no
build multi-stage, executa os testes da aplicação e recusa (exit ≠ 0, sem
lock) qualquer evidência ausente, divergente ou inconclusiva.

Não é admission controller, não aprova a segurança da aplicação e não
substitui a política corporativa de consumo. A assinatura da base não assina
a imagem derivada e o SBOM da base não lista o que a aplicação acrescenta.

## Níveis de consumo

| Nível | O que o time faz | O que fica comprovado | O que **não** fica |
| --- | --- | --- | --- |
| Conveniência | `FROM .../image-base-<fw>:stable` | Nada sobre origem; dois builds podem usar índices diferentes | Não é consumo auditado |
| `simplified` | `verify-image.sh` sobre o digest (assinatura, SBOM attestation do índice, provenance por repo/workflow/ref) | Identidade exata do workflow, issuer e subject do índice | Plataformas exatas, IDs numéricos do repositório, commit/run aprovados, par runtime/-dev da mesma execução |
| `full-policy` | `verify_promotion` de um checkout revisado da Factory + SBOM attestation | Índice com exatamente amd64/arm64, assinatura e provenance da mesma identidade, IDs de repositório/owner, subject do statement, par runtime/-dev da mesma execução e, com release record, commit + run/attempt aprovados | Scan atual, ausência de CVEs, aprovação humana, SLSA level formal |

O record (`verification-record.json`) mostra cada verificação como `PASS`,
`NOT_CHECKED` ou `NOT_REQUESTED`; o nível simplificado nunca aparece como a
policy completa. `build-args --require-level full-policy` recusa um lock
simplificado.

## Arquivos

| Arquivo | Papel |
| --- | --- |
| `audited_consumer.py` | Gate (Python 3.9+, só biblioteca padrão, POSIX): `verify`, `check-dockerfile`, `build-args`, `record-consumption` |
| `consume.sh` | Fluxo completo e fail-closed: verify → Dockerfile → build com testes → smoke → evidência |
| `policy.example.json` | Identidade do sandbox (mesma do contrato) com dois placeholders que o gate recusa até serem preenchidos |
| `Dockerfile` | Multi-stage: testes e build na `-dev`, estágio final na runtime, bases só por build args sem default |
| `app/` | Aplicação Go mínima com testes (`go vet` + `go test` rodam dentro do build) |

## Pré-requisitos

- `aws`, `docker` com Buildx, `cosign` e `gh`, autenticados **somente para
  leitura** do ECR e das attestations do repositório de origem. O exemplo não
  cria roles, policies ou repositórios e não faz push.
- `full-policy`: checkout **revisado** da Factory no commit fixado em
  `factory_checkout_commit`, sem alterações locais. O gate confere `HEAD` e
  `git status` e importa `verify_promotion` exclusivamente desse checkout, em
  processo Python isolado (`-I`).
- Cópia de `scripts/verify-image.sh` desse mesmo commit, com o sha256 fixado em
  `verifier_script_sha256` (usada pelo `simplified` e pela SBOM attestation do
  `full-policy`). O gate executa uma cópia privada dos bytes conferidos.

Preencha os placeholders a partir do checkout revisado:

```sh
git -C <factory-checkout> rev-parse HEAD              # factory_checkout_commit
sha256sum <factory-checkout>/scripts/verify-image.sh  # verifier_script_sha256
```

Valores de registry, repositório e identidade do exemplo são os do sandbox,
iguais ao contrato. No corporativo, substitua-os pelos aprovados para a
fábrica corporativa; não copie a política do sandbox como autorização.

## Uso

Preferencial: digests de uma release aprovada (o gate não consulta tags):

```sh
examples/audited-consumer/consume.sh \
  --policy policy.json --out evidence/consumo \
  --release-record approved-release.json \
  --factory-checkout factory --verifier-script factory/scripts/verify-image.sh \
  --require-level full-policy
```

`approved-release.json` registra a release escolhida pelo time:

```json
{"schema_version": 1, "source_repository": "<owner>/<repo>",
 "source_sha": "<commit de 40 hex>", "run_id": 1, "run_attempt": 1,
 "images": {"go1-26": "sha256:<índice>", "go1-26-dev": "sha256:<índice>"}}
```

Com tag (`--runtime stable --build stable`), cada tag é resolvida **uma vez**
por `aws ecr describe-images`; o resultado fica no record e o restante do
fluxo usa só o digest. Se uma release record também for informada, tag e
release precisam apontar para o mesmo índice. O build nunca recebe a tag:
`build-args` lê somente o lock, e `check-dockerfile` recusa `FROM` por tag,
ARG com default, `COPY --from`/`--mount from=` de imagem externa e estágio
final que não seja a runtime.

Saídas em `--out`: `verification/verification-record.json`,
`verification/verified-bases.lock.json` (só quando `TRUSTED`),
`verification/evidence/` (saídas dos verificadores), `dockerfile-check.json`,
`image-id.txt`, `health.json`, `info.json` e `consumption-record.json`.
Publique esses JSON como artifact do job: o diagnóstico não depende de log.

### Esqueleto de job (GitHub Actions do consumidor)

```yaml
permissions: {contents: read, id-token: write}
steps:
  - uses: actions/checkout@<sha>          # repositório da aplicação
  - uses: actions/checkout@<sha>          # Factory revisada, no commit da política
    with: {repository: <owner>/<factory>, ref: <factory_checkout_commit>, path: factory, persist-credentials: false}
  - uses: aws-actions/configure-aws-credentials@<sha>  # role de LEITURA do ECR (owner Cloud/IAM)
  - run: |
      aws ecr get-login-password | docker login --username AWS --password-stdin "$REGISTRY"
      examples/audited-consumer/consume.sh --policy policy.json --out evidence \
        --release-record approved-release.json --factory-checkout factory \
        --verifier-script factory/scripts/verify-image.sh --require-level full-policy
  - if: always()
    uses: actions/upload-artifact@<sha>
    with: {name: consumo-auditado, path: evidence/**/*.json}
```

## Contrato de segurança

O gate garante, ou recusa:

1. Cada referência vira um único digest, registrado com método e horário.
2. A verificação usa exatamente esse digest; uma confirmação de outro digest é
   `DIGEST_MISMATCH`.
3. A identidade declarada na política (issuer, workflow, ref) precisa ser a
   aplicada pelo verificador escolhido; caso contrário `POLICY_NOT_ENFORCEABLE`.
   Issuer, workflow e repositório nunca são regex.
4. `full-policy`: o statement de provenance verificado tem o índice como
   subject; com release record, commit (`--source-digest`) e run/attempt
   (`invocationId`) são os aprovados; runtime e `-dev` vêm da mesma execução.
5. Lock e record são gravados só quando tudo passa; o lock fixa o hash do
   record e `build-args` recusa divergências (`LOCK_TAMPERED`).
6. Timeout, ferramenta ausente, saída vazia ou erro inesperado encerram o grupo
   de processos e bloqueiam; nada vira sucesso por omissão.

Não garante: segurança da aplicação, resultado do scan atual, ausência de
CVEs, aprovação humana, retenção do digest no registry (veja o lifecycle do
ambiente) nem atualização de imagens já implantadas. Lock e record protegem
contra edição acidental e referência trocada no mesmo job; quem controla o
runner e o repositório da esteira continua na raiz de confiança.

## Diagnósticos

| Código | Significado | Ação |
| --- | --- | --- |
| `POLICY_INVALID`, `POLICY_PLACEHOLDER` | Política incompleta, com campo desconhecido ou placeholder | Corrigir a política revisada (exit 2) |
| `POLICY_NOT_ENFORCEABLE` | Identidade declarada não é a aplicada pelo verificador | Alinhar com a Factory; não ampliar por regex |
| `PAIR_INCOMPATIBLE` | Build não é `<runtime>-dev` ou a final é `-dev` | Usar o par da mesma família/versão |
| `REFERENCE_INVALID`, `INPUT_MISSING` | Referência não é tag/digest ou falta base | Informar tag, digest ou release record |
| `TAG_RESOLUTION_FAILED` | Tag ausente, erro ou mais de um digest | Usar digest aprovado |
| `DIGEST_MISMATCH` | Tag, release e verificador divergem | Investigar; não trocar para a tag |
| `FACTORY_CHECKOUT_UNTRUSTED`, `VERIFIER_SCRIPT_UNTRUSTED` | Verificador fora do commit/hash revisados | Recriar checkout limpo no commit fixado |
| `VERIFIER_UNAVAILABLE`, `VERIFIER_TIMEOUT`, `VERIFIER_FAILED` | Ferramenta ausente, lenta ou com falha | Corrigir ambiente; repetir não é aprovação |
| `INDEX_UNAVAILABLE` | Índice não lido no registry | Acesso ECR/rede; digest expirado pelo lifecycle |
| `SIGNATURE_REJECTED` | Assinatura ausente ou de outro issuer/workflow/ref | Não usar a imagem |
| `PROVENANCE_REJECTED`, `PROVENANCE_SUBJECT_MISMATCH`, `PROVENANCE_RELEASE_MISMATCH` | Provenance ausente, de outro repositório/IDs/commit, outro subject ou outra execução | Não usar; conferir a release aprovada |
| `SBOM_ATTESTATION_REJECTED`, `INSUFFICIENT_EVIDENCE`, `PLATFORM_SET_INVALID` | Evidência faltando ou índice sem exatamente amd64/arm64 | Não usar |
| `PAIR_RELEASE_MISMATCH` | Runtime e `-dev` de execuções diferentes | Escolher o par da mesma release |
| `LOCK_INVALID`, `LOCK_TAMPERED`, `LEVEL_INSUFFICIENT` | Lock alterado ou abaixo do nível exigido | Repetir `verify` |
| `DOCKERFILE_*` | `FROM` fora do lock, default, imagem externa, final não-runtime, frontend sem digest, `ADD` remoto sem checksum | Corrigir o Dockerfile |
| `BUILD_FAILED` | Build ou testes da aplicação falharam com as bases verificadas | Corrigir a aplicação/compatibilidade |

## Critérios de aceite de um consumidor auditado

- Execução positiva com `--require-level full-policy`: record `TRUSTED`,
  `consumption-record.json` `PASS` e o mesmo `image_ref` (registry, repositório
  e `@sha256`) no record, no lock e nos build args do build.
- Negativos executados pelo próprio time, no ambiente real, todos recusados
  sem lock: issuer/workflow/ref errados na política, digest de outra release,
  release record com run/commit diferentes e `FROM` por tag.
- Atualização da base exige nova verificação, novo lock, testes e decisão de
  deploy do time; o pin não acompanha correções futuras.

## Plano de homologação com consumidor independente

1. **Escolha:** um time consumidor que não participou da autoria da Factory,
   uma aplicação real com par runtime/`-dev` e uma release aprovada.
2. **Preparação pelo time:** política preenchida com os valores aprovados do
   ambiente, checkout revisado da Factory, role de leitura (owner Cloud/IAM).
3. **Positivo:** `consume.sh` na esteira do time; artifacts JSON preservados.
4. **Negativos:** os quatro casos do critério de aceite, mais a tag movida
   entre verificação e build (o build deve continuar no digest verificado).
5. **Revisão:** AppSec revisa política, record, lock e Dockerfile sem depender
   do autor da Factory; Containers Products só responde dúvidas.
6. **Aceite:** registrado por AppSec e pelo time consumidor, com o run e os
   hashes dos JSON. Sem esse aceite, o estado continua “exemplo testado
   localmente”, não consumo auditado comprovado.

## Limites conhecidos

- `verify_promotion` aplica issuer GitHub, workflow `build-base-images.yml` e
  `refs/heads/develop` de forma fixa; outro issuer corporativo exige mudança
  revisada nesse verificador, não na política do consumidor.
- Resolução de tag só para ECR; outros registries exigem digest.
- SBOM attestation verificada no índice; inventário por plataforma segue o
  contrato (`cosign verify-attestation` por digest de plataforma).
- `consume.sh` usa Docker/Buildx; outras esteiras podem chamar só
  `audited_consumer.py` (verify, check-dockerfile, build-args).
