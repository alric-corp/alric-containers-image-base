# Segregação dos workflows — M09/M12 e identidade M03/M05/M16

O `image-base` já reutilizava jobs localmente. A segregação move execução
compartilhável para `alric-corp/alric-containers-reusable-workflows` e mantém as decisões
de release no produto. O primeiro pacote tem contrato Apko/OCI explícito;
não promete suportar qualquer pipeline Docker sem adaptação.

Autoria/sustentação e requisitos corporativos aplicáveis são tratados no
[ADR-0003 / P1-06](adr/0003-controles-seguranca-workflows-federados.md).
O reuso técnico descrito aqui não transfere a manutenção da fábrica a Pipelines
nem homologa seus controles corporativamente.

| Componente | Destino | Motivo |
| --- | --- | --- |
| Melange + Apko + scan amd64/arm64 + artifact aprovado | Reusable `validate-apko-images.yml` | Sequência reaproveitável para produtos que implementem o contrato Apko |
| Execução de contratos sobre OCI candidato | Reusable `test-runtime-images.yml` | Executor comum; probes, projetos e cobertura continuam sendo do produto |
| Instalação/verificação do Trivy | Composite `actions/setup-trivy` | Mesma definição em validação, promoção e recuperação, sem comandos como input |
| `workflow.yml` | `image-base` | Eventos, cron, catálogo e parâmetros AWS são decisões do produto |
| `build-base-images.yml` | `image-base` | Gates por framework, contrato de publicação, ECR e identidade do assinador |
| `promote-stable.yml` / `recover-stable.yml` | `image-base` | Soak, quarentena, concorrência, assinatura e política de recuperação são acoplados ao produto |
| `test-promotion.yml` | `image-base` | Testes de domínio e nomes dos required checks `test`/`lint-workflows` |
| Saúde operacional | `image-base` | Catálogo, crons, dono, limites e retenção são política do produto |
| `cve-triage.md` / lock gerado | `image-base` | Instruções, ferramentas e permissões do agente de triagem deste produto |
| Scripts, manifests, certificados e projetos de teste | `image-base` | Contrato e comportamento do produto, revisados com seu código |

`validate-base-images.yml` e `test-runtime-images.yml` ficam como pontos de
entrada pequenos. O primeiro preserva as chamadas locais já existentes; o
segundo preserva também o dispatch manual. Os executores remotos aceitam apenas
`workflow_call`, sem cron, dispatch ou secrets. O build e o publicador continuam
em jobs distintos, preservando o retry da publicação sem rebuild.

## Contrato e confiança

