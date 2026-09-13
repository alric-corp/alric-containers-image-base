# EVIDENCE — P1-05

Estado: ADR e documentação implementados; verificação local registrada abaixo.
Decisão corporativa EXTERNAL / PROPOSED. Revisão independente PENDING.

## Baseline

13/09/2026, macOS arm64. main == origin/main ==
`44fac09718c63a4cdffd456e65ce21944ac6b11c` após fetch e fast-forward local
sem novo commit; PR #56 já integrado. Working tree inicial limpa.
Shared consumido: `7a9b055a462eeb8552d3404c26538b44e8ccd83f`.
AGENTS, CLAUDE, Constitution, Capability Matrix, PROJECT e WORKFLOW foram lidos.
Também foram lidos RFC, README, contrato de consumo, ADR-0001, workflows de
build/publish/promotion/recovery, helpers, policies e specs/evidence relacionadas.

## Identidade observada

API GitHub somente leitura: repository `alric-corp/alric-containers-image-base`,
ID `1360616627`, owner `alric-corp` ID `178685987`, visibility `public`,
default branch `main`; coincide com signing-identities.json.
Branch protection: test/lint-workflows, uma revisão, code owner,
dismiss_stale_reviews=true, enforce_admins=false, sem force-push/deletion.
O false é decisão autorizada do sandbox, não regressão nem prova corporativa.

## Reconstrução do comportamento atual

| Fonte canônica | Fato confirmado |
| --- | --- |
| [build-base-images.yml](../../.github/workflows/build-base-images.yml) | main/evento autorizado; OCI validado e contrato aplicável precedem cópia Skopeo por digest; read-back de publicação; Cosign sign; três SPDX attestations; provenance GitHub com push-to-registry |
| [publish_sboms.py](../../scripts/pipeline/release/publish_sboms.py) | SPDX original verificado, hash e subject vinculados ao OCI aprovado; cada documento atestado contra seu digest; subprocessos check=True |
| [verify_promotion.py](../../scripts/pipeline/release/verify_promotion.py) | índice exatamente amd64/arm64, Cosign SAN/issuer literal, gh repo/workflow/ref; IDs certificados e mesmo signer/digest, incluindo alias histórico restrito |
| [signing-identities.json](../../policies/release/signing-identities.json) | Nome/IDs atuais coincidem com API; alias alric-corp/itau-xj7-containers-image-base condicionado aos mesmos IDs |
| [promote-stable.yml](../../.github/workflows/promote-stable.yml), [recover-stable.yml](../../.github/workflows/recover-stable.yml) | Mesma verificação de origem, re-scan e read-back; nenhum gate específico de SBOM attestation |
| [Consumer Verification Contract](../../docs/consumer-verification-contract.md) | Índice como unidade suportada; comandos e limites; verificação recomendada não é enforcement em runtime |

Limites preservados: tag de build é escrita antes de signing, sem transação
ou rollback de publicação. Falhas de Cosign/attestations bloqueiam os passos
seguintes; não apagam artifacts já escritos. Promoção não exige mesmo run/commit
entre signature e provenance nem filtra explicitamente o tipo cosign/sign/v1
na saída do Cosign. Não foi adicionada nenhuma nova verificação.

O ADR-0002 estava livre. O índice ADR explicita que revisão/merge documental
não substitui aceite externo, evitando promover PROPOSED a decisão corporativa
por consequência da convenção genérica do ADR-0001.

## Fontes oficiais — consultadas em 13/09/2026

Somente documentação e código oficial; versões de cliente fixadas foram
priorizadas sobre descrições legadas. Referências de servidor explicam o
formato, não afirmam qual release binária o operador público executa.

