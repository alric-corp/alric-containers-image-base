# Documentação

| Necessidade | Documento |
| --- | --- |
| Trabalhar com Codex, Claude Code e Copilot | [Guia de engenharia com IA](ai/README.md) |
| Estudar os fundamentos do domínio (Wolfi, apko, Melange, Sigstore, admission) | [Fundamentos](fundamentals/00-README.md) |
| Escolher e verificar uma base por digest | [Consumer Verification Contract](consumer-verification-contract.md) |
| Construir imagens e consultar exemplos | [README do produto](../README.md) |
| Localizar responsabilidades e dependências | [Arquitetura](repository-architecture.md) |
| Preparar ambiente e validar uma mudança | [Contribuição](../CONTRIBUTING.md) |
| Entender contratos com o executor compartilhado | [Workflows reutilizáveis](m09-m12-reusable-workflows.md) |
| Entender a renomeação e a confiança AWS | [Migração de nomes](repository-rename.md) |
| Consultar o diagnóstico histórico de liberação | [Snapshot de 10/09/2026](release-readiness-2026-09-10.md) |
| Entender CAs, timezone, camadas, replay e SBOMs | [Composição](image-composition.md) |
| Consultar políticas executáveis | [Políticas](../policies/README.md) |
| Consultar decisões pontuais e seu estado | [ADRs](adr/README.md) |
| Avaliar raízes, metadados e adoção corporativa do Sigstore | [ADR-0002 — Sigstore Trust Model (PROPOSED)](adr/0002-sigstore-trust-model.md) |
| Distinguir autoria, controles e requisitos corporativos da fábrica federada | [ADR-0003 — P1-06](adr/0003-controles-seguranca-workflows-federados.md) |
| Consultar a V1 de referência Go 1.26 (escopo, catálogo preservado) | [ADR-0004](adr/0004-v1-referencia-go126.md), [fechamento operacional](v1-reference-closure-2026-09-16.md) |
| Consultar `stable`/lifecycle restaurados conforme a RFC-013 | [ADR-0005](adr/0005-stable-lifecycle-realinhamento-rfc013.md) |
| Consultar o bloqueio de scan do Java 21 (zlib) e opções de remediação | [ADR-0006 — decisão do Tech Lead pendente](adr/0006-java21-zlib-blocker-remediation-options.md) |
| Avaliar permissões AWS, templates e aceite IAM futuro | [Contrato IAM — P1-04, proposta não aplicada](iam-permission-contract.md) |
| Preparar configuração e aceite do destino corporativo | [Pacote de adoção — P0-03, execução externa pendente](corporate-adoption.md) |
| Operar a fábrica e avaliar alertas, indicadores e proposta de SLO/SLA | [Contrato operacional — M11/M04/P1-08](m11-m04-operational-health.md) |
| Revisar signing key Wolfi e rotação | [Wolfi signing-key defense-in-depth](wolfi-signing-key.md) |
| Recuperar stable | [Runbook de recuperação](../README.md#recuperação-de-stable-runbook-m15) |
| Entender gates e hardening | [Inventário de gates](m12-gate-inventory.md), [revisão M09–M16](m09-m16-review.md) |
| Consultar a decisão sobre cache | [Política de cache](m09-m16-cache-policy.md) |
| Executar contratos de imagens reais | [Runtime](../tests/runtime/README.md) |
| Consultar proposta, estado e prontidão para produção | [RFC-013](../RFC-013-Image-Base-Completa-com-Mermaid.md) |
| Consultar aceites, entregas e achados de cada etapa | [Histórico da RFC-013](rfc-013-historico-de-entregas.md) |
| Auditar resultados históricos | [Evidências](evidence/), [fechamento do checklist](old-checklist-closure.md) |
| Planejar a migração para o repositório corporativo | [Manifesto de migração corporativa](corporate-migration-manifest.md) |

Documentos históricos e evidências usam os nomes atuais dos repositórios
(o GitHub redireciona as URLs antigas de qualquer forma); a exceção é a
evidência criptográfica de assinatura, que preserva o nome vigente no momento
da assinatura (ver [Migração de nomes](repository-rename.md)). Os JSON em
`evidence/` descrevem as execuções e commits registrados; não são
configuração ativa nem comprovam o estado atual do produto.
