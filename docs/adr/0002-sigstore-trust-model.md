# ADR-0002 — Modelo de confiança Sigstore

| Informação | Valor |
| --- | --- |
| Estado | **PROPOSED — decisão corporativa EXTERNAL / PENDING** |
| Data | 13/09/2026 |
| Baseline examinada | main `44fac09718c63a4cdffd456e65ce21944ac6b11c` |
| Owners | Segurança/AppSec: decisão; Containers Products / Owner RFC-013: proposta e aplicação futura |
| Origem | RFC-013, P1-05 — Sigstore Trust Model ADR |
| Aplicação atual | Documenta signing/verification existentes; não altera controles |

O eventual aceite/merge deste documento não representa aprovação corporativa
de serviços públicos. A decisão externa exige registro explícito de Segurança/AppSec.

## Context

A fábrica publica o OCI validado, assina o **index digest** com Cosign
keyless, atesta os SPDX originais e gera provenance com GitHub Build
Attestations. Promoção e recovery verificam assinatura e provenance antes
de re-scan e retag. É necessário explicitar quem autentica cada declaração,
quais dados saem do ambiente e o que precisa ser aprovado no corporativo.

Fontes executáveis: [publicador](../../.github/workflows/build-base-images.yml),
[publish_sboms.py](../../scripts/pipeline/release/publish_sboms.py),
[verify_promotion.py](../../scripts/pipeline/release/verify_promotion.py),
[promoção](../../.github/workflows/promote-stable.yml),
[recovery](../../.github/workflows/recover-stable.yml) e
[policy de identidades](../../policies/release/signing-identities.json).

O installer fixado instala **Cosign v3.0.6**; os comandos não configuram
chave estática, KMS, instância privada ou bypass de transparência. A action
de provenance é `actions/attest-build-provenance` v4, fixada por SHA. A CLI
`gh` vem do runner e tem sua versão registrada; não é pinada pelo projeto.

## Decision

Propor a manutenção do **Sigstore keyless público para assinatura de imagens
e attestations SPDX feitas por Cosign**, sujeita à aprovação de Segurança.
O desenho associa identidade verificável do workflow ao digest sem uma chave
privada duradoura sob custódia do projeto. Não envia layers da imagem ao
Rekor, mas expõe metadados e envia o predicate SPDX ao serviço para validação;
essa transferência também precisa ser aprovada.

Preservar GitHub Build Attestations para provenance, respeitando a diferença
de raízes e transparência entre repository público e privado. Manter consumo
por digest e verificação conforme o contrato canônico. Nenhuma dessas decisões
instala enforcement nos consumidores ou autoriza produção.

Private Sigstore: **NOT REQUIRED WITHOUT REGULATORY REQUIREMENT** como posição
proposta; não foi identificada nesta entrega uma exigência regulatória ou
policy corporativa aprovada que justifique operá-lo. Uma restrição explícita
de confidencialidade/policy também exige reavaliar as alternativas; não se
presume aceitação ou rejeição pela empresa.

## Trust model

| Componente / raiz | Responsabilidade e limite |
| --- | --- |
| GitHub Actions e OIDC | Executa o workflow e emite o token de identidade do job. Repository, workflow, ref, commit e IDs certificados dependem da integridade do GitHub e do contexto de execução. O issuer não aprova a segurança do build. |
| Cosign e chave efêmera | A chave privada temporária no cliente assina o digest/statement. Keyless elimina a gestão de uma chave persistente pelo projeto; não elimina chaves nem a confiança no runner. |
| Sigstore / Fulcio | Valida o token OIDC e certifica a associação identidade–chave pública por tempo limitado. A CA autentica identidade, não conteúdo seguro. |
| Rekor / transparency | Evidência verificável de registro da assinatura no log, com compromisso criptográfico sobre o payload. Não é registry, scanner ou aprovador; possibilidade de auditoria não significa monitoramento automático pelo projeto. |
| Certificate Transparency (CT) | Publica certificados Fulcio para tornar emissão auditável. É distinto do log de assinaturas Rekor. |
| Distribuição de trust roots | Cosign usa raízes/configuração Sigstore distribuídas por TUF a partir do bootstrap confiado pelo cliente: CAs, chaves de logs e material temporal aplicável. O projeto não fixa um fingerprint próprio de Fulcio/Rekor nem importa esses roots do ECR. |
| GitHub Build Attestations | Gera e armazena o bundle de provenance; a instância de assinatura depende da visibilidade do repository, conforme tabela abaixo. |
| AWS ECR | Armazena índice, manifests/layers e artifacts associados/referrers. Controla acesso e tags; **não é o signer** e não substitui verificação criptográfica. |
| Repository governance | CODEOWNERS, checks e proteções limitam quem altera código/workflows/policy. São controles de autorização da origem, distintos de certificado e assinatura. |

