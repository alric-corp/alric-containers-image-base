# Documentação

Porta de entrada da documentação do produto. Cada seção responde a uma
necessidade concreta; o histórico do desenvolvimento está no histórico Git,
não nesta árvore.

## Architecture

| Necessidade | Documento |
| --- | --- |
| Localizar responsabilidades, domínios e dependências | [Arquitetura do repositório](repository-architecture.md) |
| Entender por que distroless não é sinônimo de hardened | [RFC-013 — O que significa "hardened"](../RFC-013-Image-Base-Completa-com-Mermaid.md#o-que-significa-hardened) |
| Entender CAs, timezone, camadas, replay e SBOMs | [Composição das imagens](image-composition.md) |
| Entender contratos com o executor compartilhado | [Workflows reutilizáveis](m09-m12-reusable-workflows.md) |

## Consumer

| Necessidade | Documento |
| --- | --- |
| Escolher e verificar uma base por digest | [Consumer Verification Contract](consumer-verification-contract.md) |
| Construir imagens e consultar exemplos | [README do produto](../README.md) |

## Operations

| Necessidade | Documento |
| --- | --- |
| Operar a fábrica e avaliar alertas, indicadores e SLO/SLA | [Contrato operacional](m11-m04-operational-health.md) |
| Recuperar `stable` | [Runbook de recuperação](../README.md#recuperação-de-stable-runbook-m15) |
| Consultar a V1 de referência Go 1.26 e seu fechamento | [ADR-0004](adr/0004-v1-referencia-go126.md), [fechamento operacional](v1-reference-closure-2026-09-16.md) |

## Security

| Necessidade | Documento |
| --- | --- |
| Revisar a signing key Wolfi e sua rotação | [Wolfi signing-key defense-in-depth](wolfi-signing-key.md) |
| Avaliar raízes, metadados e adoção do Sigstore | [ADR-0002 — Sigstore Trust Model](adr/0002-sigstore-trust-model.md) |
| Avaliar permissões AWS, templates e aceite IAM | [Contrato IAM](iam-permission-contract.md) |
| Consultar as políticas executáveis | [Políticas](../policies/README.md) |

## Troubleshooting

| Necessidade | Documento |
| --- | --- |
| Diagnosticar uma imagem distroless em execução | [Toolkit de troubleshooting](../troubleshooting/README.md) |
| Executar os contratos sobre imagens reais | [Runtime](../tests/runtime/README.md) |

## Governance / ADRs

| Necessidade | Documento |
| --- | --- |
| Consultar decisões pontuais e seu estado | [Índice de ADRs](adr/README.md) |
| Entender autoria, controles e requisitos da fábrica federada | [ADR-0003](adr/0003-controles-seguranca-workflows-federados.md) |
| Consultar a investigação do bloqueio de scan do Java 21 (zlib) e sua resolução | [ADR-0006 — resolvido pelo fix upstream do Wolfi](adr/0006-java21-zlib-blocker-remediation-options.md) |
| Consultar `stable`/lifecycle conforme a RFC-013 | [ADR-0005](adr/0005-stable-lifecycle-realinhamento-rfc013.md) |
| Readiness da implementação de referência e roteiro para port/validação no ambiente corporativo | [Corporate Production Readiness](corporate-production-readiness.md) |
| Preparar configuração e aceite do destino corporativo | [Pacote de adoção](corporate-adoption.md) |
| Planejar a migração para o repositório corporativo | [Manifesto de migração](corporate-migration-manifest.md) |

## RFC

| Necessidade | Documento |
| --- | --- |
| Consultar proposta, estado e prontidão para produção | [RFC-013](../RFC-013-Image-Base-Completa-com-Mermaid.md) |
| Comparar esta solução com a POC de referência | [RFC-013 — Relação com a POC](../RFC-013-Image-Base-Completa-com-Mermaid.md#relação-com-a-poc-de-referência) |

## Development

| Necessidade | Documento |
| --- | --- |
| Preparar ambiente e validar uma mudança | [Contribuição](../CONTRIBUTING.md) |
| Trabalhar com Codex, Claude Code e Copilot | [Guia de engenharia com IA](ai/README.md) |
| Estudar os fundamentos do domínio | [Fundamentos](fundamentals/00-README.md) |

Os JSON em `evidence/` descrevem execuções e commits registrados nas datas
indicadas; não são configuração ativa nem comprovam o estado atual do produto.
