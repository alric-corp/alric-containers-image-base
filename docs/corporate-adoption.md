# P0-03 — Pacote de adoção corporativa e plano de execução

**Pacote local para revisão; implantação e homologação NÃO EXECUTADAS.**
Baseline: main `3af67d47869b6370f72fcfad1d16cde673cb7f57`, com PR #60
integrado. O [aceite desta documentação](../specs/2026-09-13-corporate-adoption/acceptance.md)
é distinto dos testes de destino abaixo. Aprovação deste pacote não autoriza
aplicar IAM, publicar imagens, mover stable, configurar serviços ou transmitir
metadados corporativos.

Este é o ponto de entrada da adoção. A premissa de autoria e sustentação
permanece no [ADR-0003](adr/0003-controles-seguranca-workflows-federados.md):
Containers Products mantém os workflows federados. Não se reabre essa
autorização, nem se transfere manutenção a Pipelines. Regras de AppSec,
auditoria, infraestrutura e operação precisam de decisões próprias.

## 1. O que existe, o que falta e qual evidence vale

| Área | Implementação / fonte canônica | Observação ou preparo existente | Dependência para o destino |
| --- | --- | --- | --- |
| Composição e contratos | [Apko/Melange, CAs, tzdata, lock e SPDX](image-composition.md); amd64/arm64, runtime/-dev | Testes sintéticos e runs de sandbox nos registros referenciados; cobertura depende do plano de frameworks | Runners, rede, âncoras e lote corporativos; testes CA-05/06/07 |
| Reuso e governança | [Contrato de reuso](m09-m12-reusable-workflows.md) e [arquitetura](repository-architecture.md); chamadas por SHA e executores sem AWS | Código integrado; origem e referências sandbox ainda presentes | Dois repositórios, acesso e ajustes PAR-01–06; CA-01/02 |
| Release e consumo | [Contrato canônico](consumer-verification-contract.md): OCI validado, assinatura, provenance, SBOM, promoção/recovery | Evidence disponível no sandbox; não é enforcement de runtime | Identidade, ECR e piloto de destino; CA-08–12/14 |
| IAM | [P1-04](iam-permission-contract.md) e [templates propostos](../policies/aws/proposals/factory-permissions/README.md) | Artefatos locais revisados, não aplicados | Cloud/IAM fornece parâmetros e restrições efetivas; CA-03/04 |
| Sigstore e scanner | [ADR-0002](adr/0002-sigstore-trust-model.md) e ADR-0003 | Signing atual e Trivy implementados; decisões corporativas PROPOSED/EXTERNAL_PENDING | Decisão antes de uso dos serviços/dados corporativos; CA-01/09 |
| Wolfi | [Chave local, pin, rotação e drift](wolfi-signing-key.md) | Defense-in-depth; discovery/JWKS continua risco residual | Aprovar egress/trust requerido e exercer preflight; CA-13 |
| Operação | [P1-08](m11-m04-operational-health.md): health, pins, resumos e timing | Detecção/relatórios em amostra datada; envio externo NOT IMPLEMENTED | Responsáveis, canal, entrega/ACK, metas e acordo; CA-15–18 |

Estados das fatias, conforme a [RFC atual](../RFC-013-Image-Base-Completa-com-Mermaid.md)
e as evidências referenciadas, sem reescrever snapshots pré-merge:

