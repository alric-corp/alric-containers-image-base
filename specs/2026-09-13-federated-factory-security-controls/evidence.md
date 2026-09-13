# EVIDENCE — P1-06

Estado: ADR/spec e referências implementados e verificados localmente.
Decisões externas e revisão independente permanecem pendentes.

## Baseline e fontes

13/09/2026, macOS arm64. Árvore inicial limpa. Após fetch e fast-forward
local sem criar commit, main == origin/main ==
`a5f1c435eab545b28bf37f445ddd11c3ff5b3ff7` (merge PR #57, P1-05).
Shared conferido no checkout `7a9b055a462eeb8552d3404c26538b44e8ccd83f`.
Não foi encontrada spec/ADR P1-06 equivalente na árvore, nos nomes de branches
ou worktrees disponíveis; ADR-0003 estava livre.

Contexto lido: AGENTS, CLAUDE, Constitution, Capability Matrix, PROJECT e
WORKFLOW. A premissa está somente no
[ADR-0003](../../docs/adr/0003-controles-seguranca-workflows-federados.md#premissa-canônica-de-autoria-e-sustentação),
com origem no relato do responsável pelo projeto. Não foi criada referência
formal, ticket ou nova aprovação de autoria. PROJECT apenas aponta para o ADR;
AGENTS, CLAUDE e os demais adaptadores de IA permanecem inalterados.

## Reconstrução e uso das fontes

| Fonte | O que foi conferido / limite |
| --- | --- |
| [workflow.yml](../../.github/workflows/workflow.yml) e [validação](../../.github/workflows/validate-base-images.yml) | Orquestração própria, PR sem AWS, eventos autorizados, preflight e chamada shared por SHA com locked-build=true |
| Shared no SHA acima | Melange/Apko e scan nas duas arquiteturas; publicação de validated-oci somente após sucesso do scan; nenhuma alteração no shared |
| [scan_images.py](../../scripts/pipeline/artifacts/scan_images.py) | vuln/secret, severidades atuais, ignore-unfixed; JSON por arquitetura, rejeição de falhas/relatório ausente ou inválido/arquitetura divergente |
| [runtime_images.py](../../scripts/pipeline/runtime/runtime_images.py), [contract_evidence.py](../../scripts/pipeline/runtime/contract_evidence.py) | Plano de contratos, skips explícitos e binding de retry no mesmo run/revisão/digests; falha mais recente de producer impede fallback |
| [publicador](../../.github/workflows/build-base-images.yml), [verify_publication.py](../../scripts/pipeline/release/verify_publication.py) | Cópia OCI com preservação de digests, leitura da tag publicada e comparação de índice/plataformas; sem rebuild |
| [verify_promotion.py](../../scripts/pipeline/release/verify_promotion.py), [ADR-0002](../../docs/adr/0002-sigstore-trust-model.md) | Identidade/issuer/main e IDs certificados, provenance e limites atuais; aprovação corporativa Sigstore continua externa |
| [promoção](../../.github/workflows/promote-stable.yml), [verify_stable.py](../../scripts/pipeline/release/verify_stable.py), [recovery](../../.github/workflows/recover-stable.yml) | Re-scan, digest/read-back antes de declarar promoção, restauração sem bypass; a tag observada não é garantia eterna |
| [policy de saúde](../../policies/operations/health.json), [saúde operacional](../../docs/m11-m04-operational-health.md) | Owners de sandbox, retenção OCI 3d/evidence 30d, canal de run e external_destination=null; thresholds não são SLA corporativo |
| [contrato de reuso](../../docs/m09-m12-reusable-workflows.md) e [consumer contract](../../docs/consumer-verification-contract.md) | Responsabilidades técnicas do produto/shared e identidade de consumo; controles de aplicações não são delegados à fábrica |

O [snapshot P1-09/P1-10](../2026-09-13-consumer-contract-rfc-refresh/evidence.md)
e a [evidence P1-05](../2026-09-13-sigstore-trust-model-adr/evidence.md) foram
usados como evidência já registrada, limitada aos commits/runs citados.
Nenhuma consulta nova de AWS, build, scan real, signing, promoção ou retry
foi feita nesta fatia. P1-01 hosted PASS e P1-02/P1-03 PENDING preservados;
não se declara homologação ou disponibilidade corporativa a partir deles.

## Levantamentos corporativos: síntese sanitizada

Dois Markdown locais fornecidos pelo responsável foram lidos integralmente
por pesquisa auxiliar somente leitura, sem auditoria corporativa ou pesquisa
externa de produto. Permanecem fora deste repositório público:

- R1 — levantamento de build/publicação: descreve Trivy no fluxo de build,
  transporte/publicação e promoção. Foi usado para perguntas de interfaces,
  sem importar severidades, bypasses, cache, autenticação ou destinos.
- R2 — levantamento Veracode SCA de imagem/container: descreve seleção de
  alvo, análise de imagem/container, parsing/consolidação, status/policy e
  relatórios. Foi usado para identificar a necessidade de distinguir análise
  do candidato, fallback de modo, falha operacional e resultado de política.

Os fluxos são diferentes. R2 não torna Veracode obrigatório ou inaplicável
à fábrica, e R1 não homologa Trivy para este produto. Não foram inspecionados
os workflows corporativos executáveis nem sua versão/configuração vigente.
Os materiais não têm força de requisito obrigatório por si próprios.
Não foram copiados conteúdo integral, identificadores internos, destinos,
credenciais ou configurações desses materiais.

## Mudança documental

- ADR-0003: premissa canônica, quatro categorias, controles/fontes/limites,
  cinco distinções de scanner, interfaces condicionais, quatro responsáveis
  e seis perguntas somente sobre pendências para a validação de segunda-feira.
- RFC, README, índices, mapa do projeto e contrato de reuso apontam para o ADR.
- Histórico recebe apenas nota de escopo: o planejamento de migração de
  10/09 continua preservado como hipótese anterior, não obrigação vigente.
- Spec P1-06 nova porque não havia equivalente; nenhuma spec anterior alterada.
- Check de links existente inclui novo ADR e os seis arquivos da spec;
  não há parser novo nem teste que simule autorização/homologação.

## Verificação local

| Comando | Resultado |
| --- | --- |
| make test-unit | PASS, exit 0; 300 testes, 6,915s |
| make test-integration | PASS, exit 0; 24 testes, 11,860s |
| make lint-local | PASS, exit 0; 52 pins/49 arquivos e lote canônico |
| make lint-shared | PASS, exit 0; SHA/contrato shared, retenção e cron |
| make lint-workflows | PASS, exit 0; actionlint local e shared |
| python3 -B -m unittest tests.unit.pipeline.governance.test_consumer_documentation -v | PASS, exit 0; 6 testes, 0,095s, também incluídos nos 300 unitários |
| python3 -B tools/check_ai_context.py | PASS, exit 0 |
| git diff --check | PASS, exit 0 |

Logs locais: `/private/tmp/p106-{unit,integration,lint-local,lint-shared,lint-workflows,docs,context,diff}.log`.
Checks documentais e de contexto validam destinos locais, não autoridade de
uma decisão externa, anchors Markdown ou conteúdo de endpoints remotos.

Critérios semânticos A01–A09: inspeção de correspondência entre ADR, fontes e
pedido. A08/A10 também usam checks estruturais e escopo do diff. Verificação
do implementador não equivale a revisão independente.

## Arquivos da entrega

15 arquivos: ADR-0003; seis documentos desta spec; README, RFC, docs/README,
docs/adr/README, docs/ai/PROJECT, contrato de reuso e nota no histórico;
extensão do teste documental. Fora os novos documentos, o diff é somente
referências/qualificações e ampliação do conjunto de links testado.
Nenhuma spec anterior, implementação, gate ou policy foi alterada.

## Limites

Sem alteração de infraestrutura, scanner, código/gates, workflows ou policies.
Sem commit/push/PR. Consultas e síntese auxiliar somente leitura não são
revisão independente. Validação e aceite corporativos não executados.
AppSec/Segurança ainda deve confirmar os requisitos; Cloud/IAM/Network/PKI
deve prover recursos/acessos e seus aceites. Nenhuma pergunta pede novamente
autorização de autoria. Testes locais não substituem essas decisões externas.
