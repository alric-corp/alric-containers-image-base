# HANDOFF — P0-03

Baseline main 3af67d47869b6370f72fcfad1d16cde673cb7f57, PR #60 integrado.
Objetivo em [spec.md](spec.md), plano em [plan.md](plan.md).
Repositório sandbox alric-corp/alric-containers-image-base, branch main.
Pacote local implementado e verificado, ainda sem staging/commit;
revisão independente posterior pelo Claude Code permanece pendente.

## Entrega e verificação

[Pacote canônico](../../docs/corporate-adoption.md): 20 parâmetros/dependências,
sequência A–G e checklist CA-01–18 com execução e aceite separados. Há somente
referências incrementais no README/RFC/índice e extensão do teste documental
existente. Os onze arquivos e as fontes estão em [evidence.md](evidence.md).
T01–T05 concluídas; os critérios A01–A08 são de preparação local, não execução
do destino. T06/revisão independente ainda não realizada.

Checks desta fatia: 323 unitários PASS (incluem 6 documentais), 24 integrações
PASS após repetir o teste com socket TLS fora da restrição do sandbox;
lint-local, lint-shared, lint-workflows/actionlint, check_ai_context e diff
--check PASS. O erro de ambiente inicial e a repetição estão na evidence.
Nenhum resultado AWS ou corporativo foi produzido.

## Decisões e próximos passos

Autoria do ADR-0003 preservada; requisitos de scanner, Sigstore, IAM, PKI,
rede, retenção e operação continuam sujeitos a decisões próprias. IAM atual
exige execution + provisioning; pré-provisionamento sozinho não remove a
chamada de mutabilidade, e publisher pode mover stable. Templates não aplicados.
Consumo continua por OCI index digest; evidence não é enforcement.

A próxima fatia técnica recomendada é **P0-03 — Portabilidade da origem da
biblioteca compartilhada**: resolvedor/callers/checkout/action coerentes com
origem aprovada e SHA exato. Acesso privado e runner distinto são dependências
condicionais, não credenciais ou privilégios autorizados por este documento.
Nenhum ajuste técnico foi iniciado. PKI real precisa de insumos/endpoints
autorizados; fixtures sintéticas não comprovam o aceite corporativo.

P1-01 mantém hosted PASS limitado; P1-02/P1-03 PENDING. P1-04 mantém validações
AWS/laboratório NOT RUN e aceite corporativo EXTERNAL_PENDING. P1-08 mantém
canal/envio/entrega/ACK, responsáveis e acordo pendentes; seus gaps de
indicadores, resumo e scheduler não foram corrigidos. CA-01–18: NOT RUN.

Para continuar: Claude Code deve ler instruções/spec, conferir o diff completo
incluindo novos arquivos, critérios e fontes, e realizar a revisão independente.
Não assumir que o pacote concede autorização para execução das etapas A–G.

Preservar contratos IAM/consumo/operação/ADRs, políticas, implementação da
fábrica e biblioteca. Não operar destinos externos nem criar commit/push/PR
sob a autorização desta sessão. Pacote não é aprovação de implantação,
recursos, IAM, serviços de transparência, canal operacional ou SLA.
