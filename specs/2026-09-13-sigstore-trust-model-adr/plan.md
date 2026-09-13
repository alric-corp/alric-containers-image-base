# PLAN — P1-05

## Pesquisa

Confrontar main, signing-identities, publicador, verify_promotion, publish_sboms,
promotion/recovery, contrato de consumo, ADR-0001 e evidence existente.
Consultar fontes oficiais atuais e código fixado de Cosign/attest action para
resolver defaults e diferenças público/privado. Ler APIs GitHub somente para
confirmar identidade e governança; não publicar artifacts ou executar builds.

## Estratégia

1. Fixar a baseline observada e criar SPEC/aceite antes de redigir o ADR.
2. Usar o próximo número livre, ADR-0002, com decisão corporativa PROPOSED.
3. Acrescentar referências curtas no índice ADR, docs/README, README,
   contrato canônico e item Sigstore externo da RFC. Preservar históricos.
4. Estender checks documentais existentes para links/identidade do ADR e
   links da spec, sem parser novo ou controles da pipeline.
5. Executar checks solicitados, registrar fontes, resultados, limites e handoff.

## Decisões e hipóteses

Não deduzir detalhes de Rekor a partir de versões antigas: o installer
fixado e o caminho efetivo da versão governam a explicação. Distinguir
aprovação deste documento de aprovação externa de produção. A convenção do
índice ADR precisa explicitar essa diferença para decisões externas.

## Risco e rollback

Risco principal: overclaim de privacidade, identidade ou enforcement.
Mitigar com fontes primárias, limites explícitos e revisão independente.
Rollback é reverter apenas documentos/testes desta fatia; não há efeito no build.

## Validação

make test-unit; make test-integration; make lint-local; make lint-shared;
make lint-workflows; python3 -B tools/check_ai_context.py; git diff --check;
suíte documental existente. Registrar SHA do reusable exigido e exit codes.
Asserções de links/identidades são estruturais, não aceitação de trust roots.