| Fatia | Estado de origem preservado | Aceite corporativo |
| --- | --- | --- |
| P1-01 | Hosted PASS limitado a go1-26/go1-26-dev no run 34768459323, commit e3ed682; read_back_status=confirmed e digests iguais, conforme [evidence P1-09](../specs/2026-09-13-consumer-contract-rfc-refresh/evidence.md) | NOT RUN |
| P1-02 | Retry/reuse hospedado PASS no run 34889507318; continuação de publicação pendente | PENDING — aceite integral não encerrado |
| P1-03 | PARTIAL / BLOCKED_UPSTREAM; mínimo hosted PASS observado nos dois Go em 34852458933/1, conforme [nova evidence](../specs/2026-09-13-wolfi-signing-key/evidence.md#reconciliação-hospedada--2026-09-14); coleta sujeita a revisão | NOT RUN |
| P1-04 | LOCAL_STRUCTURE_VALIDATED=PASS; AWS_VALIDATOR_CHECKED, AWS_SIMULATION_CHECKED e SANDBOX_EXECUTION_VERIFIED=NOT RUN | CORPORATE_ACCEPTED=EXTERNAL_PENDING |
| P1-08 | Documentação revisada; aceite operacional completo pendente | NOT RUN / EXTERNAL_PENDING |

A amostra operacional de 12/09/2026 00:00 a 13/09/2026 22:00 UTC
(44 runs, dois health com problemas detectados e relatórios) está na
[evidence P1-08](../specs/2026-09-13-operational-readiness-slo/evidence.md).
Não é desempenho atual nem série corporativa. Este pacote não coletou novos
runs de operação nem produziu novos aceites hospedados.

Separar em cada registro: **documentação**, **mecanismo implementado**,
**configuração de destino**, **autorização**, **execução** e **aceite**.
Não existe score agregado ou um único estado “pronto” para essas dimensões.

## 2. Mapa de parâmetros e ajustes

As classes não são prioridades do roadmap:

- CONFIGURATION_ONLY: preencher settings/inputs ou dados declarativos
  existentes, inclusive arquivos versionados sob revisão; não significa
  apenas trocar GitHub variables nem autoriza aplicar a configuração.
- CODE_CHANGE_REQUIRED: modificar lógica, referências executáveis ou
  interface de workflow em fatia posterior.
- EXTERNAL_PROVISIONING: criar/configurar recursos por operador autorizado.
- EXTERNAL_DECISION: definir requisito, destino ou aprovação por competência.
- ALREADY_PORTABLE: mecanismo reaproveitável nas condições indicadas.
- NOT_YET_VERIFIED: configuração efetiva/comportamento do destino não observado.

Todos os valores corporativos estão **A FORNECER**, sem IDs, ARNs, canais ou
segredos fictícios. As colunas finais apontam a um teste de destino CA-xx.

### Identidades, repositórios e AWS

| ID / finalidade | Origem e configuração sandbox publicável | Entrada e fornecedor corporativos | Forma atual / ajuste e classe | Verificação |
| --- | --- | --- | --- | --- |
| PAR-01 — dois repositórios | Produto `alric-corp/alric-containers-image-base`; biblioteca `alric-corp/alric-containers-reusable-workflows`. URLs/estrutura em [reuso](m09-m12-reusable-workflows.md). [Promoção](../.github/workflows/promote-stable.yml) e [recovery](../.github/workflows/recover-stable.yml) passam `$GITHUB_REPOSITORY` ao [verificador](../scripts/pipeline/release/verify_promotion.py), que recebe `repository` como argumento posicional. [Build](../scripts/pipeline/artifacts/build_image.py) e [runtime](../scripts/pipeline/runtime/runtime_images.py) fazem leituras próprias da variável para identificar o repositório de origem | Admin GitHub + Containers Products: host, owner/nome, visibilidade, URLs e acesso dos dois repos | EXTERNAL_PROVISIONING. Contexto GITHUB_REPOSITORY é ALREADY_PORTABLE; literais das linhas seguintes não são | CA-01/02/09: commit, origem e identidade do destino |
| PAR-02 — origem e pins shared | [Policy de origem](../policies/governance/reusable-workflows.json) + [workflow_dependencies.py](../scripts/pipeline/governance/workflow_dependencies.py): inventário explícito de pontos obrigatórios; [validate](../.github/workflows/validate-base-images.yml)/[runtime](../.github/workflows/test-runtime-images.yml) usam SHA `7a9b055a462eeb8552d3404c26538b44e8ccd83f` | Mantenedores: origem e release revisado acessível | Origem é CONFIGURATION_ONLY versionada; atualização dos literais/release é coordenada. O resolvedor portátil foi implementado localmente na [subfatia técnica](../specs/2026-09-14-shared-origin-portability/spec.md), com PASS hosted observado na origem sandbox após PR #62, sujeito à revisão da coleta; migração real/acesso privado pendentes. REUSABLE_WORKFLOWS_PATH só muda diretório; não aprova origem, SHA ou bytes | CA-02: policy, callers, action interna/local, checkout, Dependabot e documentos coerentes; acesso privado ainda não comprovado |
| PAR-03 — action compartilhada | [Promoção](../.github/workflows/promote-stable.yml)/[recovery](../.github/workflows/recover-stable.yml): setup-trivy SHA `eea2d2f4c4102ded74204e4131c1417f444ae3fc`; referência interna também existe no release shared | Containers Products: origem e commit da action e novo release da biblioteca se necessário | CODE_CHANGE_REQUIRED condicional à nova origem, coordenada entre repos. Renomear caller não reescreve referências de commit antigo; publicar release revisado antes de repin, em etapa autorizada | CA-02/07: mesma definição Trivy nos caminhos |
| PAR-04 — acesso privado e checkout | [Fast checks](../.github/workflows/test-promotion.yml): segundo actions/checkout usa repository/ref resolvidos e token padrão, sem credencial própria | Admin GitHub/Segurança: visibilidade, compartilhamento e forma segura de leitura cross-repository | Sharing de action/reusable é CONFIGURATION_ONLY; segundo checkout privado exige solução revisada, CODE_CHANGE_REQUIRED se o acesso atual não servir. Não injetar secret em PR/fork | CA-02: download do reusable e clone explícito testados separadamente |
| PAR-05 — governança e permissões | [CODEOWNERS](../.github/CODEOWNERS), [fast checks](../.github/workflows/test-promotion.yml), [workflow.yml](../.github/workflows/workflow.yml); owners sandbox, checks test/lint-workflows. Enforce_admins=false é decisão do sandbox | Admin GitHub/AppSec: times/revisores, origem dos checks, regras centrais, Actions permitidas e acesso da biblioteca | CONFIGURATION_ONLY para owners versionados; EXTERNAL_PROVISIONING + EXTERNAL_DECISION para proteções efetivas, incluindo enforce_admins corporativo. Preservar permissões aninhadas; sem secrets: inherit | CA-01/02: revisão exigível e PR sem AWS/OIDC |
| PAR-06 — runners | Produto/shared usam ubuntu-latest; shared não oferece input de runner. Melange exige Docker privilegiado e QEMU; [contratos](../tests/runtime/README.md) precisam Docker, OpenSSL, Python e portas locais | Plataforma/Segurança: capacidade, grupos, isolamento, labels, egress e permissão para esse modo de build | Hosted permitido: EXTERNAL_DECISION + EXTERNAL_PROVISIONING. Runner distinto obrigatório: CODE_CHANGE_REQUIRED coordenada em shared/callers, sem alterar a biblioteca nesta fatia. ARM nativo não é pré-requisito novo | CA-05: amd64 nativo e arm64 emulado identificados, sem privileged/socket no candidato runtime |
| PAR-07 — região/role/registry | [workflow.yml](../.github/workflows/workflow.yml): vars.AWS_REGION e vars.AWS_ROLE_ARN; promoção direta/recovery usam essas vars. Não há default de região em execução; us-east-1 é exemplo sandbox. Registry vem do ecr-login | Cloud/IAM fornece conta, região e role; admin GitHub configura vars | CONFIGURATION_ONLY após EXTERNAL_PROVISIONING; valores remotos atuais NOT_YET_VERIFIED nesta coleta. Não copiar conta `712107929769` como corporativa | CA-03/04: recurso e sessão corretos em cada rota |
| PAR-08 — trust e subject | [Trust ativa](../policies/aws/github-actions-image-base-trust.json): provider token.actions.githubusercontent.com, aud=sts.amazonaws.com, subject main com repo ID `1360616627` e owner ID `178685987` | Cloud/IAM + admin GitHub: issuer/provider, aud/sub realmente emitidos, IDs, role e restrições adicionais | Referenciar [sete parâmetros e trust proposta P1-04](iam-permission-contract.md). CONFIGURATION_ONLY dos parâmetros; aplicação EXTERNAL_PROVISIONING. Repository StringEquals continua ligado ao nome; [renomeação](repository-rename.md) trata também outras referências | CA-03: caminhos chamados/diretos; extras na trust não são conditions da sessão ECR |
| PAR-09 — assinatura/provenance | [signing-identities.json](../policies/release/signing-identities.json): entrada sandbox, IDs e alias histórico; [verify_promotion.py](../scripts/pipeline/release/verify_promotion.py) compõe GitHub.com/build-base-images.yml/main e issuer GitHub | Admin GitHub/Segurança: repository/owner IDs, identidade certificada, branch/host/path e aliases legítimos | CONFIGURATION_ONLY versionada para cadastrar nova identidade/IDs. **Sem a entrada, a verificação extra de IDs não é aplicada**; cadastrar e testar antes de publicar. Outro host/ref/path exige CODE_CHANGE_REQUIRED e avaliação ADR-0002; não presumir GHES equivalente | CA-09: IDs ausentes/errados e identidade divergente rejeitados; não copiar alias sandbox |
| PAR-10 — nomes ECR e mutabilidade | [Publicador](../.github/workflows/build-base-images.yml), promoção/recovery: image-base-<framework>, IMMUTABLE_WITH_EXCLUSION com stable. CreateRepository condicional; PutImageTagMutability incondicional | Cloud/IAM + produto: catálogo aprovado de ARNs, manter prefixo ou decidir mudança | P1-04: execution + provisioning. EXTERNAL_DECISION + EXTERNAL_PROVISIONING. Novo prefixo: CODE_CHANGE_REQUIRED nos fluxos e referências associadas. Pré-provisionar sozinho não elimina a chamada de mutabilidade | CA-04/08/10: recursos consistentes e read-back; não prometer isolamento por tag |
| PAR-11 — consumo ECR | [Contrato de consumo](consumer-verification-contract.md) e P1-04; factory role não é policy de pull do piloto | Cloud/IAM + consumidores: principals/contas/redes, escopo de imagens/referrers, acesso GitHub às attestations | EXTERNAL_PROVISIONING + EXTERNAL_DECISION. Identity/repository policy e demais restrições precisam avaliação conjunta; policy efetivamente anexada não foi obtida | CA-04/14: leitura no escopo permitido e negativo fora dele; sem role de publicação no consumidor |

**Biblioteca privada:** Settings de compartilhamento permite download de
actions/reusables por mecanismo próprio; isso não concede acesso Git genérico
ao segundo checkout. O token padrão do checkout é restrito ao repo corrente.
Conferir [sharing](https://docs.github.com/en/actions/how-tos/reuse-automations/share-with-your-organization),
[checkout privado](https://github.com/actions/checkout#checkout-multiple-repos-private)
e [restrições do reuso](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations).
Aprovar o desenho de acesso antes de implementar qualquer credencial.
Sem rota segura para fast checks de PR, essa etapa permanece bloqueada.

Para PR/fork interno, admins devem confirmar se forks são permitidos, quem
pode iniciar runs, acesso a Actions privadas e restrições de runners/tokens.
Se fork não for viável, registrar restrição e exercício seguro de PR de branch
no mesmo repo, com o alcance menor declarado. Não tornar o repo público,
criar exceção de proteção ou fornecer credenciais a código não confiável para
fabricar um negativo. A impossibilidade do teste completo não vira PASS.

### PKI, rede, ferramentas e operação

| ID / finalidade | Origem / configuração atual | Entrada e fornecedor corporativos | Forma atual / ajuste e classe | Verificação |
| --- | --- | --- | --- | --- |
| PAR-12 — âncoras reais | [manifest.json](../melange/certificates/manifest.json): profile=public, certificates vazio; aquisição histórica usa MOCK. [Composição](image-composition.md) distingue os perfis | PKI: CAs públicas aprovadas, origem, hash/validade, legitimidade e autorização de distribuição no repo de destino | Mecanismo ALREADY_PORTABLE; insumos CONFIGURATION_ONLY sob revisão. Nunca private key corporativa nem cópia de anchors internas para repo público sem aprovação | CA-06: manifesto real, sem MOCK/test; PEM/JKS e TLS |
| PAR-13 — aquisição de CAs | [certificados.sh](../scripts/certificates/certificados.sh): buckets via CERTIFICADOS_BUCKET_CLOUDSEC/CERTIFICADOS_BUCKET_CACERTITAU e --lockfile; EXPECTED_FILES/object keys fixos; [hashes](../scripts/certificates/certificados.sha256)/[metadados](../scripts/certificates/certificados.metadata.txt) históricos | PKI/Cloud: fontes/objetos e acesso do operador de aquisição | CONFIGURATION_ONLY se convenção atual aprovada; outra lista/protocolo implica CODE_CHANGE_REQUIRED no helper. CI só verifica insumos locais com [prepare_anchors.py](../scripts/certificates/prepare_anchors.py), não chama S3/make certificates. Não ampliar role recorrente | CA-06: pin deliberado, aquisição e stage/verify; mismatch bloqueia |
| PAR-14 — stores e conectividade TLS | [Base](../distroless/image-base.yaml): SSL_CERT_FILE/NODE_EXTRA_CA_CERTS para PEM; Apko integra Java cacerts; [receita Melange](../melange/image-base-ca-certificates.yaml) instala provider | PKI + pilotos: endpoints autorizados com cadeia real e negativo controlado | ALREADY_PORTABLE na imagem; NOT_YET_VERIFIED no destino. Trust do host/proxy, Docker e ferramentas é separada da CA dentro da imagem | CA-05/06: TLS sem bypass e confiança instalada, não PEM injetado |
| PAR-15 — packages e trust Wolfi | Base/Melange: packages.wolfi.dev/os; [chave/pin](../melange/keys/wolfi-signing-key.json), [preflight](../scripts/pipeline/governance/wolfi_trust.py); discovery/JWKS pode ampliar trust | Network/Segurança: egress permitido, requisito de isolamento ou alternativa aprovada | EXTERNAL_DECISION + EXTERNAL_PROVISIONING; pacotes/pins portáveis se origem mantida. Se exigida trust exclusiva, aplicar requisito futuro de [mirror/proxy controlado e egress](wolfi-signing-key.md), sem escolher tecnologia aqui | CA-05/13: APK/lock e pin locais, drift detect-only; não usar 404 como invariant |
| PAR-16 — ferramentas/Actions | [Pin inventory](../scripts/pipeline/governance/pin_inventory.py), [Makefile](../Makefile), publicador e shared: cgr.dev (Apko/Melange), quay.io (Skopeo), Docker Hub (actionlint), GitHub (Actions/releases), [requirements-dev.txt](../requirements-dev.txt) | Network/Segurança + mantenedores: catálogo permitido e acesso aos hosts/redirects; atualização por revisão | EXTERNAL_DECISION + EXTERNAL_PROVISIONING; origem alternativa exige ajuste/pin revisado nos consumidores, condicional. Configuração Renovate/Dependabot não comprova app instalado | CA-05/13: downloads, pin/checksum e versão efetiva |
| PAR-17 — DB de vulnerabilidades | [scan_images.py](../scripts/pipeline/artifacts/scan_images.py)/[report_unfixed_cves.py](../scripts/pipeline/release/report_unfixed_cves.py) não sobrescrevem DB repositories. Shared fixa Trivy 0.72.0 | Network/AppSec: acesso/atualização de DB e alternativa se necessária | Defaults upstream abaixo, NOT_YET_VERIFIED em destino. Troca de origem exige ajuste revisado em todos os caminhos relevantes; não congelar DB nem enfraquecer Trivy | CA-05/07/10: DB utilizável/atual, scans por arquitetura |
| PAR-18 — serviços de segurança | [ADR-0002](adr/0002-sigstore-trust-model.md): Cosign direto público, Fulcio/Rekor/TUF; GitHub Attestations é outro mecanismo. [ADR-0003](adr/0003-controles-seguranca-workflows-federados.md): Trivy e aplicabilidade de SCA a confirmar | AppSec/Segurança: aprovar transferência de metadados/SPDX e scanner/integrações deste produto; admin GitHub confirma plano/visibilidade | EXTERNAL_DECISION antes de execução corporativa. Privado no GitHub não torna Cosign privado; rejeição exige fatia própria antes de usar esses serviços, não bypass | CA-01/09: aprovação e verificação com raízes/identidade do destino |
| PAR-19 — retenção | [health.json](../policies/operations/health.json): OCI 3 dias; reports/Melange/SBOM 30; [lifecycle ECR](../policies/operations/ecr-lifecycle.json): untagged 30 dias | Auditoria/Cloud/produto: prazos, quotas, acesso, exportação e preservação de subjects/referrers | EXTERNAL_DECISION + EXTERNAL_PROVISIONING; mudar prazos exige alinhar dados versionados e uploaders CODE_CHANGE_REQUIRED, inclusive shared quando aplicável | CA-12/15: artifact disponível na janela, preview representativo e recovery |
| PAR-20 — operação/alertas | health.json owner/escalation sandbox, external_destination=null; [pipeline-health.yml](../.github/workflows/pipeline-health.yml); resumos/timing em P1-08 | Containers Products + operação corporativa: responsáveis nomeados, canal, atendimento, retenção, escalonamento e metas | Campos CONFIGURATION_ONLY; envio externo requer CODE_CHANGE_REQUIRED após EXTERNAL_DECISION + EXTERNAL_PROVISIONING. Preencher destino não implementa envio/entrega/ACK | CA-16/17/18: reports, entrega, reconhecimento e acordo separados |

Os defaults de DB da **versão fixada 0.72.0** são, em ordem, GCR mirror e
GHCR: `mirror.gcr.io/aquasec/trivy-db` → `ghcr.io/aquasecurity/trivy-db`,
e equivalentes `trivy-java-db`. Fontes oficiais:
[flags](https://github.com/aquasecurity/trivy/blob/v0.72.0/pkg/flag/db_flags.go),
[DB](https://github.com/aquasecurity/trivy/blob/v0.72.0/pkg/db/db.go) e
[Java DB](https://github.com/aquasecurity/trivy/blob/v0.72.0/pkg/javadb/client.go).
São dependências documentadas, não tráfego observado nesta sessão.

Esse mapa não é uma allowlist de firewall completa: incluir resolução de
GitHub/API/Actions/artifacts, OIDC, ECR/API/layers, redirects/CDNs, downloads
dos installers e distribuição das raízes Sigstore conforme versões efetivas.
O helper manual de certificados também acessa curl.se para o insumo Mozilla,
distinto do store público fornecido por Wolfi às imagens atuais. Network
confirma o tráfego real por etapa autorizada; não inventar grants S3 pela URL
pré-assinada de layer ECR ou pela aquisição manual de CA.
Os projetos mínimos compilados usam rede desativada e dependências padrão;
não exigir npm/Maven/NuGet remoto como requisito desses contratos por associação.

## 3. Quem fornece, autoriza, executa e aceita

Os papéis abaixo são **propostos por competência**, não pessoas nomeadas ou
aceites corporativos já concedidos. Cada resposta futura deve registrar
responsável real, data, escopo, referência autorizada e evidência, fora do
repositório público quando restrita.

| Papel | Entrega/ação a solicitar | Decisão e limite |
| --- | --- | --- |
| Containers Products | Manter código/contratos/pins, mapa de destino, testes e operação; coordenar adoção e piloto | Autoria já informada no ADR-0003; não cria IAM nem assume SLA unilateral |
| Administração GitHub | Dois repos, IDs, acessos/owners, Actions permitidas, compartilhamento, proteções e eventos viáveis | Confirmar regras centrais e acesso ao segundo checkout sem ampliar privilégios dos executores |
| Cloud/IAM | Conta/região/provider/role, recursos ECR, consumidor e camadas efetivas de autorização | Avaliar P1-04; usuário não tem autonomia para aplicar IAM corporativo |
| Network / responsáveis por runners | Egress, endpoints/rotas, capacidade Docker/QEMU, isolamento e trust TLS do host | Mirror/runner próprio só quando requerido/decidido; não é autorização dada pelo agente |
| PKI / Segurança | Fonte/manifesto de CA, fingerprints, legitimidade e distribuição; endpoints para aceite TLS | Não fornecer private key para o pacote; CA de teste não aprova PKI real |
| AppSec/Segurança/Auditoria | Requisitos da fábrica federada, Trivy, integração SCA se aplicável, Sigstore, retenção e exceções | Levantamentos de outras esteiras não são normas; scanner de aplicação é outra decisão |
| Operação designada + produto | Canal, destinatários, janela/escalonamento, entrega/ACK, dados e avaliação das metas | Nenhum plantão/24x7/SLO/SLA aprovado neste pacote |
| Time piloto consumidor | Identidade por índice, verificação, build/teste da aplicação e aceite de uso | Assinatura da base não assina imagem final nem substitui controles do consumidor |

Questões externas que condicionam execução: quais requisitos se aplicam à
fábrica; Trivy atende; há integração adicional obrigatória; dados/metadados
podem ir aos serviços do ADR-0002; quais evidências/retenções e regras centrais;
quais recursos/acessos/runners serão disponibilizados; quem atende e aceita.
Não perguntar novamente se workflows próprios são autorizados.

## 4. Ordem de execução posterior

Nenhuma etapa externa foi executada nesta fatia. A configuração inicial dos
repos deve impedir execução operacional não autorizada durante a importação;
admins definem o procedimento disponível no destino. Importar uma main que
publica não pode disparar signing/push antes das decisões e dos recursos.

### A — Resolver decisões que condicionam execução
**Pré-condições/entradas:** contratos P1-04, ADR-0002/0003, P1-08 e mapa acima;
fornecedores ainda a nomear. **Responsável:** produto coordena; cada owner
da seção 3 decide sua competência.
**Procedimento/autorização:** respostas documentadas sobre scanner, serviços,
PKI, GitHub/runner/rede, IAM/provisionamento, retenção e operação. Nenhuma
aplicação de recursos decorre do aceite documental.
**Resultado/evidence:** requisitos aplicáveis, decisões e bloqueios vinculados
a CA-01. **Interromper:** decisão obrigatória ausente/rejeitada; não inventar
alternativa. **Recuperação:** voltar ao owner/ADR correspondente com escopo
delimitado, preservando decisões anteriores.

### B — Obter recursos e acessos
**Pré-condições/entradas:** A aceita para o escopo, conta/região/repos/owners
fornecidos e autorização do operador. **Responsável:** admins/Cloud/IAM,
Network/PKI/runner conforme PAR.
**Procedimento/autorização:** usar o plano P1-04 para validação oficial,
simulação e laboratório quando autorizados; provisionar recursos isolados de
teste, acesso da biblioteca e consumidor. Aplicações/leituras privilegiadas
exigem autorização e operador específicos, não execução pelo pacote.
**Resultado/evidence:** configuração efetiva sanitizada, versões/ARNs e
resultados CA-02/03/04/05; referência de baseline para reversão.
**Interromper:** falta de acesso seguro, requisito de rede/PKI ou permissão
efetiva incompatível. **Recuperação:** operador restaura só recursos de teste
aprovados pelo procedimento P1-04; não tocar a fábrica sandbox.

### C — Configurar identidades e referências
**Pré-condições/entradas:** parâmetros reais de B e decisões sobre os ajustes
condicionais. **Responsável:** produto prepara mudanças; owners revisam;
admins aplicam settings autorizados.
**Procedimento/autorização:** seguir [renomeação](repository-rename.md),
[reuso](m09-m12-reusable-workflows.md), [PKI](image-composition.md), P1-04
e os ajustes da seção 6. Primeiro publicar release shared com referências
internas aprovadas, depois adotar seu SHA nos callers e no checkout.
Não alterar o shared fixado em silêncio.
**Resultado/evidence:** diffs/configuração revisados, par repo/owner IDs,
subject e identidade registrados, pins/manifesto aprovados; CA-02/06/09.
**Interromper:** novo nome sem entrada de identidade/IDs, SHA/origem errados,
MOCK/test na release ou acesso privado inseguro.
**Recuperação:** restaurar configuração revisada anterior por processo de
mudança; procedimento de rename cobre mais que a condition repository.

### D — Validar sem publicação
**Pré-condições/entradas:** C revisada, acesso e runners para testes aprovados.
**Responsável:** produto; PKI/Segurança avaliam os testes pertinentes.
**Procedimento/autorização:** checks locais abaixo e gates de validação
existentes em eventos autorizados de PR/branch; sem credenciais AWS em
caminhos não confiáveis. Exercitar CA-02/05/06/07/13 no escopo aprovado.
Os comandos locais não fazem provisionamento ou publicação.
**Resultado/evidence:** logs completos, versões, planos de contratos,
índices/arquiteturas, scans e confiança instalada. **Interromper:** falha de
pin/PKI/scan/contrato ou capacidade do runner. **Recuperação:** diagnosticar
pelo P1-08, corrigir a causa em nova revisão, sem relaxar gates.

Do checkout revisado e com a biblioteca no SHA exigido, conforme
[CONTRIBUTING](../CONTRIBUTING.md):

```bash
make test-unit test-integration lint-local lint-shared lint-workflows
python3 -B tools/check_ai_context.py
git diff --check
```

### E — Executar a primeira cadeia no ambiente autorizado
**Pré-condições/entradas:** A–D satisfeitas para lote explícito, destinos e
janela autorizados; serviços Sigstore aprovados antes de transmitir metadata
ou SPDX corporativo. **Responsável:** produto executa; Cloud/AppSec dão suporte.
**Procedimento/autorização:** usar workflow.yml/main/build-push conforme
[configuração no README](../README.md#configuração-dos-workflows-reusáveis).
Execução/push são ações futuras autorizadas, não comandos automáticos do pacote.
Primeiro piloto runtime com seu par -dev quando exigido pelo plano; Go1-26
é candidato possível somente se ainda elegível, não promessa de scan verde.
**Resultado/evidence:** build/scan/contrato → OCI aprovado → cópia com digest
preservado → assinatura/provenance/SPDX; CA-07/08/09/12.
**Interromper:** qualquer gate falho ou evidence incompleta. Tag de build
existente não prova release completa.
**Recuperação:** preservar artifacts; retry P1-02 somente quando elegível;
não rebuildar no publicador nem usar resultado incompleto como sucesso.

### F — Promover, recuperar e exercitar consumo piloto
**Pré-condições/entradas:** E completa, candidato elegível e digest autorizado,
soak cumprido, alvo isolado de testes de recuperação e piloto acordado.
**Responsável:** produto, operador autorizado de recovery e consumidor piloto.
**Procedimento/autorização:** [promoção](../README.md#gate-de-promoção-para-stable-canário-de-soak),
[recovery](../README.md#recuperação-de-stable-runbook-m15) e
[consumo](consumer-verification-contract.md). Escrita de stable, recovery e
mudança de quarentena requerem autorização específica; não provocar falha
destrutiva nem teste negativo sobre stable com consumidores.
**Resultado/evidence:** CA-10/11/14/15, incluindo read-back e evidências
verificáveis para o mesmo índice.
**Interromper:** mismatch, assinatura/provenance não verificável, scan bloqueado
ou piloto falho. No-op não é promoção.
**Recuperação:** runbook M15 preservando gates e digest de retorno aprovado;
quarentena exige alteração explícita revisada, não é aplicada pelo lembrete
do workflow. Reverter base não reverte aplicações já publicadas.

### G — Registrar liberação ou não liberação
**Pré-condições/entradas:** resultados completos por CA, escopo/frameworks e
consumidores, responsáveis e operação definidos.
**Responsável:** produto consolida; aceitantes designados registram decisão.
**Procedimento/autorização:** comparar requisitos aplicáveis com a evidence
de destino, resolver CA-16/17/18 e registrar exceções/remanescentes com owner
e revisão. Não inferir aceite de ausência de resposta.
**Resultado/evidence:** termo de decisão com escopo, digests, versões,
aprovadores e pendências; nenhum SLA numérico inventado.
**Interromper/não liberar:** requisito obrigatório sem decisão/teste, identidade
ou PKI não verificada, IAM incompatível, release incompleta ou operação exigida
sem atendimento comprovado.
**Recuperação:** manter o destino sem liberação/expansão e retornar à etapa
bloqueante. Melhorias não obrigatórias só podem permanecer abertas com decisão
rastreável; isso não dispensa gates nem fecha outra spec por inferência.

## 5. Checklist de aceite do destino

IDs CA-xx são identificadores deste checklist, não prioridades novas.
As duas tabelas se complementam pelo ID: a primeira define requisito, escopo,
pré-condições/dependências e teste/resultado; a segunda define evidence,
executor, aceitante e estado. A realização e a aceitação devem ser registradas
separadamente. Todos os testes de destino continuam **NOT RUN**.

### Requisitos e procedimentos

| ID | Requisito e escopo | Pré-condições / dependências | Procedimento e resultado esperado |
| --- | --- | --- | --- |
| CA-01 | Regras e decisões aplicáveis aos dois repos/produto | A para decisões/definições; B para verificação dos repositórios provisionados; PAR-01/05/18/20 | Em A, conferir respostas ADR-0002/0003/P1-08 e definir owners e regras de proteção/acesso, com aprovação específica de serviços/scanner. Após B, verificar configuração observável dos repositórios, proteções e permissões efetivas; essa verificação posterior não é pré-condição de B. Não confundir autoria ou scan com homologação |
| CA-02 | Reuso e caminhos não confiáveis | A–C; PAR-02–05, acesso seguro | Checks de [reuso](m09-m12-reusable-workflows.md): origem/SHA/bytes/inputs corretos e action Trivy consistente; download de reusable e checkout explícito funcionam com acesso aprovado. PR/fork viável não recebe AWS/OIDC/secrets; SHA divergente e acesso indevido não aprovam; restrição de forks documentada |
| CA-03 | Autenticação AWS nas rotas diretas/reusáveis | B/C; PAR-07/08; [P1-04 A07/A09](../specs/2026-09-13-iam-permission-contract/acceptance.md) | Assunção autorizada nos caminhos main previstos; principal/ref não autorizado rejeitado pela condição pretendida. Registrar claims sanitizadas por rota; não presumir job_workflow_ref em dispatch direto |
| CA-04 | Autorizações ECR efetivas e consumidor | B; PAR-10/11; [plano IAM](iam-permission-contract.md) | Perfil compatível lê/publica/configura recurso autorizado; outro repo/conta/região e administração não concedida têm negativo isolado com AccessDenied correto. Registrar que publisher pode mover stable e alterar mutabilidade; não testar isolamento inexistente |
| CA-05 | Execução/egress/pins no runner de destino | B–D; PAR-06/14–17 | Docker/QEMU, Melange, Apko, tools/DBs e APIs funcionam com TLS/pins; arquitetura nativa/emulada registrada. Negativo de pin/chave ou resposta inválida bloqueia; falha de rede é infraestrutura, não resultado de segurança |
| CA-06 | PKI corporativa e stores dos runtimes | C/D; PAR-12–14; [composição](image-composition.md) | Manifesto/anchors aprovados, sem MOCK/test/private key; stage/verify positivos e cópias adulteradas/ausentes/inválidas rejeitadas. Cinco famílias × duas arquiteturas fazem TLS com CA corporativa instalada e rejeitam CA desconhecida; endpoint/fixture controlados autorizados, sem bypass ou chave privada corporativa |
| CA-07 | Build, scan e funcional por índice/plataforma | D/E; CA-05/06; lote/plano explícitos | OCI amd64+arm64 e relatórios por arquitetura; Trivy gate e contratos previstos no [plano runtime](../scripts/pipeline/runtime/runtime_images.py) aprovados. Par -dev incluído quando necessário; ausente/corrompido/scan fail não produz OCI aprovado; skips não são PASS |
| CA-08 | Publicação do artifact validado | E; CA-03/04/07 | [verify_publication](../scripts/pipeline/release/verify_publication.py): índice validado=copiado=observado, manifests corretos, sem rebuild/repack. Tag de build imutável testada em recurso isolado; considerar job inteiro e CA-09 antes de afirmar release completa |
| CA-09 | Assinatura, provenance e SBOM corretos | A/C/E; PAR-09/18; CA-08 | [Contrato de consumo](consumer-verification-contract.md): Cosign + gh para índice, mesma identidade/IDs esperados; negativos por identidade/IDs/digest incorretos. SPDX original do índice e de cada plataforma atestado/verificado no próprio subject. Não atribuir SLSA level, scan ou assinatura final da aplicação |
| CA-10 | Promoção confirmada | F; CA-09; [P1-01 A01–A07](../specs/2026-09-13-stable-promotion-readback/acceptance.md) | Candidato selecionado/verificado → soak → re-scan → stable escrita → read-back pela tag → digest igual → promoted=true; falhas de consulta/ausência/ambiguidade/mismatch não aprovam. Negativos controlados fora de stable de uso; no-op/soak incompleto registrados separadamente |
| CA-11 | Recovery e quarentena | F; digest de retorno autorizado; [M15](../README.md#recuperação-de-stable-runbook-m15) | Verificar alvo, re-scan, retag e read-back; preservar anterior/novo/reason/operator. Mudança de quarentena revisada exclui digest retirado da seleção; lembrete do workflow não prova que foi aplicada. Não restaurar digest sem verificação |
| CA-12 | Retry sem rebuild no mesmo run | E; OCI ainda retido; [P1-02 A01–A08](../specs/2026-09-13-partial-retry-without-rebuild/acceptance.md) | Attempt anterior PASS + falha downstream legítima/transitória ou barreira futura revisada antes de escrita → rerun failed jobs; mesmo run/revisão/framework/índice/plataformas/par-dev, PASS reutilizado, sem falha producer relevante mais nova, sem Apko/repack/novo digest. Ausência/conflito/cross-run falham; não fabricar falha insegura |
| CA-13 | Wolfi/preflight/rotação e drift | D; PAR-15/16; [P1-03 A01–A10](../specs/2026-09-13-wolfi-signing-key/acceptance.md) | Chave local + pin confirmados antes de Apko/Melange; lock/build verifica APK normalmente. Negativos isolados de chave/pin/arquivo; drift detecta sem escrever. Preservar EXPECTED TOOLING LIMITATION REPRODUCED de discovery; não exigir 404 nem declarar exclusividade |
| CA-14 | Consumo piloto verificável | F; CA-06/09/10; PAR-11 | Resolver/fixar um OCI index digest, verificar assinatura/provenance/SPDX conforme policy e consumir o mesmo índice; testar aplicação e variantes -dev. Registrar imagem final e seus controles separadamente; evidence disponível não é admission enforcement |
| CA-15 | Retenção e recuperação de evidence | B/F; PAR-19; [operação §4](m11-m04-operational-health.md) | Conferir uploaders/settings/quotas, download autorizado e prazo real; preview lifecycle com conteúdo representativo, incluindo formatos atuais de referrers/subjects, em recursos de teste. Provar preservação necessária a retry/recovery/auditoria; report 30d não prolonga OCI 3d |
| CA-16 | Saúde e diagnóstico com limites conhecidos | D/G; PAR-20; [operação §2/5/7](m11-m04-operational-health.md) | Report de destino com janela, paginação/truncamento, timestamps/ausências e classes por framework. Separar proxy de jobs de release verificável, no-op de promoção e exclusão de saúde; gaps do scheduler não viram monitoramento independente |
| CA-17 | Entrega e reconhecimento de alerta quando integração existir | G; decisão/canal/owner e implementação futura P1-08 | Teste controlado autorizado: detecção → relatório → envio → entrega → ACK; preservar horários/comprovantes, testar falha de envio/encaminhamento. Sem integração, permanecer NOT RUN/NOT IMPLEMENTED; preencher external_destination não aprova |
| CA-18 | Liberação e acordo operacional por escopo | G; decisões aplicáveis e CA anteriores, sem aceite implícito | Responsáveis reais avaliam evidências, atendimento/escalonamento, metas com dados suficientes e acordo com consumidores; decisão explícita de liberar/não liberar. Sem SLA acordado, registrar EXTERNAL_PENDING, sem prazo/24x7/percentual inventado |

Para negativos, registrar alvo, condição pretendida e causa observada.
Timeout, recurso inexistente, JSON inválido do harness ou token expirado não
substituem negativo IAM/TLS. Ausência de Allow no template não comprova
negação efetiva; seguir P1-04. Testes destrutivos ou com escrita só em recursos
isolados expressamente autorizados, nunca na stable já usada pelo consumidor.

### Evidence, execução, aceite e estado

Cada registro deve incluir conta/repo de destino em local autorizado, commit,
run/attempt/job, framework, OCI index e manifests quando aplicáveis, timestamps,
versões/policies e links/hashes de artifacts. Não publicar JWTs, credenciais,
private keys, relatórios integrais ou metadados corporativos restritos.

| ID | Evidence específica necessária | Executor proposto | Aceitante a designar | Estado atual de destino |
| --- | --- | --- | --- | --- |
| CA-01 | Decisões datadas, requisitos aplicáveis, owners e regras definidas em A; configuração observada dos repositórios, proteções e permissões efetivas após B | Produto + admins | AppSec/Segurança e owners por competência | NOT RUN / decisões EXTERNAL_PENDING |
| CA-02 | Callers/SHAs, commits internos da action, logs de acesso/restrição e permissões por job | Produto + admins | Responsáveis GitHub/Segurança | NOT RUN |
| CA-03 | Trust/versões, metadados sanitizados de sessão/claims e negativos por rota | Operador IAM autorizado + produto | Cloud/IAM | NOT RUN |
| CA-04 | Policies efetivas/restrições, requests/resultados por ação/recurso e limitações stable | Operador de laboratório + piloto | Cloud/IAM/Segurança | NOT RUN |
| CA-05 | Tool versions/pins, logs de download/egress/capacidade, nativo/emulado | Produto + plataforma | Responsáveis runner/rede/Segurança | NOT RUN |
| CA-06 | Aprovação PKI, hashes do manifesto/âncoras, stores e TLS por família/arquitetura | Produto + operador de endpoints PKI | PKI/Segurança | NOT RUN |
| CA-07 | Plano de lote, validated-index, locks/SPDX, scans, runtime reports e motivos de skip | Produto | Produto + AppSec para requisito de scan | NOT RUN |
| CA-08 | OCI local/copiado/remoto, publication-evidence, job completo e negativo imutabilidade | Produto | Responsáveis release/Cloud | NOT RUN |
| CA-09 | Saídas verificadas Cosign/gh, IDs certificados, SPDX/subjects e negativos | Produto + piloto | Segurança/AppSec | NOT RUN |
| CA-10 | promotion-evidence, promotion-scans, read_back_status=confirmed, candidate_digest=stable_digest_observed, promoted=true, intervalo do step | Operador de promoção autorizado | Responsável release | NOT RUN |
| CA-11 | recovery-evidence, anterior/novo, re-scan/read-back, decisão de quarentena e seletor | Operador de recovery autorizado | Responsável release/Segurança | NOT RUN |
| CA-12 | Dois attempts, IDs de artifacts/jobs, runtime-gate-result, digests iguais e ausência de rebuild | Produto | Responsável release | NOT RUN |
| CA-13 | Preflight/hash, lock/build, negativos/monitor e limite de discovery registrado | Produto | Segurança + mantenedor da trust | NOT RUN |
| CA-14 | Índices fixados, verificações, testes e identificação da aplicação final | Time piloto | Responsável consumidor + produto | NOT RUN |
| CA-15 | Retenção real, preview/downloads, preservação de subjects/referrers e acesso autorizado | Cloud/admins + produto | Auditoria/Cloud e responsável release | NOT RUN |
| CA-16 | Health/pins/summary/timing com fontes, lacunas e diagnóstico sem extrapolação | Produto | Operação designada | NOT RUN |
| CA-17 | ID de alerta/run, envio, recibo, ACK e falha de entrega testada | Operação/produto após integração autorizada | Dono do canal/atendimento | NOT RUN; emissor externo NOT IMPLEMENTED |
| CA-18 | Termo de decisão por escopo, remanescentes/owners/revisão e acordo operacional | Produto consolida | Responsáveis corporativos e consumidores | NOT RUN / EXTERNAL_PENDING |

**Limites que o aceite deve enxergar:** a identidade assinada suportada é o
índice multiarch. SPDX por plataforma não é assinatura de imagem/provenance
independente dessa plataforma. Assinatura da base não assina a aplicação final.
Os contratos diretos e os skips são os do plano runtime, não uma cobertura
universal. O gate sintético de CA instalada (`image`) e o teste suplementar
do candidato (`injected-runtime-ca`) não provam PKI corporativa; CA-06 exige
endpoints e insumos reais autorizados. Não usar private key corporativa como
fixture `--baked-ca` dos testes sintéticos.

O [ADR-0002](adr/0002-sigstore-trust-model.md) documenta que o verificador atual
não filtra explicitamente o tipo da assinatura dedicada Cosign. Não prometer
que remover somente essa assinatura, mantendo outros bundles aceitos, produzirá
o negativo esperado. CA-09 deve verificar as três evidências distintas e
registrar essa limitação; requisito corporativo adicional exige tratamento
próprio, não interpretação otimista deste checklist.

## 6. Pendências transformadas em próximas ações

### A. Ajustes locais necessários ou condicionais

A portabilidade do resolvedor possui implementação local na subfatia técnica
vinculada abaixo; sua adoção no destino e os demais ajustes continuam pendentes.
Códigos PAR/CA são do pacote, sem nova prioridade ou backlog concorrente.

| Ajuste / evidência do problema | Resultado necessário e componente | Dependência | Critério de aceite / fatia |
| --- | --- | --- | --- |
| Mudança de origem da biblioteca exige adoção coordenada | Resolvedor e validação local implementados na [subfatia de portabilidade](../specs/2026-09-14-shared-origin-portability/spec.md); para o destino, atualizar policy, callers, action, checkout, [.github/dependabot.yml](../.github/dependabot.yml) e documentos ativos/teste documental enumerados abaixo | Nome/acesso/release reais aprovados; fixture sintética não comprova integração no destino | CA-02: origem esperada, SHA exato de cada referência, bytes íntegros, agrupamento e documentação ativa coerentes; inputs/permissões e snapshots históricos preservados; P0-03/reuso M09/M12 |
| Segundo checkout usa token do próprio repo | Solução de leitura cross-repository segura se biblioteca for privada, em [test-promotion.yml](../.github/workflows/test-promotion.yml) | Decisão de visibilidade/acesso admins; sem secrets a PR/fork | CA-02 com limites de eventos documentados, falha fechada e sem ampliar executor; P0-03 |
| Runners literais e sem input shared | Se destino exigir outros runners, adaptar interface/callers e release shared sob revisão | Plataforma/Segurança decide capacidade/labels | CA-05 e contratos reais por arquitetura; P0-03, sem obrigação de ARM nativo |
| Aquisição CA presume lista/object keys | Se fonte aprovada divergir, adaptar estreitamente helper/inputs, mantendo pins e stage/verify | Fontes/manifesto da PKI | CA-06 positivos/negativos e sem aquisição AWS recorrente implícita; M10/P0-03 |
| Host/ref/path ou prefixo diferentes dos suportados | Ajustar verificadores/callers/referências somente se PAR-09/10 exigir | Identidade/nomenclatura corporativa confirmadas | CA-03/04/08/09/10 sem wildcard ou perda de IDs; P0-03 |
| Integração scanner, alerta ou egress alternativo exigida | Fatia própria para requisito confirmado; não copiar thresholds/bypasses ou inventar emissor pelo campo destination | ADR-0003, ADR-0002 e P1-08; decisão/serviço/autorização | CA-05/07/09/17 conforme requisito; fatias existentes P1-06/P1-08/P0-03 |

Cadastro de signing-identities/IDs, owners, vars, parâmetros IAM e manifesto
de CA são mudanças declarativas revisadas de C, não justificativa para
renderizador universal ou substituição em massa. Nenhuma foi feita aqui.

### B. Aceites sandbox ainda pendentes
P1-02: retry/reuse hospedado PASS no run `34889507318`, sem rebuild; a
continuação de publicação permanece pendente, conforme [evidence](../specs/2026-09-13-partial-retry-without-rebuild/evidence.md).
P1-03: revisar a nova comprovação do mínimo preflight/chave
local dos dois Go; o lote permanece PARTIAL / BLOCKED_UPSTREAM, sem
inferir exclusividade. P1-04: validador/simulador/laboratório autorizado; P1-08:
integração/entrega/ACK e operação após decisões. Resultados futuros entram na
fatia correspondente; não são transferência automática para o corporativo.

### C. Parâmetros e decisões corporativas
Solicitar os dados PAR-01–20 e decisões da seção 3 com owners reais.
Sigstore, scanner, PKI, acesso privado, runners, IAM e operação não se resolvem
por aprovação deste texto. Levantamentos corporativos integrais continuam fora
do repositório público.

### D. Provisionamento e operação autorizados
Executar B–G por operadores designados, preservando configuração anterior e
evidence de recursos isolados. Cloud/IAM decide recursos e permissões efetivas;
produto não adquire autonomia administrativa por manter workflows federados.

### E. Melhorias futuras não bloqueantes por inferência
Os gaps de [P1-08](m11-m04-operational-health.md) permanecem: proxies de jobs
para publicação/stable; limites declarados sem avaliação (`queue_delay_p90_seconds`,
`update_pr_stale_days`); resumo com ordenação/interpretação de artifacts que
não aplica o binding do publicador; scheduler compartilhado sem detector
independente. Não foram corrigidos e não demonstram falha dos gates de
promoção/retry. Não usá-los como SLIs mais fortes do que medem.
Sua obrigatoriedade depende do requisito operacional aprovado; enquanto não
exigidos, ficam como melhorias registradas, não pretexto para expandir esta
fatia. Watchdog, mirror generalizado, Renovate, admission, VEX e ARM nativo não
são adicionados automaticamente ao plano obrigatório.

### Portabilidade: subfatia técnica e adoção posterior

A [implementação local](../specs/2026-09-14-shared-origin-portability/evidence.md)
foi integrada pelo PR #62. A coleta de 14/09/2026 registra PASS hospedado
observado na origem sandbox (PR e main), sujeito à revisão independente da
reconciliação; migração real e acesso privado continuam pendentes.
A sequência abaixo permanece necessária para mudar a origem
operacional, sem usar o SHA de fixture como release publicado.

**P0-03 — Portabilidade da origem da biblioteca compartilhada**, começando pelo
resolvedor, callers, action e checkout, incluindo o padrão do grupo
`reusable-container-pipeline` em [.github/dependabot.yml](../.github/dependabot.yml)
que contém o nome da origem. A mudança não deve deixar o agrupamento apontando
para o repositório anterior. É uma dependência concreta da adoção dos dois
repositórios, pode ser implementada/testada localmente com origem sintética e
não exige decidir/aplicar IAM ou operar produção.

Atualizar também as referências ativas de origem/pins na
[RFC-013](../RFC-013-Image-Base-Completa-com-Mermaid.md), no
[contrato de reuso](m09-m12-reusable-workflows.md), no [README](../README.md)
e na [arquitetura](repository-architecture.md), com a verificação documental
correspondente em [test_consumer_documentation.py](../tests/unit/pipeline/governance/test_consumer_documentation.py),
que exige origem/pin corrente nesses quatro documentos. Preservar os
snapshots históricos que registram origens/pins anteriores.

Critério: origem explicitamente aprovada resolvida em todos os callers,
checkout no SHA comum dos reusables e íntegro, pin próprio da action consistente
entre suas chamadas, agrupamento de atualizações e documentação ativa coerentes
com as referências executáveis. Manter SHA exato em cada referência, distinguindo
o pin do reusable do pin da action; preparar o release compartilhado antes de
adotá-lo, conforme etapa C. Negativos locais para origem/SHA inesperados e
falha da fronteira Git integram a subfatia técnica; não comprovam acesso privado.
Permissões e os seis adaptadores permanecem preservados.
Se a biblioteca for privada, a solução de acesso de PAR-04 depende da decisão
dos admins antes de qualquer credencial; não inventar autorização.
A origem operacional e os pins reais permanecem sandbox. Nenhum release
compartilhado novo foi publicado nem foi comprovado acesso privado corporativo.

## 7. Registro de liberação

Não liberar o ambiente corporativo a partir de testes locais, merge de PR,
job success isolado ou snapshot sandbox. A decisão precisa associar requisitos
aplicáveis aos resultados CA-xx, configuração efetiva, digests, responsáveis
e escopo dos consumidores/frameworks.

Bloqueio upstream de CVE pode coexistir com funcionamento correto do gate;
não autoriza liberar o framework bloqueado nem contar exclusão formal como
saúde. Soak ainda não cumprido, falta de candidato, no-op, promoção confirmada
e recovery precisam permanecer classes distintas. Read-back comprova somente
o instante observado, sem impedir alterações administrativas posteriores.

Canal sem integração, entrega/ACK não comprovados, responsáveis não nomeados,
metas sem avaliação e SLA não acordado permanecem pendências explícitas.
A documentação local pode ser revisada enquanto esses itens continuam abertos;
**P0-03 operacional não está concluído e a fábrica corporativa não está
homologada**. Resultados locais, fontes e limites desta preparação estão na
[evidence P0-03](../specs/2026-09-13-corporate-adoption/evidence.md).