| Fonte | Resultado relevante |
| --- | --- |
| [Installer no SHA consumido](https://github.com/sigstore/cosign-installer/blob/6f9f17788090df1f26f669e9d70d6ae9567deba6/action.yml) | default cosign-release=v3.0.6; workflow não sobrescreve |
| [Provenance action no SHA consumido](https://github.com/actions/attest-build-provenance/blob/4d101475d8b20a2381f78447822ac1eab6504dd8/action.yml) | Wrapper usa actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d; recebe subject/digest e push-to-registry |
| [GitHub: instâncias pública/privada](https://docs.github.com/en/actions/concepts/security/artifact-attestations) | PGI público com transparência; instância GitHub privada sem log e federada somente com Actions |
| [GitHub: requisitos](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations) | Private/internal requer Enterprise Cloud; não presumir suporte equivalente no GHES |
| [gh manual](https://cli.github.com/manual/gh_attestation_verify) | API GitHub por padrão, bundle-from-oci opcional; predicate SLSA v1 padrão; campos certificados distintos de conteúdo do predicate |
| [gh v2.100.0 verifier](https://github.com/cli/cli/blob/v2.100.0/pkg/cmd/attestation/verification/sigstore.go) | Default cria verificadores PGI e GitHub; TUF distinto; PGI SCT/log/observer timestamp, GitHub signed timestamp |
| [gh v2.100.0 flags](https://github.com/cli/cli/blob/v2.100.0/pkg/cmd/attestation/verify/verify.go) | no-public-good=false e custom-trusted-root vazio; essas opções não são usadas pelo projeto |
| [Sigstore security model](https://docs.sigstore.dev/about/security/) | CA, logs, TUF e limites de identidade/transparência |
| [Sigstore signing overview](https://docs.sigstore.dev/cosign/signing/overview/) | Audience sigstore, raízes distribuídas e configuração de serviços |
| [Cosign v3.0.6 sign options](https://github.com/sigstore/cosign/blob/v3.0.6/cmd/cosign/cli/options/sign.go), [attest options](https://github.com/sigstore/cosign/blob/v3.0.6/cmd/cosign/cli/options/attest.go) | new-bundle-format, use-signing-config e tlog-upload true por padrão |
| [Cosign signDigestBundle](https://github.com/sigstore/cosign/blob/v3.0.6/cmd/cosign/cli/sign/sign.go), [SPDX statement](https://github.com/sigstore/cosign/blob/v3.0.6/pkg/cosign/attestation/attestation.go) | Signature usa subject digest; attest incorpora SPDX como predicate; ambos seguem DSSE no caminho padrão |
| [Cosign signcommon](https://github.com/sigstore/cosign/blob/v3.0.6/cmd/cosign/cli/signcommon/common.go), [seleção de serviços](https://github.com/sigstore/cosign/blob/v3.0.6/pkg/cosign/bundle/sign.go) | Signing config/roots carregados por TUF; endpoints e material de confiança podem evoluir sem mudar pin do cliente |
| [sigstore-go v1.1.4](https://github.com/sigstore/sigstore-go/blob/v1.1.4/pkg/sign/transparency.go) | Envelope DSSE integral e certificado enviados ao Rekor v1/v2; inclui SPDX no caso de SBOM |
| [Rekor v1.5.1 DSSE](https://github.com/sigstore/rekor/blob/v1.5.1/pkg/types/dsse/v0.0.1/entry.go) | Canonicalize exclui envelope, guarda envelopeHash/payloadHash/signatures/verifier; não implementa storage auxiliar de attestation; indexa digests dos subjects |
| [Rekor v2.2.1 DSSE](https://github.com/sigstore/rekor-tiles/blob/v2.2.1/pkg/types/dsse/dsse.go) | Entrada DSSE v0.0.2 guarda payloadHash e assinaturas/verificadores; não predicate integral |
| [Fulcio v1.8.5 OIDs](https://github.com/sigstore/fulcio/blob/v1.8.5/docs/oid-info.md), [GitHub principal](https://github.com/sigstore/fulcio/blob/v1.8.5/pkg/identity/github/principal.go) | SAN/issuer, source/workflow/ref/digest/IDs, runner e run/attempt URI conforme claims |
| [Fulcio CT](https://github.com/sigstore/fulcio/blob/main/docs/ctlog.md) | Publicação de certificados distinta do Rekor; remover apenas tlog upload não elimina exposição de identidade |
| [Cosign KMS](https://docs.sigstore.dev/cosign/key_management/overview/) | AWS KMS é alternativa suportada, sem escolha ou implementação aqui |

A pesquisa inicial de gh v2.96.0 foi complementada pelo código v2.100.0 após
encontrar essa versão no artifact hospedado. A CLI não é pinada pelo projeto.
O endpoint de documentação Fulcio certificate-specification não respondeu
via browser; a fonte oficial versionada de OIDs/principal foi usada.

### Inferências explicitamente delimitadas

- Repository GitHub privado não muda defaults do comando Cosign independente:
  inferência dos dois caminhos separados, sem overrides no workflow.
- Transferência do SPDX ao serviço é distinta de publicação do predicate no
  log. Não afirmar que só hash sai do ambiente ou que o serviço não mantém
  nenhum log operacional; não foi feita auditoria interna do operador.
- A proposta de manter Sigstore público é uma recomendação do projeto
  condicionada à aprovação de dados/serviços, não fato normativo corporativo.

## Evidência hospedada existente — leitura, não nova execução

Consultas em 13/09/2026, aproximadamente 17:17 UTC. Nenhum build, assinatura,
attestation ou verificação criptográfica nova foi executado nesta fatia.

[Run 34735740791 / job 103667558521](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34735740791/job/103667558521),
commit `285ada4d6948c2d7e7508dd0ba8883c38306c7a1`, artifact
`publication-go1-26-1` ID `10311202090`: copy/sign/SPDX/provenance success;
Cosign v3.0.6; três SPDX attested=true, índice validado=copiado=remoto
`sha256:de811b47d076bdd93b411efba0edc6c0a3c58803be1833919e0146ef14e2c0d3`.

[Run 34768459323](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34768459323),
commit `e3ed68259f66af41e8054a4c0ac29a54082ddd60`, artifact
`promotion-scans-go1-26-1` ID `10320124242`: Cosign v3.0.6, gh 2.100.0;
índice `sha256:f658ed77f8734e1c3d218e07684f876f5cd38964afd79bb5c7a7c9e6571d339f`.
O certificado preservado registra OIDC issuer GitHub, SAN esperado, IDs
`1360616627`/`178685987`, CA `sigstore-intermediate/O=sigstore.dev`,
sourceRepositoryVisibilityAtSigning=public, buildSignerURI do reusable
build-base-images.yml e buildConfigURI do chamador workflow.yml. A execução
de origem é `34745870807/attempts/1`.

O bundle de **provenance da action GitHub** nessa amostra contém:

- mediaType `application/vnd.dev.sigstore.bundle.v0.3+json`;
- DSSE payloadType `application/vnd.in-toto+json`;
- tlog `kind=dsse`, `version=0.0.1`, URI `https://rekor.sigstore.dev`;
- logID `c0d23d6ad406973f9559f3ba2d1ca01f84147d8ffc5b8445c224f98b9591801d`,
  logIndex `2815401111`, integratedTime `1789285881`;
- corpo canonicalizado com `envelopeHash`, `payloadHash`, `signatures`;
  signature entries contêm `signature` e `verifier`, sem payload integral;
- payloadHash SHA-256 `de4284c5c6c27c11c1d940d48cb4854fe81daa6f147376b41fc2bc1b9e1b8db7`,
  recalculado dos bytes de dsseEnvelope.payload: igual ao hash do log,
  **diferente** do OCI index digest acima.

Esse bundle confirma o formato da provenance observada, não o endpoint/log
de todo comando Cosign. `signature.json` contém saída normalizada do Cosign,
sem tlog/bundle, com tipos SPDX, SLSA provenance e cosign/sign/v1 para o mesmo
índice. Isso reforça a nota do ADR: verify_promotion não filtra explicitamente
o tipo da assinatura dedicada. Não foi executado um negativo hospedado de
remoção dessa assinatura; não se infere seu resultado.

## Validação local

| Check | Resultado nesta fatia |
| --- | --- |
| make test-unit | PASS, exit 0; 300 testes, 5,500s, incluindo os seis documentais |
| make test-integration | PASS, exit 0; 24 testes, 11,758s |
| suíte documental explícita | PASS, exit 0; 6 testes, 0,114s |
| make lint-local | PASS, exit 0; 52 pins/49 arquivos, lote 17−1 |
| make lint-shared | PASS, exit 0; shared SHA/contrato e retenção/cron |
| make lint-workflows | PASS, exit 0; actionlint local e shared |
| python3 -B tools/check_ai_context.py | PASS, exit 0; estrutura, imports e links locais |
| git diff --check | PASS, exit 0 |

Logs locais: `/private/tmp/p105-{unit,integration,docs,lint-local,lint-shared,lint-workflows}.log`.
Contexto e diff: `/private/tmp/p105-{context,diff}.log`.
Os dois checks documentais existentes foram estendidos: links incluem ADR,
índice e nova spec; identidade confere policy/contrato e SAN/issuer/ref no ADR.
Os outros quatro testes de comandos/referências permanecem presentes.
Não há parser novo, chamadas AWS/GitHub em unit tests ou teste de texto que
pretenda provar trust criptográfico. Nenhum teste de produção foi removido.

Critérios A01–A10 inspecionados contra o ADR e fontes acima. A verificação
semântica pelo implementador não é aprovação arquitetural independente.

## Escopo e limites

Entrega: ADR-0002, seis documentos desta spec, referências em README,
docs/README, docs/adr/README, consumer contract e item Sigstore da RFC;
extensão do teste documental existente. Nenhuma outra spec foi alterada.
Workflows, scripts da fábrica, policies, shared repo, IAM/ECR/PKI/scanner e
signing/provenance/SBOM continuam inalterados.

P1-01 hosted PASS; P1-02/P1-03 PENDING, preservados. Não se declara novo hosted
PASS nesta fatia documental. Aceite corporativo e primeiro E2E permanecem
NOT RUN / EXTERNAL. Não foi validado um repository corporativo privado,
GHES, cenário offline ou indisponibilidade real de Sigstore.

## Revisão

Pesquisa auxiliar somente leitura com GPT-6-Astra, reasoning ULTRA.
Isso não é revisão arquitetural independente. Opus 5 MAX: PENDING.
Nenhum commit, push, PR, workflow dispatch ou alteração remota nesta fatia.
