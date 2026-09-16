# EVIDENCE — P1-09 + P1-10

Estado: documentação implementada e verificada localmente; pronta para revisão independente.
Revisão independente Opus 5 MAX: APPROVE WITH MINOR CHANGES. Único finding
LOW corrigido nesta rodada; re-revisão final pendente. Sem commit/push/PR.

## Baseline e escopo

13/09/2026, macOS arm64. Após fetch somente leitura, origin/main era
`e3ed68259f66af41e8054a4c0ac29a54082ddd60` (merge PR #55, P1-02).
A branch `docs/consumer-contract-rfc-refresh` partiu dessa HEAD com árvore limpa.
P1-01/P1-03 já estavam integrados. Shared consumido:
`7a9b055a462eeb8552d3404c26538b44e8ccd83f`; nenhum arquivo do shared foi alterado.

Contexto persistente lido: AGENTS, CLAUDE, Constitution, Capability Matrix,
PROJECT e WORKFLOW. RFC, README, arquitetura/composição/release, policies,
ADR-0001, specs/evidence existentes, workflows e scripts foram confrontados.
Pesquisa paralela somente leitura usou GPT-6-Astra, reasoning ULTRA, para
comandos oficiais e matriz de controles; isso não é revisão independente.

## Drift confirmado e corrigido

- RFC de 10/09 dizia main incapaz de publicar por rename/Skopeo/permissions;
  código e runs recentes mostram publicações individuais bem-sucedidas.
- Contagens antigas misturavam catálogo com inventário ECR: catálogo atual
  tem 17 definições e lote 16, não uma prova de 17 releases/stables disponíveis.
- README alegava camada única; configuração origin/budget 10 permite até 11
  camadas no Apko fixado. Mecanismo de CAs/lock/SPDX já havia evoluído.
- README usava regex ampla, identidade genérica antiga e tag stable para
  verificação. Contrato canônico usa índice resolvido uma vez e policy vigente.
- RFC/README alegavam enforce_admins ativo. Decisão persistente e API confirmam
  false no sandbox; exigência corporativa continua P0-03.
- Contratos são condicionais: 11 diretos, seis interpretados/cinco compilados.
  -dev compilado não tem gate próprio; runtime compilado sem par/dotnet8
  recebem not_required, passed:null. Não foram adicionados gates nesta fatia.
- Retenção atual é OCI 3 dias; Melange, SBOM e relatórios 30 dias.
- P1-01/02/03 foram acrescentados sem confundir código integrado com aceite.
  P1-03 conserva risco residual de repository key discovery/JWKS.
- Pin antigo da biblioteca substituído nas referências atuais; snapshots
  históricos e specs anteriores permanecem preservados.

## Matriz de controles da main

IMPLEMENTED = presente no código identificado, não homologação corporativa.
PARTIAL = cobertura/aceite/operação com lacuna explícita. EXTERNAL = decisão
ou implantação fora do produto. DEFERRED = trabalho técnico posterior.

| Controle | Estado | Fonte atual / limite |
| --- | --- | --- |
| Apko/Melange composition | IMPLEMENTED | [build_image.py](../../scripts/pipeline/artifacts/build_image.py), [receita Melange](../../melange/image-base-ca-certificates.yaml); lock e data do commit |
| Multiarch amd64 + arm64 | IMPLEMENTED | [base](../../distroless/image-base.yaml), [OCI verify](../../scripts/pipeline/artifacts/oci_artifact.py); índice com ambas plataformas |
| tzdata | IMPLEMENTED | base e [probes/runtime](../../scripts/pipeline/runtime/runtime_images.py); regras históricas de São Paulo testadas |
| Integrated CA mechanism | IMPLEMENTED | [prepare_anchors](../../scripts/certificates/prepare_anchors.py), [image trust](../../.github/workflows/image-trust.yml); perfil public, CA de teste isolada |
| Corporate CA anchors | EXTERNAL | manifesto real aprovado ausente; MOCK rejeitado para release |
| Runtime / -dev | PARTIAL | [catálogo](../../frameworks/); dotnet8 conserva SDK e não tem par |
| Trivy per architecture | IMPLEMENTED | [scan_images.py](../../scripts/pipeline/artifacts/scan_images.py); vuln/secret, ignore-unfixed e severidades preservadas |
| Functional contracts | PARTIAL | [plano e gate](../../scripts/pipeline/runtime/runtime_images.py); 11 contratos diretos, skips condicionais explícitos |
| Build Once / Promote Many | IMPLEMENTED | [publicador](../../.github/workflows/build-base-images.yml); Skopeo --all --preserve-digests, sem rebuild/repack |
| OCI digest verification | IMPLEMENTED | [verify_publication](../../scripts/pipeline/release/verify_publication.py); validado, copiado e bytes remotos comparados |
| ECR immutable build tags | IMPLEMENTED | publicador configura IMMUTABLE_WITH_EXCLUSION, stable como única exceção; inventários antigos datados |
| Stable promotion | IMPLEMENTED | [promote-stable](../../.github/workflows/promote-stable.yml), [seletor](../../scripts/pipeline/release/find_promotion_candidate.py) |
| Stable read-back P1-01 | IMPLEMENTED / hosted PASS | [verify_stable](../../scripts/pipeline/release/verify_stable.py); igualdade confirmada para Go/runtime e -dev no run 34768459323, conforme correção LOW abaixo |
| Cosign keyless signing | IMPLEMENTED | publicador assina índice; [verify_promotion](../../scripts/pipeline/release/verify_promotion.py) aplica identidade/issuer |
| GitHub provenance | IMPLEMENTED | publicador + verify_promotion + [IDs](../../policies/release/signing-identities.json); subject índice, sem SLSA level formal |
| SBOM attestations | IMPLEMENTED | [publish_sboms](../../scripts/pipeline/release/publish_sboms.py); SPDX originais índice/amd64/arm64, cada um no próprio digest |
| Soak | IMPLEMENTED | default 6h, input manual validado; não é invariável de todo dispatch nem canário de tráfego |
| Promotion re-scan | IMPLEMENTED | mesmo digest nas duas arquiteturas, sem bypass |
| Recovery | IMPLEMENTED | [recover-stable](../../.github/workflows/recover-stable.yml); mesma verificação, re-scan, retag/read-back; quarentena exige PR explícito |
| Partial retry P1-02 | IMPLEMENTED / aceite PARTIAL | [contract_evidence](../../scripts/pipeline/runtime/contract_evidence.py); same-run/index/revision, producer original/latest success; rerun real pendente |
| Wolfi signing-key defense-in-depth | IMPLEMENTED | [wolfi_trust](../../scripts/pipeline/governance/wolfi_trust.py), [pin_inventory](../../scripts/pipeline/governance/pin_inventory.py), [runbook](../../docs/wolfi-signing-key.md); sem confiança exclusiva |
| dotnet8 default-batch exclusion | IMPLEMENTED | [default_batch](../../scripts/pipeline/catalog/default_batch.py), [health policy](../../policies/operations/health.json), [ADR-0001](../../docs/adr/0001-dotnet8-fora-do-lote-padrao.md) |
| Pipeline health | PARTIAL | [health workflow](../../.github/workflows/pipeline-health.yml); cron/fila/idade/pins/drift; external_destination null, SLA externo |
| Corporate GitHub/OIDC/IAM/ECR/PKI/egress | EXTERNAL | reprovar no ambiente real; sandbox não transfere autorização nem aceite |
| Sigstore/scanner decision, alerta/SLA corporativos, primeiro E2E | EXTERNAL | owners/aceites preservados na RFC |
| ARM nativo, enforcement/admission, separação dotnet8 | DEFERRED | nenhuma implementação nesta fatia |

Contagens obtidas por `python3 -B -m scripts.pipeline.catalog.default_batch list`
e `python3 -B -m scripts.pipeline.runtime.runtime_images --list`:
17 definições / 1 exclusão / lote 16; 11 contratos diretos. O default manual
[go1-26] não inclui seu par e não executa contrato compilado; o documento
não transforma esse skip em PASS.

## Observações hospedadas existentes — somente leitura

Consultas em 13/09/2026, aproximadamente 04:44–04:48 UTC; nenhum workflow foi
disparado, reexecutado ou alterado por esta entrega.

[Run 34735740791](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34735740791),
HEAD 285ada4, attempt 1, failure agregado. Publicadores Go
[job 103667558521](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34735740791/job/103667558521)
e [-dev 103667558498](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34735740791/job/103667558498)
concluíram cópia, Cosign, três SPDX attestations e provenance com success.

| Artifact de publicação | ID | Índice validado = copiado = remoto |
| --- | --- | --- |
| publication-go1-26-1 | 10311202090 | sha256:de811b47d076bdd93b411efba0edc6c0a3c58803be1833919e0146ef14e2c0d3 |
| publication-go1-26-dev-1 | 10311077554 | sha256:d76b9d6bad633f227d277d8614f18ae636c0eceb066aef4b6c58168123180242 |

O [preflight Wolfi 103666725783](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34735740791/job/103666725783)
passou com SHA esperado/observado
`f0031424cf46f7db780ce63a45f0fd6aa6f85f601e6bb3b7a91fe3d4d5b7d2cc`.
O lock preservado no artifact publicado referencia
`melange/keys/wolfi-signing.rsa.pub`. Isso é evidência posterior observada do
caminho mínimo hospedado P1-03, sem exclusividade de trust, aprovação formal
ou extrapolação para lote inteiro. As specs originais NOT RUN não foram alteradas.

[Run da baseline 34738421104](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34738421104),
HEAD e3ed682, attempt 1, estava in_progress na última consulta. O contrato Go
já havia passado; isso não comprova retry. [Fast checks 34738419433](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34738419433)
estava success. Não se atribui resultado final posterior sem consulta.

Amostra de scan da baseline: `build-scans-nodejs22-1`, ID 10311821968, duas
arquiteturas com exit 1, CVE-2026-85091/zlib MEDIUM, 1.3.2-r5 → 1.3.3-r0.
Não houve nova consulta ao APKINDEX nem extrapolação da amostra a todo framework.
Incidente upstream e ausência consequente de artifacts/contratos ficam separados.

Na consulta inicial de 04:44–04:48 UTC, não havia sido localizado o aceite
hospedado P1-01. A evidência posterior confirmada abaixo substitui essa
pendência. Nenhum rerun entre attempts do P1-02 foi observado.

Branch protection main, API somente leitura: checks test/lint-workflows,
uma revisão, code owner requerido, descarte de aprovações antigas; strict=false,
require_last_push_approval=false, enforce_admins=false, force-push/deletion=false.
Isso confirma a decisão explícita do sandbox, sem alterar configuração remota.

## Correção do finding LOW — P1-01 hosted PASS

A revisão independente apontou evidence posterior à consulta inicial.
Reconsulta somente leitura confirmou o commit
`e3ed68259f66af41e8054a4c0ac29a54082ddd60`, attempt 1, no
[run principal 34768459323](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34768459323).
Para `go1-26` (job `103753567614`) e `go1-26-dev` (job `103753567547`),
seleção, verificação de plataformas/assinatura/provenance, re-scan,
`Promote to stable`, `Confirm stable via independent ECR read-back` e
`Preserve promotion outcome` concluíram com success.

Os arquivos `promotion-evidence.json` dos artifacts foram baixados e lidos:

| Artifact | ID | candidate_digest == stable_digest_observed |
| --- | --- | --- |
| promotion-go1-26-1 | 10320328866 | sha256:f658ed77f8734e1c3d218e07684f876f5cd38964afd79bb5c7a7c9e6571d339f |
| promotion-go1-26-dev-1 | 10321237217 | sha256:c7484452cae8da2a37c313adf1a8c55be599512a397ad99f2133e87b871b36a4 |

Ambos registram `promoted=true` e `read_back_status=confirmed`. Isso satisfaz
P1-01: candidato verificado → re-scan → escrita → read-back independente →
igualdade → promoção confirmada → evidence preservada. O run agregado tem
failure em outros frameworks; o PASS aqui é do aceite P1-01 observado nesses
dois frameworks. A garantia continua limitada ao instante do read-back.
Nenhum workflow foi disparado ou alterado nesta rodada. P1-02 e P1-03 seguem
PENDING, sem inferência de aceite a partir destes artifacts.

Reverificação após a correção LOW: `make test-unit` (300, 5,485s),
`make test-integration` (24, 11,843s), testes documentais explícitos (6, 0,087s),
`make lint-local`, `make lint-shared`, `make lint-workflows`,
`python3 -B tools/check_ai_context.py` e `git diff --check`: todos PASS, exit 0.
Logs desta rodada: `/private/tmp/p109-low-{unit,integration,docs,lint-local,lint-shared,lint-workflows,context,diff}.log`.
O snapshot anterior confirma que só README, RFC, evidence, acceptance e handoff
mudaram nesta rodada; código, testes e contrato de consumo ficaram intactos.

## Comandos e fontes oficiais

O contrato lista fontes oficiais de Cosign, GitHub CLI e AWS. A pesquisa
conferiu o installer fixado (Cosign v3.0.6), fontes do verificador Cosign
v3.0.6 e manual/fontes do gh v2.96.0. Ferramentas locais observadas: Cosign
v3.1.3, gh 2.96.0; gh do CI é fornecido pelo runner e registrado em evidence.

- Cosign usa certificate identity exata do workflow main e issuer GitHub.
- gh usa repo, signer-workflow, source-ref e predicate SLSA v1 explícito.
  --signer-workflow não é igualdade literal de SAN; --cert-identity é opção
  mutuamente exclusiva, não foi combinada no exemplo.
- verify_promotion existente acrescenta índice/plataformas e IDs certificados,
  com compatibilidade histórica por IDs, sem regex aberta.
- verify-attestation spdxjson valida cada subject; extração ocorre somente
  depois do sucesso, a partir dos envelopes verificados. SBOM não é provenance.
- Consulta stable resolve uma única vez; digest inválido/ausente/ambíguo falha.
  Não se publica nem move tag nos exemplos do contrato.

Não houve execução autenticada destes comandos de consumidor nem novo pull,
build, assinatura, attestation, promoção ou recuperação nesta fatia. A validação
local de comandos é estrutural, com mocks somente no subprocesso externo.

## Verificação local

Checks executados em 13/09/2026 sobre o diff local desta spec:

| Check | Resultado |
| --- | --- |
| make test-unit | PASS, exit 0; 300 testes, 5,375s (inclui os seis documentais novos) |
| make test-integration | PASS, exit 0; 24 testes, 11,569s |
| make lint-local | PASS, exit 0; 52 pins/49 arquivos e lote canônico |
| make lint-shared | PASS, exit 0; contrato fixado, hardening e retenção |
| make lint-workflows | PASS, exit 0; actionlint dos workflows mantidos e shared |
| python3 -B tools/check_ai_context.py | PASS, exit 0 |
| git diff --check | PASS, exit 0 |
| testes documentais direcionados | PASS; seis testes offline |

Logs: `/private/tmp/p109-{unit,integration,lint-local,lint-shared,lint-workflows,context,diff}.log`.
O teste documental valida links de arquivos locais (não anchors/HTTP remoto),
sintaxe dos blocos Bash sem executá-los, IDs da policy, pin compartilhado,
argv reais de signature/provenance capturados do verificador e tipo/subject/
identidade SBOM capturados do publicador. Nenhum parser Markdown genérico foi criado.

Os últimos ajustes após a suíte completa foram texto/diagramas e registro de
resultados. Conferência documental/contexto/diff repetida na finalização.
Nenhum arquivo de produção, policy, workflow, catálogo ou spec anterior mudou.

## Arquivos da entrega

13 arquivos: RFC-013, README, docs/README, docs/repository-architecture,
docs/m09-m12-reusable-workflows, novo docs/consumer-verification-contract,
novo tests/unit/pipeline/governance/test_consumer_documentation.py e seis
documentos desta spec. Todos os arquivos modificados pertencem à fatia.
Não houve staging, commit, push, PR ou alteração remota.

## Limites e próximos aceites

Documentação não instala enforcement nem atribui aprovação corporativa.
P1-01: hosted acceptance PASS, conforme run 34768459323. P1-02: PENDING.
P1-03: PENDING; observação anterior do caminho Go não foi promovida a aceite.
P1-09/P1-10: APPROVE WITH MINOR CHANGES recebido; finding LOW corrigido e
re-revisão final pendente. Nenhum novo workflow foi executado nesta rodada.
CAs/proteções/OIDC/IAM/ECR/egress/Sigstore/scanner/alerta/SLA/primeiro E2E
corporativos continuam EXTERNAL.