O checkout dentro de um workflow reutilizável lê o **consumidor**. Assim,
`frameworks/`, `melange/`, `scripts/pipeline/` e `tests/runtime/` continuam
resolvendo no commit do `image-base`. Isso é intencional e documentado no
[contrato do pacote](https://github.com/alric-corp/alric-containers-reusable-workflows/blob/8f82ea345b38142d43fb8f8358ae76d2d4ea97ce/docs/apko-contract.md).
Outro produto precisa implementar as mesmas interfaces antes de adotar o pacote.

Biblioteca aprovada: `alric-corp/alric-containers-reusable-workflows@7a9b055a462eeb8552d3404c26538b44e8ccd83f`.

A action Trivy e todas as demais Actions externas também usam SHA completo.
Validação recebe
somente `contents: read`; runtime recebe também `actions: read` para baixar
artifacts do próprio produto. Não há `secrets: inherit`, comandos como input
nem novos jobs com OIDC. As permissões existentes de publicação continuam
declaradas no consumidor.

O job assinador permanece em `.github/workflows/build-base-images.yml`;
`verify_promotion.py` preserva a identidade exata por workflow; a compatibilidade
com o nome anterior exige IDs assinados, conforme a [migração de nomes](repository-rename.md). Não há nova identidade de assinador a
autorizar nem wildcard para aceitar candidatos históricos. Uma futura extração
do publicador deve satisfazer o aceite de identidade já registrado na RFC antes
de ser ativada. A migração atual também não altera Environments ou trust policy IAM.

O nome e a retenção dos artifacts são parte da API:
`melange-repo` (30 dias), `validated-oci-*` (3 dias), `build-scans-*`,
`sbom-*` e `runtime-*` (30 dias). Um run deve chamar a validação uma única vez com o lote
completo, porque os nomes dos artifacts são compartilhados dentro do run.

O consumidor implementa [P1-02](../specs/2026-09-13-partial-retry-without-rebuild/spec.md):
runtime permanece nomeado por attempt; download/seleção por run e binding dos
reports aos índices atuais ficam no produto. O reusable continua executando
o módulo runtime do checkout consumidor e não precisa de mudança de interface.
Identidade do producer vem do contexto GitHub; artifact-run-id do dispatch
diagnóstico é a origem do OCI, não uma autorização de publicação cross-run.

## Checks e atualização

[policies/governance/reusable-workflows.json](../policies/governance/reusable-workflows.json)
aprova uma origem GitHub.com pelo campo `repository` (`schema_version: 1`).
O SHA continua literal nos dois chamadores; a composite Trivy conserva seu
SHA próprio. A policy não gera `uses`: [GitHub exige referência estática no
job](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_iduses),
sem expressões nesse campo.

`workflow_dependencies.py checkout` valida a policy, os dois pontos de chamada
obrigatórios, as actions Trivy de promoção/recuperação, o grupo Dependabot e
os dois checkouts do gate rápido **antes** de emitir `repository`/`ref`.
Ele não baixa a biblioteca nem verifica seu conteúdo nessa etapa. Os pontos
obrigatórios são identificados por arquivo/job/step: mudar a origem de uma
referência não permite que ela desapareça do inventário validado.

Nos checks, o segundo checkout traz o commit para `.reusable-workflows/`, sem
persistir credenciais Git. `lint` e `shared_workflows()` então conferem a URL
de fetch `origin` (HTTPS ou SSH de GitHub.com), HEAD e bytes dos **dois YAMLs
consumidos**, sem substituições por Git replace objects. Conferem ainda
`workflow_call`, inputs e igualdade da referência Trivy em validação, promoção
e recuperação, incluindo a chamada interna da biblioteca. Checkout ausente,
origem divergente, SHA móvel/divergente, YAML alterado e inputs incompatíveis
falham. O lint M16 mantém a exigência de SHA completo para dependências externas.

O escopo não atesta todos os arquivos da biblioteca nem os bytes da composite
no seu commit remoto separado. Uma URL em `origin` é metadado local, não prova
de que o commit foi publicado naquela origem ou de acesso a um repositório
privado. Essas provas exigem o aceite remoto no destino.

O executor publicado ainda usa seis scripts em `.github/scripts/`; adaptadores
sem lógica preservam essas interfaces e delegam para `scripts/pipeline/`.
Testes executam as CLIs e a API importada pelo executor, além de conferir os
paths que o release fixado exige. Veja a [arquitetura](repository-architecture.md).

O lint lê os YAML compartilhados. Na integração com o trabalho local de saúde,
`operational_health.workflow_files()` usa o mesmo resolvedor para que a
comparação com `policies/operations/health.json` continue lendo a retenção efetiva
dos uploaders remotos. Ausência do checkout falha; não omite os artifacts.
Essa verificação faz parte do `make check` e do gate rápido do produto.

Dependabot agrupa atualizações deste repositório compartilhado. O gate exige
um único SHA revisado para os workflows e a mesma action Trivy em validação,
promoção e recuperação. A action usada pelo validador tem seu próprio SHA,
definido no workflow compartilhado. Ao atualizar, alinhe as chamadas de
promoção/recuperação a esse SHA: simplesmente escolher o último commit da
action pode fazê-las divergir. O lint bloqueia essa divergência, inclusive em
PR automático.

Renovate passa a manter Apko/Melange e a versão Trivy no repositório que os
define. No produto, continuam os insumos ainda usados localmente. Configuração
versionada não comprova que o app Renovate está instalado e ativo.

Prepare o checkout no SHA declarado pelos chamadores e execute `make check`,
conforme [CONTRIBUTING.md](../CONTRIBUTING.md). Não use o checkout com alterações
locais do repositório compartilhado como substituto do release publicado.

## Mudança de origem revisada — P0-03

Para adotar outro nome/origem, uma mudança revisada deve manter coerentes:
policy de origem, os dois `uses` de workflows, as duas actions Trivy locais,
a referência Trivy interna da biblioteca, os checkouts que recebem os outputs,
o grupo `reusable-container-pipeline` do Dependabot e as referências atuais
no README, RFC, arquitetura e neste contrato. Os testes documentais conferem
essas referências; nenhum rename é feito automaticamente.

O release consumido ainda contém a chamada interna da composite na origem
sandbox. A futura adoção de outra origem exige: disponibilizar o commit real
da composite no destino; publicar o workflow com a origem aprovada e esse
SHA anterior; depois alinhar os dois chamadores e as actions locais ao release
revisado. O [README da biblioteca](https://github.com/alric-corp/alric-containers-reusable-workflows/blob/7a9b055a462eeb8552d3404c26538b44e8ccd83f/README.md)
descreve essa ordem. Não trocar a chamada interna por `./actions/setup-trivy`:
o checkout do executor pertence ao produto chamador.

Esta subfatia permite validar outra origem com fixtures locais, sem alterar
a biblioteca nem os pins sandbox. `REUSABLE_WORKFLOWS_PATH` altera somente a
localização do checkout; `--root` permite ler a policy/chamadores de uma árvore
local de teste, sem override da origem por variável de ambiente. Acesso privado
permanece `EXTERNAL_PENDING`; aceite hospedado desta portabilidade é `NOT RUN`
e a revisão independente permanece pendente. Não há novas credenciais, secrets
ou permissões para os executores. A execução corporativa segue o
[pacote de adoção](corporate-adoption.md).

## Adoção e evidências

PRs: [reusable-workflows #1](https://github.com/alric-corp/alric-containers-reusable-workflows/pull/1) e [image-base #45](https://github.com/alric-corp/alric-containers-image-base/pull/45).
A migração de pastas usa o commit já publicado. A proposta local de consumir
`@v1` foi substituída por SHA completo: a tag não existia na consulta de
10/09/2026, e o pin evita mudança implícita do executor entre execuções.
Os arquivos locais ainda não publicados da biblioteca não são necessários
para o consumidor reorganizado.

A consulta inicial encontrou a biblioteca pública e `main` sem proteção.
Nos ajustes finais de 10/09/2026, a proteção foi aplicada e relida: três checks
obrigatórios, aprovação independente de CODEOWNERS, descarte de aprovações
antigas, aprovação do último push e `enforce_admins`. O time recebeu escrita
e `sha_pinning_required` foi ativado. A configuração reproduzível está no
[PR #3](https://github.com/alric-corp/alric-containers-reusable-workflows/pull/3).
Esse parágrafo registra o estado observado em 10/09; não é inventário atual
de proteções corporativas. O pin atual indicado acima já está integrado ao
produto; o [PR #2](https://github.com/alric-corp/alric-containers-reusable-workflows/pull/2)
é parte do histórico da migração. [Evidência remota](evidence/release-readiness-2026-09-10.json).

A validação local e os runs autenticados estão registrados abaixo e na RFC
com seus limites. Um check aprovado não comprova publicação ECR, promoção, recuperação
ou execução do cron; os aceites remotos dos demais itens continuam separados.

Referências: [reuso e permissões](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows),
[contexto do chamador](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations),
[OIDC e workflow chamado](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-with-reusable-workflows).

## Evidências da segregação — 10/09/2026

- Biblioteca: 11 testes, hardening, actionlint e instalação real do Trivy
  [aprovados](https://github.com/alric-corp/alric-containers-reusable-workflows/actions/runs/34431800269).
- Consumidor: `test` e `lint-workflows`
  [aprovados](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34432303109).
- Validação de PR pela biblioteca: [14 de 15 frameworks aprovados](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34432303814).
  `dotnet8` foi bloqueado nas duas arquiteturas pelo scan: `CVE-2026-47304`
  (CRITICAL), `CVE-2026-47302`, `CVE-2026-50525` e `CVE-2026-50648` (HIGH),
  com versão de correção `8.0.129-r1` reportada pelo Trivy. Nenhum artifact
  `validated-oci-dotnet8` foi liberado; publicação e promoção ficaram `skipped`.
- Runtime Python 3.13: [amd64 nativo e arm64 emulado aprovados](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34432393980),
  consumindo o artifact do run de validação acima. UID/GID, filesystem somente
  leitura, tmpfs e TLS positivo/negativo passaram sobre o mesmo índice OCI.
- Local: 123 testes de pipeline + 13 de certificados na branch isolada;
  168 testes e a política de retenção aprovados na árvore com os trabalhos
  preexistentes de runtime/saúde. O runtime compilado dessa árvore não foi
  exercido no dispatch hospedado desta segregação.

[Registro com commits, digests e relatórios](evidence/reusable-workflows-2026-09-10.json).
Os runs correspondem ao commit funcional `974384c`; a atualização posterior
registra somente documentação/evidências. Publicação ECR, promoção, recuperação
e merge não foram executados nesta entrega.
