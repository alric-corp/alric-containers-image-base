# HANDOFF — P1-09 + P1-10

- Repositório: alric-corp/alric-containers-image-base.
- Base: e3ed68259f66af41e8054a4c0ac29a54082ddd60 (origin/main consultada).
- Branch: docs/consumer-contract-rfc-refresh, sem commit novo.
- Objetivo: contrato canônico de consumo e RFC reconciliada com código/evidence.
- Entrega: 13 arquivos, somente Markdown e um teste documental; nenhum staging,
  commit/push/PR, alteração em controles técnicos ou em specs anteriores.
- T01–T05 concluídas. 300 unitários, 24 integração, seis documentais PASS;
  lint-local/shared/workflows, check_ai_context e diff PASS.
- Fontes, matriz, hashes e runs: [evidence.md](evidence.md).

## Decisões e limites

Stable é ponteiro mutável; build tag identifica release; OCI index digest é
identidade exata suportada para assinatura/provenance. SBOM é atestado no
índice e nos dois manifests; verificar não equivale a consumir ou instalar
enforcement. Os comandos estruturais espelham a policy atual; não houve nova
verificação autenticada contra ECR ou atribuição de SLSA level formal.

O catálogo tem 17 definições/16 automáticas/11 contratos diretos. Skips
not_required, incluindo -dev compilados e runtime sem par, não são PASS.
Isso foi documentado, não corrigido tecnicamente nesta fatia.

P1-01: hosted PASS no commit e3ed682, run 34768459323, go1-26 e go1-26-dev:
read_back_status=confirmed, candidate_digest == stable_digest_observed e
promoted=true preservados em artifact; detalhes na evidence. P1-02 e P1-03
continuam PENDING. Discovery/JWKS continua risco residual; snapshots antigos preservados.

Corporate CA anchors, GitHub protections, OIDC/IAM, ECR, egress/mirror,
Sigstore/scanner decision, alerta externo, SLA e primeiro E2E permanecem
EXTERNAL. enforce_admins false corresponde à decisão do sandbox.

## Próximo passo

Opus 5 MAX retornou APPROVE WITH MINOR CHANGES. O único finding LOW de
status P1-01 foi corrigido; encaminhar para re-revisão final. Não fazer commit,
push ou PR sem instrução posterior. Confirmar Git e o diff antes de continuar;
nenhuma auto-aprovação foi emitida.
