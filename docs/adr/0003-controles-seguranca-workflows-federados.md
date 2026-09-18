# ADR-0003 — Controles de segurança da fábrica em workflows federados

| Informação | Valor |
| --- | --- |
| Fatia | P1-06 |
| Data / baseline | 13/09/2026; main `a5f1c435eab545b28bf37f445ddd11c3ff5b3ff7` |
| Estado do ADR | **PROPOSED quanto aos requisitos e aceites corporativos ainda abertos** |
| Autoria/sustentação | Premissa definida abaixo, informada pelo responsável pelo projeto |
| Responsável pela fábrica | Containers Products |
| Decisões externas | AppSec/Segurança e owners de infraestrutura, conforme competência |

## Premissa canônica de autoria e sustentação

O responsável pelo projeto informou que o **Tech Lead autorizou Containers
Products a utilizar workflows federados, de autoria, manutenção e
responsabilidade do próprio time**. Para esta fábrica, não há obrigação de
adotar os workflows governados mantidos por Pipelines. A origem desta
informação é o relato do responsável, registrado nesta entrega; não foi
fornecido ticket ou documento formal para citar. Não se inventa aprovação
documental nem se reabre essa autorização.

**Federado descreve responsabilidade pelo workflow. Não é federação de
identidade OIDC.** A autorização não dispensa requisitos de AppSec, auditoria,
IAM, PKI, rede ou homologação corporativa. O estado PROPOSED deste ADR se
refere a essas decisões externas ainda abertas, não à premissa de autoria.

## Contexto e decisão desta fatia

A fábrica já possui controles próprios e executores compartilhados do
projeto. A tarefa é tornar claro o que existe, o que requer confirmação e
quem mantém cada parte. Preservar o desenho atual; não propor sua substituição
por workflows governados apenas por serem mantidos por Pipelines.

