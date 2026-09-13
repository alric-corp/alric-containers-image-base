# HANDOFF — P1-05

- Baseline: main `44fac09718c63a4cdffd456e65ce21944ac6b11c`.
- Objetivo: ADR do trust model existente, sem redesenho ou novos controles.
- Pasta: [spec.md](spec.md), [aceite](acceptance.md), [plano](plan.md).
- Estado: ADR PROPOSED e referências implementados; testes/lints/contexto/diff PASS;
  consultar [evidence.md](evidence.md) para resultados finais e fontes.
- Revisão arquitetural independente: Opus 5 MAX, pendente.
- Decisão corporativa: Segurança/AppSec, EXTERNAL / PROPOSED.
- Autorização desta sessão: documentação/testes; sem commit/push/PR.

## Entrega

[ADR-0002](../../docs/adr/0002-sigstore-trust-model.md), esta spec e referências
mínimas em README/RFC/docs/contrato de consumo; testes documentais existentes
estendidos para links/identidade. Pipeline, policies, signing, provenance,
SBOM e infraestrutura permanecem inalterados.

## Pontos para a revisão arquitetural

- Cosign v3.0.6 usa DSSE: predicate SPDX enviado ao serviço Rekor; log guarda
  hashes/assinaturas/verificadores, não o predicate integral. CT de Fulcio
  também expõe metadados. Não prometer confidencialidade perante o serviço.
- Instância privada GitHub de attestations não reconfigura Cosign direto.
  gh aceita raízes PGI/GitHub por padrão; valores corporativos não definidos.
- Promoção usa Cosign+gh com mesmo signer/digest/main e IDs certificados;
  não exige mesmo run/commit entre ambos, não tem gate SBOM nem filtro
  explícito de tipo cosign/sign/v1. Documentar limitações não altera controles.
- Falha pode deixar build tag/evidence parcial no ECR; não há rollback nem
  fallback que dispense verificação. O índice continua unidade suportada.
- PROPOSED persiste após eventual merge documental até aprovação externa
  explícita. Option A é recomendação condicionada; Option B não implementada.

## Pendências

Verificação local: 300 unitários, 24 integração, seis documentais; lint-local,
lint-shared, lint-workflows (actionlint), check_ai_context e diff --check PASS.
São verificações da entrega local, não aceite corporativo ou auto-aprovação.

Opus 5 MAX: revisão independente desta entrega, sem auto-aprovação.
Segurança/AppSec: aceitar ou rejeitar serviços/metadados/processamento SPDX,
raízes e identidade corporativa. P0-03/PKI/rede/IAM/ECR/scanner/alerta/SLA/E2E
permanecem externos. P1-01 hosted PASS; P1-02/P1-03 PENDING preservados.

Próximo passo: revisão arquitetural independente, seguida de autorização
específica antes de staging/commit/push/PR. Nenhuma issue externa foi aberta.

Confirme Git e diff antes de continuar. Nenhum aceite corporativo decorre
da conclusão local ou do futuro merge documental.