O modelo de CA/log e distribuição das raízes está descrito no
[security model Sigstore](https://docs.sigstore.dev/about/security/) e na
[configuração de signing](https://docs.sigstore.dev/cosign/signing/overview/).
TUF permite evolução de serviços/raízes: pin da versão Cosign não congela
eternamente endpoints ou chaves públicas dos serviços.

O job solicita OIDC para Sigstore com audience `sigstore`; a autenticação
AWS assume role por outro token/audience. Ambos dependem do GitHub, mas a
role ECR não é a identidade de assinatura. A emissão GitHub/Fulcio está
separada da confiança AWS por IDs.

### Sandbox identity

| Campo | Sandbox atual |
| --- | --- |
| Repository de origem | `alric-corp/alric-containers-image-base` |
| Repository ID | `1360616627` |
| Owner ID | `178685987` |
| Visibilidade | `public`, observada em 13/09/2026 |
| Workflow assinante | `alric-corp/alric-containers-image-base/.github/workflows/build-base-images.yml` |
| Certificate identity Cosign | `https://github.com/alric-corp/alric-containers-image-base/.github/workflows/build-base-images.yml@refs/heads/main` |
| OIDC issuer Cosign | `https://token.actions.githubusercontent.com` |
| Source ref | `refs/heads/main` |
| Registry | `712107929769.dkr.ecr.us-east-1.amazonaws.com` |

`workflow.yml` é chamador; a identidade assinante é o reusable
`build-base-images.yml` do produto, não o executor compartilhado de validação.
O alias histórico `alric-corp/itau-xj7-containers-image-base` só é aceito pela
policy com os mesmos IDs certificados. Signature e provenance precisam passar
para o **mesmo signer e digest**; os IDs são extraídos do certificado de
provenance verificado, nunca de um predicate livre.

Os campos de identidade e execução publicados no certificado seguem a
[especificação Fulcio](https://github.com/sigstore/fulcio/blob/v1.8.5/docs/oid-info.md);
o certificate issuer X.509 da CA e o OIDC issuer GitHub são campos distintos.

### Corporate identity

A identidade corporativa ainda não está estabelecida. O destino proposto na
RFC não é uma identidade já aprovada ou certificada. Repository/owner IDs,
workflow/ref, issuer, registry e raízes aceitas devem ser definidos e testados
no ambiente real, incluindo negativos. Copiar os valores do sandbox não
concede confiança à fábrica corporativa. PKI de TLS das imagens e assinatura
APK Wolfi têm finalidades distintas das raízes de assinatura de artifacts.

## Image Signature vs Provenance vs SBOM Attestation

| Evidência | Declaração autenticada | Subject / limite |
| --- | --- | --- |
| Image Signature | Uma identidade assinou determinado digest | OCI index digest; não prova aprovação humana, resultado de scan ou segurança do código |
| Provenance | Um workflow/repository/commit produziu ou declarou determinado subject | Mesmo índice, predicate SLSA provenance v1; conteúdo declarado depende do workflow, não é scan nem certificação de SLSA level |
| SBOM Attestation | Uma identidade atestou um predicate SPDX para determinado subject | Índice, manifest amd64 e manifest arm64, cada qual com SPDX próprio; não prova completude nem ausência de vulnerabilidades |

Apko gera os SPDX; a validação registra subjects/hashes; `publish_sboms.py`
confere o OCI/SPDX aprovado e chama `cosign attest --yes --type spdxjson`
para cada digest. Isso difere da action GitHub usada para provenance.
Assinatura de imagem e provenance independentes dos manifests de plataforma
não são produzidas: a unidade de consumo assinada suportada é o índice.

## What is public

Não confundir conteúdo enviado a um serviço com conteúdo persistido na entrada
pública do log. No **Cosign v3.0.6**, os defaults de sign/attest usam bundles
e DSSE com signing config; descrever todo evento como o formato legado
`hashedrekord` seria incorreto. O caminho efetivo é explicado pelas fontes
[sign](https://github.com/sigstore/cosign/blob/v3.0.6/cmd/cosign/cli/sign/sign.go),
[attest](https://github.com/sigstore/cosign/blob/v3.0.6/cmd/cosign/cli/attest/attest.go).

| Dado | Exposição no modelo atual |
| --- | --- |
| Identidade/certificado | Repository/owner, IDs, workflow, ref/commit, issuer, chave pública e metadados certificados da execução podem ser públicos em CT e no material de verificação Rekor. O certificado observado inclui URI do run/attempt. |
| Digests e evento de assinatura | O statement/bundle contém o subject digest; o log DSSE contém hashes do payload/envelope conforme versão, assinaturas/certificados e metadados/provas de inclusão. **Hash do payload DSSE não é o OCI index digest.** O bundle permite correlacioná-los. |
| Imagem/source code | Layers, arquivos da imagem e checkout do código não são enviados ao Rekor por esses comandos. Identidade e digest podem revelar existência/associação do artifact, sem publicar seus bytes. A visibilidade do GitHub/ECR determina acesso aos conteúdos ali armazenados. |
| Predicate SPDX | O envelope integral é enviado ao serviço Rekor para verificar a assinatura. A entrada DSSE canonicalizada guarda hashes/assinaturas/verificadores, não o predicate SPDX completo. O SPDX integral permanece no bundle/artifact associado no ECR e nas evidências de CI, sujeitos aos acessos desses serviços. |
| Provenance GitHub | No sandbox público, o bundle disponibilizado pelo GitHub expõe subject, repository/workflow, commit/ref e metadados de execução/build. Isso é distinto dos dados canonicalizados no log; não contém automaticamente o checkout ou layers. |

O comportamento de armazenamento DSSE é verificável no
[Rekor v1](https://github.com/sigstore/rekor/blob/v1.5.1/pkg/types/dsse/v0.0.1/entry.go)
e [Rekor v2](https://github.com/sigstore/rekor-tiles/blob/v2.2.1/pkg/types/dsse/dsse.go).
O v1 também indexa digests dos subjects para busca: payload ausente no corpo
do log não significa impossibilidade de correlação por digest.
O envio do envelope completo pode ser conferido no
[cliente sigstore-go v1.1.4](https://github.com/sigstore/sigstore-go/blob/v1.1.4/pkg/sign/transparency.go),
dependência do Cosign examinado. Fulcio também publica certificados no seu
[CT log](https://github.com/sigstore/fulcio/blob/main/docs/ctlog.md):
desligar apenas upload ao Rekor não tornaria o keyless público privado.
O envio de SPDX ao operador é relevante mesmo sem predicate consultável no
log. Não se promete confidencialidade perante o serviço, ausência de logs
operacionais ou eliminação posterior de metadados públicos. Também não se
afirma que SBOMs ficam secretas só porque não são payloads do log.

## Public vs private repositories

| Mecanismo | Repository GitHub público (sandbox) | Repository GitHub privado (possível corporativo) |
| --- | --- | --- |
| GitHub Build Attestations | Usa Sigstore Public Good Instance, com transparência pública | Usa instância Sigstore do GitHub, raízes próprias, sem transparency log, federada somente com GitHub Actions |
| Distribuição/verificação GitHub | Bundle via API GitHub; neste projeto também é anexado ao ECR | Acesso autorizado à API/registry e disponibilidade do recurso/plano precisam ser validados no corporativo |
| Cosign direto: image sign e SPDX attest | Configuração padrão pública do Sigstore | **Continua pública se os mesmos comandos/defaults forem mantidos**; visibilidade privada não seleciona automaticamente a instância GitHub |

A distinção da instância de attestations é documentada pelo
[GitHub](https://docs.github.com/en/actions/concepts/security/artifact-attestations).
Para repositories privados/internos, a disponibilidade de artifact attestations
exige GitHub Enterprise Cloud, conforme os
[pré-requisitos oficiais](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations).
Não se presume equivalência com GitHub Enterprise Server ou ambiente isolado.

`gh attestation verify` confia, por padrão, nas instâncias pública Sigstore
e GitHub, obtendo o material pelas respectivas raízes TUF. A instância privada
usa evidência temporal de TSA em lugar de Rekor; ausência de log nesse modelo
não é uma flag de bypass do Cosign. Não há `--custom-trusted-root` ou restrição
a uma única dessas instâncias no verificador atual. Detalhes e fontes da CLI
estão no [verificador gh v2.100.0](https://github.com/cli/cli/blob/v2.100.0/pkg/cmd/attestation/verification/sigstore.go).

## Verification model

Fluxo recomendado para consumo auditado, com comandos e valores no
[Consumer Verification Contract](../consumer-verification-contract.md):

```text
OCI index digest fixado
  → cosign verify (identity + issuer esperados)
  → gh attestation verify (repository + workflow + ref + subject)
  → cosign verify-attestation --type spdxjson, conforme policy consumidora
  → consumir exatamente o digest verificado
```

O comando `gh` consulta attestations na API GitHub por padrão; a imagem
`oci://...` exige acesso ao registry. `--bundle-from-oci` é opção da CLI,
mas não é usada pelo gate atual. O verificador do projeto acrescenta índice
com exatamente amd64/arm64, policy de nomes históricos e IDs certificados.
O [manual da CLI](https://cli.github.com/manual/gh_attestation_verify) distingue
os campos certificados dos predicates controláveis pelo workflow.

Promoção/recovery executam gates de assinatura/provenance, além de re-scan
e read-back. Não executam gate específico de SBOM attestation. A política
atual também não exige mesmo run/commit entre signature e provenance nem
fixa um commit humano aprovado: exige a mesma identidade, main e digest.
Consumidores devem conferir a revisão/run da release que aprovaram.

Há ainda um limite do gate atual: ele exige sucesso de `cosign verify` e
lista JSON não vazia, mas não filtra explicitamente o tipo
`https://sigstore.dev/cosign/sign/v1`. Na amostra hospedada do Cosign v3.0.6,
a saída normalizada contém registros de assinatura, SPDX e provenance para
o mesmo índice.
Não se afirma que a ausência isolada da assinatura dedicada seria rejeitada
se houver outro bundle aceito pelo Cosign. Esse registro descreve o controle
existente; não adiciona nem remove verificações.

`stable` é ponteiro mutável; build tag é identificador imutável da release;
OCI index digest é a identidade exata do artifact multiarch. Evidence
disponível **não é runtime/admission enforcement**. Não há admission
controller nesta fábrica nem verificação automática instalada em todos os
consumidores. Não se atribui SLSA level formal.

## Consequences

Há identidade auditável e menos responsabilidade por segredos duradouros,
com dependência de GitHub/Sigstore, dos clientes e de suas raízes distribuídas.
Verificação e política de origem continuam indispensáveis. O projeto não
opera um monitor de CT/Rekor; a transparência oferece evidência para auditoria,
não detecção/resposta automática a toda emissão indevida.

### Integrity e availability

Falha de OIDC, Fulcio, Rekor ou serviço temporal requerido pode impedir nova
assinatura. Erro no Cosign ou na geração de attestations falha o passo e
interrompe a sequência; não há fallback para assinatura opcional. A cópia ao
ECR **já ocorreu**: uma tag de build pode existir com evidence incompleta.
SPDX é atestado após image signing e antes de provenance; uma falha pode
deixar estado parcial, sem rollback automático.

Promoção/recovery não avançam quando a verificação necessária falha ou falta.
Isso não implica apagar artifacts parcialmente escritos nem acrescentar um
gate SBOM inexistente. Falha de leitura de evidência/raízes também pode
bloquear verificação: não se aceita artifact sem evidência para restaurar
disponibilidade. Certificado efêmero expirado não invalida automaticamente
assinatura histórica cuja validade temporal seja comprovada. Não se promete
verificação offline/indisponibilidade tolerada pelo fluxo atual, que consulta
GitHub/ECR e material de confiança conforme as ferramentas.

## Risks

| Risco | Mitigações presentes / limite residual |
| --- | --- |
| Workflow comprometido | Pins, validação de inputs, permissões e separação de PR sem AWS reduzem exposição. Código que controla o contexto autorizado ainda pode produzir declarações válidas e maliciosas. |
| Repository comprometido / writer autorizado malicioso | CODEOWNERS, checks e revisão reduzem mudanças indevidas. Assinatura não detecta intenção maliciosa aprovada. No sandbox, enforce_admins=false é decisão explícita; proteção corporativa permanece externa. |
| Compromisso da identidade GitHub ou CA | SAN/issuer exatos, IDs certificados e transparência reduzem impersonação simples e permitem auditoria. Um emissor comprometido pode emitir identidade aparentemente válida; não há garantia de prevenção completa. |
| Indisponibilidade GitHub/Sigstore | Timeouts e falha dos passos/gates preservam integridade; novas releases/verificações podem ficar bloqueadas. Não há SLA corporativo provado. |
| Privacidade de transparência/processamento | Metadados públicos são persistentes e correlacionáveis; SPDX é enviado ao serviço. Aprovação de Segurança é pendente, não mitigada pela simples escolha de ECR privado. |
| Modificação/remoção no registry | Digest, assinatura/provenance, imutabilidade de build tags e read-back detectam divergências no fluxo. Registry pode remover conteúdo/evidence ou mover stable com acesso externo; read-back só confirma o instante observado. |

## Alternatives considered

| Alternativa | Avaliação para esta decisão |
| --- | --- |
| Chave privada estática | Exige custódia, distribuição confiável da pública, rotação/revogação e resposta a vazamento. Compromisso da chave duradoura amplia o período de abuso; identidade deixa de ser certificada por execução como hoje. Não escolhida nesta proposta. |
| AWS KMS signing | Cosign suporta KMS; pode reduzir exposição da chave privada, mas exige policy/gestão de chave e outro contrato de verificação. Um workflow com permissão Sign comprometido ainda pode assinar; KMS por si só não define política de transparência. Alternativa conceitual, sem IAM ou implementação. |
| Fulcio/Rekor privados | Permitem controlar distribuição/metadados, ao custo de operar CA, logs, raízes/rotação, disponibilidade, auditoria e clientes. Sem exigência regulatória/policy identificada, esse custo não é justificado automaticamente. |
| Sem assinatura | Rejeitada: perde a autenticação verificável do digest exigida pela plataforma. |

Suporte técnico de KMS: [Cosign key management](https://docs.sigstore.dev/cosign/key_management/overview/).
As alternativas não são backlog autorizado e não são implementadas por este ADR.

## Corporate decision required

Segurança/AppSec, com Containers Products e Cloud/Network, deve registrar:

- **Option A — Accept public Sigstore:** aceitar os metadados públicos de
  image signing/attestations e o processamento externo do SPDX; manter o
  desenho e aprovar raízes, identidades, egress e procedimento de incidentes.
- **Option B — Disallow public transparency metadata/processamento:** exigir
  novo desenho do trust model antes da produção. Repositório privado GitHub
  sozinho não resolve o Cosign direto. Não há implementação dessa opção aqui.

O registro externo precisa identificar aprovador/policy e escopo dos dados,
visibilidade/plano GitHub, valores corporativos a verificar, raízes aceitas
e evidence de geração/verificação no ambiente escolhido. A recomendação é
Option A condicionada a esse aceite; não há decisão corporativa tomada.
CAs, GitHub protections, OIDC/IAM, ECR, egress/mirror, scanner, alerta/SLA e
primeiro E2E continuam pendentes conforme a [RFC](../../RFC-013-Image-Base-Completa-com-Mermaid.md).

## Revisit conditions

Reavaliar se Segurança rejeitar divulgação/processamento, surgir exigência
regulatória, mudar repository/visibilidade/plataforma GitHub ou identidade de
workflow, mudar versão/defaults/raízes/formato de log das ferramentas, ocorrer
compromisso de emissor/workflow ou a disponibilidade não atender ao requisito
corporativo. Mudança de estado ou substituição deve conservar esta evidência
e seguir a [convenção dos ADRs](README.md), sem aceitação externa implícita.
