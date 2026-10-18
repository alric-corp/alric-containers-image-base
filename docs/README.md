# Documentação

Porta de entrada da documentação do produto. O estado atual vem primeiro; em
seguida, cada domínio indica o documento canônico (primeira linha da tabela) e
os complementares. Documentos históricos ficam no fim, com data ou baseline, e
não descrevem a operação vigente.

## Estado atual

Baseline: `develop` em `a90f57623aea70482e7fc1b6396473316a0c8182`, leituras de
13/10/2026 no LAB (conta `712107929769`). A linha DEV `stable` foi relida em
15/10/2026, com `develop` em `90f10b91c4c814d25a204323fb39b9f21c4fe494`, e
completada com os recibos dos builds seguintes, lidos no GitHub com `develop`
em `01e95afd064193366be790eeb193e56a4a0ff572`.

| Domínio | Estado | Fonte |
| --- | --- | --- |
| Catálogo | 16 definições em `frameworks/`. O build automático publica somente o golden path `go1-26`/`go1-26-dev`; o catálogo completo é certificado por dispatch | [README](../README.md#imagens-disponíveis), [certificação do catálogo](catalog-certification.md) |
| Suporte | Go 1.25 (`go1-25`, `go1-25-dev`) sem suporte upstream desde 19/08/2026; decisão do owner pendente | [Suporte do catálogo](catalog-support.md) |
| DEV `stable` | Recuperado em 15/10/2026: par Go 1.26 na release `r38705617503-a1`, sem pausas e com marca d'água `[38705617503, 1]`, conferido por leitura independente; o incidente de 01/10/2026 foi encerrado e a automação DEV voltou a valer. No mesmo dia, o job `approve` dos builds `38784464692` e `38785513761` registrou promoções automáticas para `r38784464692-a1` e `r38785513761-a1`, ainda sem confirmação independente | [Registro do incidente](dev-hom-promotion.md#incidente-de-dev-stable-de-01102026-encerrado) |
| HOM | Promoção habilitada pela policy (`"enabled": true`); a elegibilidade de cada release continua sujeita ao soak de 6 h e aos gates técnicos do lifecycle. Os jobs `promote` e `recover` usam o Environment `HOM`, que exige aprovação de um revisor humano antes de executar (Settings lidos em 17/10/2026); um run agendado à espera de aprovação não autoriza a promoção. Aceite hospedado G07 de promoção e recovery não executado; operação automática contínua (M2) não aprovada | [DEV → HOM](dev-hom-promotion.md), [modos M1/M2](dev-hom-hosted-acceptance.md#16-modos-operacionais) |
| Retenção ECR | Build tags expiram em 7 dias; somente a imagem com `stable` é protegida; janela corporativa não definida | [Retenção no ECR](ecr-retention.md) |
| IAM | DEV e `Infra - Apply` usam a role central desde 10/10/2026. Os grants sobre o bucket SBOM histórico foram removidos e o state local de `infra/iam` foi reconciliado (serial 8, fora do Git) em 13/10/2026 | [Role central](factory-distroless-v1-iam-runbook.md), [reconciliação IAM](sbom-analytics-migration.md#reconciliação-iam) |
| SBOM Analytics | Prova hospedada S3 + Athena encerrada (rodada `sbom-analytics-v1-r1`). O workgroup e o database históricos ainda existem, sem uso operacional; a remoção depende de autorização | [Operação](sbom-analytics-operations.md), [migração](sbom-analytics-migration.md) |
| HGC-04 | `TEST_ONLY`: núcleo offline testado, sem custódia produtiva integrada | [Custódia de evidências](hgc04-evidence-custody.md) |
| Corporativo | Não homologado; o LAB é a implementação de referência | [Corporate Production Readiness](corporate-production-readiness.md) |

## Portal para consumidores

O portal Docusaurus foi movido para o repositório privado
[alric-containers-docs-external](https://github.com/alric-corp/alric-containers-docs-external).
Acesso exige permissão no repositório. O código do portal e os comandos de build
ficam na raiz do novo repositório; os contratos e runbooks da fábrica continuam aqui.

## Produto e catálogo

| Necessidade | Documento |
| --- | --- |
| Escolher uma imagem, construir localmente e consultar exemplos | [README do produto](../README.md) |
| Saber se uma variante ainda tem suporte e para onde migrar | [Suporte do catálogo](catalog-support.md) |
| Certificar o catálogo completo | [Certificação do catálogo](catalog-certification.md) |
| Certificar com aplicações consumidoras reais | [Certificação de aplicações](consumer-app-certification.md) |

## Arquitetura

| Necessidade | Documento |
| --- | --- |
| Localizar responsabilidades, domínios e dependências | [Arquitetura do repositório](repository-architecture.md) |
| Entender CAs, timezone, camadas, replay e SBOMs | [Composição das imagens](image-composition.md) |
| Entender contratos com o executor compartilhado | [Workflows reutilizáveis](repository-architecture.md#fronteira-entre-produto-e-workflows-compartilhados) |
| Entender por que distroless não é sinônimo de hardened | [RFC-013 — O que significa "hardened"](../RFC-013-Image-Base-Completa-com-Mermaid.md#o-que-significa-hardened) |

## Build e release

| Necessidade | Documento |
| --- | --- |
| Lifecycle DEV → HOM, pausas, retomada e recovery | [DEV → HOM por release](dev-hom-promotion.md) |
| Preparar o aceite hospedado DEV → HOM e recovery | [Aceite hospedado DEV → HOM](dev-hom-hosted-acceptance.md) |
| Configurar promoção, soak e escopo | [Configuração da Factory](../policies/pipeline/README.md) |
| Saber por quanto tempo um digest fica disponível no ECR e o que pode ser recuperado | [Retenção no ECR](ecr-retention.md) |
| Recuperar `stable` em HOM | [Runbook de recuperação](../README.md#recuperação-de-stable-runbook-m15) |
| Consultar o modelo operacional do golden path | [ADR-0008](adr/0008-modelo-operacional-lab-golden-path.md), [ADR-0004](adr/0004-v1-referencia-go126.md) |

## Segurança e supply chain

| Necessidade | Documento |
| --- | --- |
| Escolher e verificar uma base por digest | [Consumer Verification Contract](consumer-verification-contract.md) |
| Revisar a signing key Wolfi e sua rotação | [Wolfi signing-key defense-in-depth](wolfi-signing-key.md) |
| Avaliar raízes, metadados e adoção do Sigstore | [ADR-0002 — Sigstore Trust Model](adr/0002-sigstore-trust-model.md) |
| Entender a custódia de evidências HGC-04 (`TEST_ONLY`) | [Custódia de evidências](hgc04-evidence-custody.md) |
| Consultar as políticas executáveis | [Políticas](../policies/README.md) |

## IAM e infraestrutura

| Necessidade | Documento |
| --- | --- |
| Conferir a role operacional central e seu contrato | [Factory Distroless V1 — IAM externo](factory-distroless-v1-iam-runbook.md) |
| Avaliar permissões AWS, templates e aceite IAM | [Contrato IAM](iam-permission-contract.md) |
| Validar a identidade nativa dos workflows e portar para outra organização | [Identidade de execução e portabilidade](workflow-identity-portability.md) |
| Operar o Terraform de ECR e S3, seus gates e read-back | [Infra](../infra/README.md) |

## SBOM Analytics

| Necessidade | Documento |
| --- | --- |
| Operar o snapshot S3 e as consultas Athena, com os nomes ativos | [Distroless SBOM Analytics — operação](sbom-analytics-operations.md) |
| Entender a projeção SPDX e o protocolo de ingestão | [Projeção offline](sbom-analytics.md), [ingestão](sbom-analytics-ingestion.md) |
| Acompanhar a substituição e a remoção da estrutura histórica | [Distroless SBOM Analytics — migração](sbom-analytics-migration.md) |
| Conferir permissões do operador Athena | [Runbook IAM do Athena](sbom-analytics-athena-iam-runbook.md) |

## Operação e incident response

| Necessidade | Documento |
| --- | --- |
| Operar a fábrica e avaliar alertas, indicadores e SLO/SLA | [Contrato operacional](m11-m04-operational-health.md) |
| Consultar o evento de alerta, entrega e reconhecimento | [Contrato operacional de alertas](operational-alerting-contract.md) |
| Diagnosticar uma imagem distroless em execução | Toolkit `alric-containers-troubleshooting` (produto independente) |
| Executar os contratos sobre imagens reais | [Runtime](../tests/runtime/README.md) |

## Readiness corporativo

| Necessidade | Documento |
| --- | --- |
| Readiness da implementação de referência e roteiro de port | [Corporate Production Readiness](corporate-production-readiness.md) |
| Saber o que copiar para o ambiente corporativo | [Corporate file manifest](corporate-file-manifest.md) |
| Entender autoria, controles e requisitos da fábrica federada | [ADR-0003](adr/0003-controles-seguranca-workflows-federados.md) |

## Governança, RFC e ADRs

| Necessidade | Documento |
| --- | --- |
| Consultar decisões pontuais e seu estado | [Índice de ADRs](adr/README.md) |
| Revisão, ownership e required checks (LAB e corporativo) | [Governança do repositório](repository-governance.md) |
| Consultar `stable`/lifecycle conforme a RFC-013 | [ADR-0005](adr/0005-stable-lifecycle-realinhamento-rfc013.md) |
| Consultar proposta, estado e prontidão para produção | [RFC-013](../RFC-013-Image-Base-Completa-com-Mermaid.md) |
| Comparar esta solução com a POC de referência | [RFC-013 — Relação com a POC](../RFC-013-Image-Base-Completa-com-Mermaid.md#relação-com-a-poc-de-referência) |

## Desenvolvimento

| Necessidade | Documento |
| --- | --- |
| Preparar ambiente e validar uma mudança | [Contribuição](../CONTRIBUTING.md) |

## Histórico

Registros datados. Não use como runbook do fluxo atual; quando divergirem do
estado acima, vale o estado acima.

| Documento | Data ou baseline | O que registra |
| --- | --- | --- |
| [Incidente de DEV `stable`](dev-hom-promotion.md#incidente-de-dev-stable-de-01102026-encerrado) | 01/10 a 15/10/2026 | Escrita incompleta, divergência entre `state` e ECR, pausas do par Go 1.26 e recuperação autorizada (run 38759851987) |
| [Migração de branch do LAB](develop-as-dev.md) | Setembro de 2026 | Migração para `develop` e retirada da autorização de `main` |
| [Preflight da role central](factory-central-role-preflight.md), [cutover da role central](factory-central-role-cutover.md) | PRs #120 e #121, 09–10/10/2026 | Revisões que levaram DEV e Infra para a role central |
| [POC LAB do SBOM Analytics](sbom-analytics-lab-poc.md), [rodada Athena da POC](sbom-analytics-athena-lab-poc.md) | Até 11/10/2026 | Estrutura e rodada `lab-sbom-athena-v1` encerradas; os nomes não são operacionais |
| [Planejamento `TODO/`](../TODO/README.md) | 21–28/09/2026 | Plano de ativação corporativa, engine anterior de promoção por unidade e análises |
| [Visão para o time](../README-TIME-1.md), [visão de produto](../README-TIME-2.md) | 28/09/2026 | Explicação do produto para o time |
| [Proposta DEV → HOM](../homologation.md) | 29/09/2026 | Proposta que orientou o lifecycle por manifesto |
| [Sustentabilidade e automação](../ANALISE-SUSTENTABILIDADE-E-AUTOMACAO.md), [lacunas de pipeline health](../DUVIDAS-PIPELINE-HEALTH.md) | 02/10/2026 | Análises e decisões daquela data |
| [Roteiro de coleta corporativa](../collect.md) | 09/10/2026 | Instruções de um levantamento corporativo |