O [contrato de reuso](../repository-architecture.md#fronteira-entre-produto-e-workflows-compartilhados) continua válido.
Uso seletivo de componentes compartilhados aprovados pode ser avaliado quando
houver benefício e compatibilidade demonstrados, sem transferir a Pipelines
a manutenção dos workflows da fábrica. Esta entrega não implementa integração,
troca scanner ou altera gates.

## Quatro categorias de decisão

| Categoria | Estado / fonte | O que não decorre desse estado |
| --- | --- | --- |
| AUTORIA/SUSTENTAÇÃO | DEFINIDA pela premissa acima | Não concede dispensa de controles ou acessos corporativos |
| IMPLEMENTAÇÃO ATUAL | Código e evidence do projeto, relacionados abaixo | Não equivale a homologação corporativa ou cobertura total |
| REQUISITOS CORPORATIVOS A CONFIRMAR | Scanner aceito, controles adicionais, relatórios, retenção, integrações, exceções, runners e regras centrais | Ausência de resposta não significa obrigação de Veracode nem dispensa dele |
| DEPENDÊNCIAS EXTERNAS | IAM, PKI, ECR, rede, aprovações de serviços e primeiro aceite corporativo | Sandbox e autorização de autoria não comprovam implantação ou aprovação |

## Controles existentes preservados

IMPLEMENTED nesta seção significa presente na baseline indicada. Os limites
de cobertura e aceites continuam os da [RFC-013](../../RFC-013-Image-Base-Completa-com-Mermaid.md)
e do [contrato de consumo](../consumer-verification-contract.md).

| Controle | Implementação / evidence disponível | Limite relevante |
| --- | --- | --- |
| Apko/Melange, composição multiarch e lock/replay | [build_image.py](../../scripts/pipeline/artifacts/build_image.py), [validação](../../.github/workflows/validate-base-images.yml) e [composição](../image-composition.md); OCI com amd64/arm64 e inputs/lock registrados | Replay depende da disponibilidade dos insumos; não é homologação do runner corporativo |
| Trivy por arquitetura | [scan_images.py](../../scripts/pipeline/artifacts/scan_images.py): JSON e evidence de amd64/arm64; falha, relatório ausente/inválido ou arquitetura divergente bloqueiam a aprovação | Usa `vuln,secret`, `CRITICAL,HIGH,MEDIUM,LOW` e `--ignore-unfixed`; achados sem correção têm relatório separado. São parâmetros atuais, não thresholds corporativos homologados |
| Contratos funcionais | [runtime_images.py](../../scripts/pipeline/runtime/runtime_images.py), [workflow](../../.github/workflows/test-runtime-images.yml); executa o OCI candidato e o par -dev quando aplicável | Cobertura depende do plano/lote; skips explícitos não equivalem a PASS; não prova os controles das aplicações consumidoras |
| Publicação sem rebuild e identidade OCI | [publicador](../../.github/workflows/build-base-images.yml) e [verify_publication.py](../../scripts/pipeline/release/verify_publication.py); Skopeo preserva digests, compara índice validado/copiado/remoto e plataformas; build tags imutáveis com exceção stable | Registro da tag pode preceder signing/attestations; não há transação de publicação com rollback automático |
| Assinatura, provenance e SBOM | Publicador, [publish_sboms.py](../../scripts/pipeline/release/publish_sboms.py) e [verify_promotion.py](../../scripts/pipeline/release/verify_promotion.py); identidade assinada suportada é o OCI index digest, SPDX de cada subject | Trust model e limites dos verificadores no [ADR-0002](0002-sigstore-trust-model.md); evidence não é enforcement e não atribui SLSA level formal |
| Soak, promoção e read-back | [promote-stable.yml](../../.github/workflows/promote-stable.yml), [verify_stable.py](../../scripts/pipeline/release/verify_stable.py); seleção, assinatura/provenance, re-scan por arquitetura e leitura ECR exigem igualdade antes de promoted=true | Soak padrão 6h com input manual validado; read-back confirma o instante observado; sem gate específico de SBOM attestation |
| Retry sem rebuild | [contract_evidence.py](../../scripts/pipeline/runtime/contract_evidence.py); mesmo run, framework/revisão, digest/plataformas e par aplicável, sem falha mais recente do producer relevante | Artifact expirado, ausente, inválido ou conflitante não vira aprovação; aceite hospedado específico P1-02 continua pendente |
| Recuperação e quarentena | [recover-stable.yml](../../.github/workflows/recover-stable.yml) e [policy](../../policies/release/promotion-quarantine.json); verifica origem, re-scan e read-back, sem reconstrução | Quarentena exige alteração explícita revisada; não é bypass de CVE |
| Trust de composição | [integração de CAs](../../.github/workflows/image-trust.yml), [Wolfi](../wolfi-signing-key.md), preflight local/pin e drift detect-only | CAs corporativas reais pendentes; chave Wolfi não é trust set exclusivo por causa de discovery/JWKS Apko |
| Governança e operação | [ci.yml](../../.github/workflows/ci.yml), [CODEOWNERS](../../.github/CODEOWNERS), lints/pins e [saúde](../m11-m04-operational-health.md) | Proteções/aplicação corporativa a confirmar; enforce_admins=false é decisão do sandbox. Alerta externo e SLA ainda pendentes |

P1-01 hosted PASS; P1-02 e P1-03 PENDING preservados. Esta documentação não
produz novo aceite hospedado, corporativo ou lote inteiro aprovado.

## Scanner: cinco distinções necessárias

1. **Trivy é o gate técnico implementado na fábrica**, conforme o código acima.
2. O levantamento de build/publicação corporativo também descreve Trivy em
   outro fluxo. Isso não homologa automaticamente seu uso nesta fábrica.
3. O levantamento da esteira de segurança descreve **Veracode SCA**, inclusive
   modos de análise de imagem/container. Não é correto reduzi-lo a scan de source.
4. A aplicabilidade desse segundo fluxo à **fábrica federada** continua
   **A CONFIRMAR** com AppSec/Segurança. Nem sua obrigatoriedade nem sua
   inaplicabilidade foram decididas pela autorização de autoria.
5. Requisitos de segurança das **aplicações consumidoras** são uma decisão
   separada. Scan/assinatura da base não substituem os controles da aplicação.

P1-06 não escolhe uma nova ferramenta. Se for exigida integração adicional,
confirmar produto/modo/versão e cobertura de Wolfi/distroless, runtime/-dev e
ambas as arquiteturas, com evidência do artifact efetivamente analisado.
Resultado sem achados, isoladamente, não comprova essa cobertura.

## Uso dos levantamentos corporativos

Os dois Markdown fornecidos pelo responsável descrevem comportamentos
observados em outros fluxos. Servem para identificar interfaces e perguntas;
não são requisitos obrigatórios da fábrica, confirmação da configuração
corporativa vigente ou autorização para dispensar controles. A leitura local
não incluiu auditoria de execução corporativa nem de seu código vigente.

| Referência local | Uso nesta decisão |
| --- | --- |
| Levantamento de build/publicação | Identificar pontos de scan, passagem do artifact, publicação/promoção e autenticação para discussão de compatibilidade |
| Levantamento Veracode SCA de imagem/container | Distinguir seleção/disponibilização da imagem, execução do scanner, parser/consolidação, resultado de política, relatórios e dependências operacionais |

Não copiar thresholds, bypasses, regras de cache, destinos ou convenções para
a implementação. A promoção descrita em outro fluxo não justifica remover
o nosso re-scan/read-back. Um fallback para diretório ou detecção de alguma
imagem local não comprova análise do candidato por digest. Erro operacional,
warning, execução pulada e cache não devem ser confundidos com análise
concluída e aprovada.

O planejamento histórico de migração
fica preservado como hipótese anterior; a premissa e o escopo atuais são os
deste ADR. Não nasce dali um backlog obrigatório de substituição da fábrica.
Os levantamentos integrais e seus identificadores internos permanecem fora
do repositório público. Referências formais futuras devem respeitar acesso
e classificação definidos por seus responsáveis.

## Evidências e interfaces que podem ser exigidas

Apresentar aos responsáveis o que já é produzido: índice/manifests aprovados,
commit/run/attempt, relatórios por arquitetura, estados dos contratos,
versões/locks, cópia/read-back, assinatura/provenance/SPDX e resultados de
promoção/recovery. O consumidor verifica o mesmo digest conforme o
[contrato canônico](../consumer-verification-contract.md).

Hoje a [policy de saúde](../../policies/operations/health.json) mantém OCI
validado por 3 dias para retry; SBOMs, locks e relatórios de CI por 30 dias.
As attestations no ECR têm armazenamento distinto dos artifacts de CI.
`external_destination` é null e os thresholds de saúde não são SLA corporativo.
Destinos, retenção, permissões de acesso e eventual envio de relatórios
precisam de confirmação; esses números não são transportados de outro fluxo.

Uma integração adicional, **se exigida e autorizada em trabalho posterior**,
precisa explicitar input por digest/arquitetura, transporte/acesso ao artifact,
modo de scan, versão/policy aplicada, estados de execução/política, atualidade
do resultado e vínculo com a release. Definir também tratamento de falha,
exceções, owners e destino/classificação dos relatórios. Nenhum adaptador,
credencial, cache de resultado ou novo gate é implementado nesta fatia.

## Responsabilidades

| Responsável | Papel | Referências / limite |
| --- | --- | --- |
| Containers Products | Autoria, manutenção, testes, atualização das dependências, operação, triagem e sustentação da fábrica e de seus workflows | [Arquitetura](../repository-architecture.md), [CODEOWNERS](../../.github/CODEOWNERS), [saúde](../../policies/operations/health.json); responsáveis individuais/canal/SLA corporativos a definir |
| AppSec / Segurança | Confirmar requisitos aplicáveis, scanner aceito, controles adicionais, evidências e decisões/exceções sob sua competência | Pendências da [RFC](../../RFC-013-Image-Base-Completa-com-Mermaid.md) e [ADR-0002](0002-sigstore-trust-model.md); não se presume aprovação |
| Cloud / IAM / Network / PKI | Prover e aprovar infraestrutura, acessos, conectividade e âncoras correspondentes | P0-03 e itens externos da RFC; autorização de autoria não cria recursos nem permissões |
| Times consumidores | Build, testes, dependências, verificação/atualização das bases e controles das próprias aplicações | [Consumer Verification Contract](../consumer-verification-contract.md); responsabilidade não é transferida à fábrica |

Os owners de sandbox nas referências são exemplos operacionais existentes,
não nomeação formal de equipes corporativas. Pipelines não recebe a
manutenção dos nossos workflows por ser o mantenedor de outros fluxos.

## Validação corporativa de segunda-feira

As perguntas tratam somente do que ainda falta. As respostas devem identificar
owner, escopo aplicável, referência autorizada e evidence de aceite esperada,
sem publicar material restrito neste repositório.

| Pergunta | Interlocutor / resultado esperado |
| --- | --- |
| Quais requisitos de segurança, auditoria e compliance se aplicam à fábrica de imagens base federada? | AppSec/Segurança: conjunto aplicável ao produto, distinguindo-o das aplicações consumidoras |
| Trivy atende ao requisito de scan deste produto, com a cobertura e a policy atuais? | AppSec/Segurança: decisão de adequação ou lacunas, incluindo Wolfi/distroless, arquiteturas, severidades e achados sem correção |
| Existe integração adicional obrigatória de segurança/compliance, inclusive aplicabilidade da esteira Veracode SCA? | AppSec/Segurança: quando/onde exigir, modo e versão, inputs/outputs, evidência de cobertura e tratamento de falhas/exceções |
| Quais evidências, destinos, acessos e retenções são exigidos? | Segurança/Auditoria com Containers Products: relatórios e attestations exigidos, classificação, retenção, canal de alerta e SLA |
| Quais regras centrais continuam aplicáveis ao repositório e à execução de workflows federados? | Segurança e responsáveis pelas regras centrais: protections/revisões, runners, componentes permitidos e tratamento de exceções, sem rediscutir autoria |
| Quais acessos e recursos corporativos serão disponibilizados, por quem e quando? | Cloud/IAM/Network/PKI: runners, roles, ECR, CAs, rede/egress e serviços aprovados, além do plano do primeiro aceite corporativo |

## Consequências e condições de revisão

Manter uma implementação própria implica sustentar seus testes, dependências,
gates, evidências e operação. Requisitos externos permanecem abertos até
resposta de seus owners; não viram dispensa nem uma migração presumida.
O [ADR-0002](0002-sigstore-trust-model.md) continua PROPOSED para a decisão
Sigstore. Nenhuma conclusão local equivale ao primeiro E2E corporativo.

Revisitar este ADR após respostas corporativas ou mudança explícita de
requisitos/responsabilidades. Uma decisão de integração deve ter escopo e
validação próprios, preservando a identidade OCI e os controles existentes.
O aceite deste documento não autoriza mudanças de infraestrutura ou pipeline.
