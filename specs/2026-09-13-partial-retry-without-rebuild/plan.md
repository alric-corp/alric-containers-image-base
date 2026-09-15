# PLAN — P1-02

## Baseline e diagnóstico

Origin/main consultada: `285ada4d6948c2d7e7508dd0ba8883c38306c7a1`, merge do
P1-03; árvore inicial limpa. Branch local `feat/partial-retry-without-rebuild`.
Shared efetivamente consumido: `7a9b055a462eeb8552d3404c26538b44e8ccd83f`.

OCI usa `validated-oci-<framework>`, overwrite true após scan. Runtime usa
`runtime-<framework>-<run_attempt>`. Publicador procura somente attempt atual.
Reports já possuem index_digest/manifest_digest e, em compilados, digests do
par -dev; gate atual só compara status. Run/attempt/repository/revisão ainda
não constam nos reports. Código atual confirma o problema histórico.

## Implementação mínima no produto

1. Acrescentar contexto GitHub aos reports no módulo runtime do consumidor;
   o reusable já executa esse código. Não alterar shared ou pins das Actions.
2. Baixar runtime por pattern de suffix numérico no mesmo run/repository, sem
   merge de diretórios e preservando erro de checksum ZIP do download v8.
3. Obter metadados completos de artifacts e jobs desse run por API paginada.
   Isso detecta nomes duplicados, downloads incompletos e producer falho que
   não chegou a escrever reports, sem usar resultado agregado de outro framework.
4. Implementar seleção offline no domínio runtime: validar metadados,
   layouts flat (um match v8) e por artifact (múltiplos), JSONs e identidades;
   comparar índices/manifests com OCI atual verificado; ordenar attempts como int.
5. Para contratos compilados, baixar também o OCI validado atual do par -dev
   e conferir seus digests. É leitura/verificação adicional, não rebuild.
6. Gate guarda runtime-gate-result.json, incluindo artifact ID/nome/attempt,
   run corrente e digests. Publicação preserva esse resultado com suas evidências.
7. Testar domínio/CLI sem GitHub/AWS/Docker, incluindo limite de run, conflitos,
   falhas de jobs sem artifact, paginação e ausência. Repetir checks exigidos.

## Política de seleção

API deve estar completa e sem IDs/nomes ambíguos. Cada artifact relevante
precisa ter os dois reports completos e identidades coerentes. Erro de
estrutura/JSON/digest ausente falha fechado, inclusive em histórico disponível;
não ignorar corrupção para encontrar um PASS. Isso pode exigir um novo run
quando o histórico é inválido. Pares bem formados para outros digests não
são candidatos. Do conjunto que corresponde ao índice e ao par -dev atuais,
selecionar o maior attempt; exigir ambos status passed.

O job producer mais recente por framework deve ter concluído success. GitHub
pode copiar job success para um attempt maior sem executá-lo novamente;
timestamps/steps históricos R03 confirmam isso. Não exigir report daquele
attempt artificialmente. Job falho/cancelado/incompleto ou ambíguo bloqueia.

## Risco e rollback

Consulta/API/download inconclusivos bloqueiam publicação. Overwrite mantém
somente o OCI aprovado atual; não escolher report só por nome. API e padrão
do nome do producer são contratos do reusable fixado e devem ser retestados
quando esse pin mudar. Download do par -dev acrescenta IO aos contratos
compilados. Rollback deve preservar falha fechada e não reintroduzir gate
baseado só em status nem reconstrução automática no publicador.

## Hosted acceptance

Após revisão/merge, preferir falha transitória legítima depois de contrato
aprovado. Alternativa controlada: workflow de aceite isolado, revisado antes
de adicionar, com barreira determinística de attempt1 antes de escrita externa;
no attempt2 reexecutar somente jobs falhos e copiar a um destino de teste
autorizado mantendo verificação de digest. Não alterar IAM, provocar falha
de assinatura após publicação produtiva nem mover stable para testar.
Registrar run/attempts, jobs/timestamps, IDs de artifacts, digests, gate e
continuação de publicação. Não criar/acionar esse workflow nesta entrega.

## Implementação local do laboratório — 2026-09-14

Baseline posterior: PR #63 mergeado em
`62af489234e29f7f731a7b9c6266143229087129`. O texto anterior é histórico;
o pedido atual autoriza preparar o laboratório, sem executá-lo.

1. Criar partial-retry-lab.yml com quatro jobs: validar solicitação, chamar
   validate-base-images uma vez para o par Go, chamar test-runtime-images
   para Go compilado e executar o consumer/gate/barreira de laboratório.
   Callers locais evitam novos pins ou alteração do inventário shared.
2. Manter o image-trust incluído no caller: seus cinco probes existentes
   não são um novo lote de publicação. Nenhum gate removido.
3. No consumer, baixar os dois OCI, reports e metadados paginados; executar
   a mesma CLI runtime_images --gate do publicador.
4. Acrescentar retry_lab.py só para contexto, comparação e evidência; ele não
   substitui o gate nem produz reports funcionais. Salvar baseline no attempt 1
   antes da barreira; reencontrá-la no attempt 2.
5. Comparar IDs/digests/created_at dos artifacts e execução dos producers:
   nomes, timestamps e steps iguais, admitindo IDs de jobs copiados diferentes
   somente quando a execução observável permaneceu igual. Exigir a falha
   anterior na barreira via metadados GitHub.
6. Barreira retorna exit 42 no attempt 1 e 0 no attempt 2 verificado.
   Outro erro é INVALID_SCENARIO, não falha esperada do laboratório.
7. Upload por attempt inclusive na falha; nomes runtime-lab-p1-02 usam retenção
   de reports existente (30 dias). OCI continua 3 dias.
8. Não ligar publicação: copy/read-back e subjects reais continuam dependentes
   de alvos/autorização/fiação revisada posterior. O ensaio atual não encerra
   sozinho o aceite hospedado integral do P1-02.


### Procedimento futuro exato — não executado

Pré-condições: revisão independente, integração deste workflow em main e
**autorização específica de execução**, indicando o SHA integrado. Confirmar
que o operador pode executar Actions no sandbox e preservar os artifacts.
Não criar permissões AWS. A confirmação do input é uma trava de contexto,
não uma concessão de autorização pelo software.

1. Na interface GitHub Actions, selecionar `P1-02 isolated retry evidence laboratory`,
   evento `workflow_dispatch`, branch `main`, `confirmation=P1-02-evidence-only`
   e `reviewed-sha=<SHA completo integrado explicitamente autorizado>`.
   Não usar o SHA da baseline anterior à implementação. Não há input livre
   de framework, destino, tag, role ou comando.
2. Aguardar os produtores reais: Melange, trust probes existentes, validação
   Apko/scan de `go1-26` e `go1-26-dev`, e contrato compilado nas duas arquiteturas.
   O gate deve retornar PASS, selected_attempt=1 e reused=false. Somente depois
   do manifest válido e seu upload, a barreira retorna 42/EXPECTED_LAB_FAILURE.
3. Conferir que a única falha foi `Controlled attempt-1 barrier` e que os uploads
   terminaram. Se build, scan, contrato, metadados ou upload falharem, interromper:
   essa execução não constitui o cenário aprovado. Não contornar o gate.
4. Dentro da retenção efetiva dos dois OCI (planejar até 24 horas, limite
   configurado de 3 dias), o operador autorizado usa **Re-run failed jobs**
   no mesmo run. Não usar Re-run all jobs, novo dispatch ou attempt 3.
5. No attempt 2, esperar produtores herdados e somente `Lab retry gate`
   reexecutado. O gate real deve produzir passed=true, selected_attempt=1,
   reused=true; a comparação deve produzir REUSE_OBSERVED e a barreira exit 0.
   A publicação não ocorre, mesmo após esse sucesso.
6. Depois de o job terminar, coletar em leitura os metadados completos dos dois
   attempts, logs e artifacts abaixo. Conferir também conclusão real do consumer
   e upload final: o manifest foi produzido durante o job, não pode atestar sua
   própria conclusão futura. Submeter a evidência ao aceite independente.

O GitHub mantém SHA/ref originais no rerun; não se executa a main atual por
inferência. Fonte: [documentação oficial de rerun](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs).
O workflow coleta jobs com `filter=all` e artifacts com paginação completa;
[metadados oficiais de jobs](https://docs.github.com/en/rest/actions/workflow-jobs)
complementam os logs, sem fabricar estado de execução.

### Retenção e checklist de evidência

| Artifact | Conteúdo / prova | Retenção configurada |
| --- | --- | --- |
| validated-oci-go1-26 e validated-oci-go1-26-dev | layouts, blobs e validated-index; IDs, hashes ZIP, índices e manifests | 3 dias, contrato compartilhado preservado |
| runtime-go1-26-1 | dois reports amd64/arm64, cada um vinculando runtime **e dev**, hashes no gate | 30 dias |
| runtime-lab-p1-02-baseline-RUN_ID | execution.json do attempt 1, antes da barreira | 30 dias, sem overwrite |
| runtime-lab-p1-02-attempt-RUN_ID-ATTEMPT | gate, execution, barrier, metadados paginados, reports e validated-index dos dois OCI | 30 dias, sem overwrite |
| melange-repo, SBOM e scan existentes | diagnóstico dos produtores reais | 30 dias, sem mudança global |

Não existe producer separado `runtime-go1-26-dev-1`: o contrato compilado
existente valida o par no mesmo report por arquitetura. O snapshot não
estende a retenção dos blobs OCI. Restrições efetivas do repositório podem
limitar retenção; conferir expires_at, tamanho e disponibilidade antes do rerun.

Checklist obrigatório para comparação:
- run_id, attempts 1/2, head_sha e workflow_ref idênticos; revisão executada;
- IDs, nomes, início/fim e steps dos producers e do consumer, em ambos attempts;
- IDs, created_at, expires_at e digest dos artifacts, sem substituição;
- índices runtime/dev, manifests linux/amd64 e linux/arm64 e hashes dos reports;
- selected_artifact/id, selected_attempt, latest_producer_job_id/attempt,
  reused e passed do **gate real**, sem reescrever os campos;
- PASS do gate, gravação/upload da baseline e posterior falha exclusiva da
  barreira no attempt 1; consumer novo concluído com sucesso no attempt 2;
- jobs herdados distinguíveis por timestamps/steps preservados, mesmo quando
  o GitHub apresentar IDs copiados diferentes; conferir logs dos IDs pertinentes;
- igualdade dos objetos retidos e da execução dos producers, e ausência de
  invocação build/repack no consumer. Igualdade de digest isolada não basta.

Dados ausentes, artifacts expirados, mudança de execução do producer, outra
falha ou novo artifact invalidam o cenário. Não tratar falha de rede como
negativo de autorização nem ausência de logs como prova de não rebuild.

### Escritas, cleanup e publicação futura

Este workflow lê fontes públicas e grava apenas artifacts/logs/status do próprio
run no GitHub. Não autentica ECR, não possui id-token:write, não assina, não atesta,
não contém etapa de publicação, promoção ou recovery. A barreira precede qualquer
possível escrita de **publicação**; uploads de evidência anteriores são necessários.
Cleanup previsto: expiração normal dos artifacts; remoção manual antecipada
exige autorização e preservação prévia das evidências. Nenhum recurso AWS a remover.

O aceite original inclui continuação da publicação; este ensaio prova apenas
sua parte anterior à escrita externa. A etapa de publicação real permanece
**não implementada e não autorizada**. Uma extensão posterior deve ser revisada
separadamente, usando o publicador real e coleta de copied_digest/remote_digest
iguais e subjects de assinatura/provenance/SBOM quando exigidos.
Conta/região, role isolada, ECR de teste já autorizado, namespace exclusivo de
laboratório, permissões efetivas, retenção e cleanup: EXTERNAL_INPUT_REQUIRED.
Nenhum ARN sintético vira destino operacional. O desenho dessa extensão deve
proibir stable, sem modificar as propostas IAM existentes. Não acionar o
publicador produtivo como substituto. A falta dessa fase impede encerrar o
HOSTED_ACCEPTANCE integral, mesmo com os dois attempts deste laboratório verdes.

## Execução hospedada registrada — 2026-09-14

O procedimento acima foi executado após autorização específica no run
`34889507318`, revisão `13b50102d29fab89509c5d539e72659529686a37`. Attempt 1
foi validado com falha exclusiva da barreira; `Re-run failed jobs` produziu o
attempt 2 com reutilização comprovada. A publicação permaneceu fora do fluxo.
Consulte [evidence.md](evidence.md) para os IDs, hashes e matriz completa.

## Proposta de infraestrutura para publication continuation — 2026-09-15

Investigação read-only da conta sandbox (detalhes completos em
[evidence.md](evidence.md#investigação-sandbox-read-only-para-infraestrutura-de-publicação--2026-09-15))
substitui os `EXTERNAL_INPUT_REQUIRED`/`UNKNOWN` do desenho anterior por
valores observados. Nenhum recurso AWS foi criado, alterado ou assumido.

```text
AWS_ACCOUNT_ID = 712107929769
AWS_REGION = us-east-1
ECR_REPOSITORY_RUNTIME = p102-lab-go1-26 (NOT_FOUND, a criar)
ECR_REPOSITORY_DEV = p102-lab-go1-26-dev (NOT_FOUND, a criar)
PUBLICATION_INFRA_DESIGN = PROPOSED
PUBLICATION_INFRA_APPLIED = NO
AWS_EXECUTION = NOT RUN
```

Recomendação de role: **CREATE_ISOLATED_ROLE**
(`github-actions-image-base-p102-lab`, nome de proposta, recurso não
aplicado). Motivo observado, não hipotético: a policy anexada à role
existente (`github-actions-image-base-ecr`) usa `Resource:
arn:aws:ecr:us-east-1:712107929769:repository/image-base-*` — um prefixo que
cobre todo o catálogo de produção. Reutilizar a role existente não criaria
isolamento nenhum por IAM: a mesma credencial que publicaria no laboratório
já alcança `image-base-go1-26`/`image-base-go1-26-dev` hoje, sem qualquer
mudança. A role nova deve ser restrita a exatamente:

```text
arn:aws:ecr:us-east-1:712107929769:repository/p102-lab-go1-26
arn:aws:ecr:us-east-1:712107929769:repository/p102-lab-go1-26-dev
```

nunca ao prefixo `image-base-*` — os nomes `p102-lab-go1-26`/
`p102-lab-go1-26-dev` foram escolhidos deliberadamente fora desse prefixo
(ver correção abaixo), e a trust primária inclui `job_workflow_ref`
restringindo a assunção ao workflow do laboratório, além de `sub`/`aud`/
`repository`/`repository_id`/`repository_owner_id`/`ref` exatos.

Perfil de execução preferido: **preprovisioned + execution-only** (Profile
A) — Cloud/operador cria os dois repositórios lab previamente como
`IMMUTABLE` sem exclusão para `stable` (ver correção abaixo), com
`scanOnPush`/`AES256`, e a role nova recebe apenas as actions de
leitura/escrita de imagem (sem `CreateRepository`/`PutImageTagMutability`).
Isso preserva o caminho de publication/integrity real (mesmos comandos de
publish/read-back/sign/attest) com o provisionamento do repositório
deliberadamente separado — bookkeeping que R7 não protege como gate, não
uma redução do que R7 exige (ver justificativa completa na correção
abaixo). Profile B (self-provisioning, só `CreateRepository` escopado aos
dois ARNs lab, sem `PutImageTagMutability`) permanece documentado como
alternativa caso o operador prefira não pré-provisionar; não foi
descartado, apenas não é a preferência.

Templates de proposta (JSON, não aplicados, não lidos por nenhum workflow):
[policies/aws/proposals/p102-lab-permissions/](../../policies/aws/proposals/p102-lab-permissions/README.md).

Repositórios de produção `image-base-go1-26`/`image-base-go1-26-dev`
permanecem fora de qualquer ARN da proposta nova — confirmado por
`describe-repositories` nesta investigação e nunca incluído nos templates.
Isolamento de `stable` combina **IAM resource isolation + repository
isolation + application guard** (dois repositórios inteiramente separados e
fora do prefixo `image-base-*`, `IMMUTABLE` sem exclusão para `stable`, mais
um guard de código a implementar que rejeita tag/destino fora do fixo
computado) — nunca uma condition key IAM por tag Docker, que não existe.

Estado inalterado por esta investigação:

```text
PUBLICATION_CONTINUATION = PENDING
P1-02 HOSTED_ACCEPTANCE = PENDING
```

Decisão externa ainda pendente: Cloud/IAM confirma ou não a criação da role
isolada e dos dois repositórios lab; Segurança/AppSec confirma que a
identidade de assinatura do laboratório (`partial-retry-lab.yml@refs/heads/main`,
distinta de `build-base-images.yml@refs/heads/main`) não entra em
`policies/release/signing-identities.json`. Sem essas decisões, não há
implementação nem execução desta fase.

## Correção da proposta após revisão independente adversarial — 2026-09-15

A revisão independente adversarial da proposta acima retornou **CHANGES
REQUIRED**. Nenhuma coleta AWS anterior foi refeita ou reescrita — os fatos
observados em
[evidence.md](evidence.md#investigação-sandbox-read-only-para-infraestrutura-de-publicação--2026-09-15)
sobre a role/policy/repos **operacionais** permanecem exatamente como
registrados. O que muda aqui é a proposta/desenho construído sobre esses
fatos, ainda `PROPOSED`, nunca aplicada.

Findings corrigidos:

- **F1 (HIGH)** — os dois repos lab usariam `IMMUTABLE_WITH_EXCLUSION` com
  exclusão para `stable`, igual à produção. Corrigido para `IMMUTABLE` sem
  nenhuma exclusão: o laboratório nunca sobrescreve tag (padrão fixo
  `p1-02-lab-<run_id>-<attempt>`, único por construção), então a exclusão
  não tinha uso legítimo e só adicionava a capacidade de o ECR aceitar uma
  eventual escrita futura em tag `stable` em vez de rejeitá-la por
  imutabilidade.
- **F2 (MEDIUM)** — `image-base-p102-lab-go1-26`/`-dev` ainda casavam com o
  wildcard `arn:aws:ecr:us-east-1:712107929769:repository/image-base-*` da
  role operacional: a role de produção continuaria alcançando os repos do
  laboratório, mesmo com a role lab corretamente isolada no sentido
  contrário. Corrigido para `p102-lab-go1-26`/`p102-lab-go1-26-dev`,
  confirmado (`"p102-lab-go1-26".startswith("image-base-") == False`) por
  teste dedicado, não só inspeção visual.
- **F3 (MEDIUM)** — a trust com `job_workflow_ref` estava descrita como
  variante opcional/futura; a trust primária usava só `sub`/`aud`, que não
  distingue qual workflow do repositório assume a role. Invertido: a trust
  primária agora inclui `job_workflow_ref` (workflow do laboratório) além
  de `sub`/`aud`/`repository`/`repository_id`/`repository_owner_id`/`ref`
  exatos; a variante sem `job_workflow_ref` passa a
  `FALLBACK / COMPATIBILITY OPTION`, não recomendada.
- **F4 (LOW)** — a escolha de Profile A (sem `ensure`/
  `PutImageTagMutability` no `lab-publish`) não explicava por que isso não
  reduz o que R7 exige. Adicionado: R7 protege artifact selecionado,
  publicação por digest, digest preservation/read-back, Cosign, provenance,
  SBOM, isolamento M13 e continuação do retry — não o bookkeeping de
  provisionamento do repositório. Classificação mantida:
  `ACCEPTABLE_LAB_ADAPTER`.
- **F5 (PROCESS)** — ausência de teste estático dedicado para o diretório
  de proposta IAM. Adicionado
  `tests/unit/pipeline/governance/test_p102_lab_iam_proposal.py`, análogo
  em espírito a `test_iam_proposal.py` (que continua exclusivo de
  `factory-permissions`, sem mistura de contratos).

Estado após a correção, ainda inalterado quanto à execução:

```text
PUBLICATION_INFRA_DESIGN = PROPOSED
PUBLICATION_INFRA_APPLIED = NO
AWS_EXECUTION = NOT RUN
PUBLICATION_CONTINUATION = PENDING
P1-02 HOSTED_ACCEPTANCE = PENDING
```

Detalhes completos da arquitetura corrigida:
[policies/aws/proposals/p102-lab-permissions/README.md](../../policies/aws/proposals/p102-lab-permissions/README.md).

## Implementação local do job de publicação — 2026-09-15

Estende `.github/workflows/partial-retry-lab.yml` com o job `lab-publish`,
implementado localmente e verificado; nenhum recurso AWS foi criado,
alterado ou assumido, nenhum workflow foi despachado.

`lab-publish` só executa quando `github.run_attempt == '2' &&
needs.lab-retry.result == 'success'` — não existe caminho de publicação no
attempt 1. Antes de qualquer autenticação AWS, o step "Validate same-run
retry/reuse binding before any AWS auth" chama
`scripts.pipeline.runtime.retry_lab_publish bind`, que:

- reutiliza `retry_lab.context()` e `retry_lab.valid_gate()` sem seletor
  paralelo, vinculando à evidência real que `lab-retry` já produziu no
  mesmo run (`lab-evidence/runtime-gate-result.json`);
- exige `run_attempt == 2`, `selected_attempt == 1` e `reused is True`;
- valida as futuras variáveis `LAB_AWS_REGION`/`LAB_AWS_ROLE_ARN`/
  `LAB_ECR_REPOSITORY_RUNTIME`/`LAB_ECR_REPOSITORY_DEV` contra os
  valores exatos aprovados (712107929769/us-east-1/
  `github-actions-image-base-p102-lab`/`p102-lab-go1-26`/
  `p102-lab-go1-26-dev`), sem fallback para a role operacional;
- computa a tag `p1-02-lab-<run_id>-<attempt>` internamente — o workflow
  não tem nenhum input de tag/destino/framework livre.

Após a autenticação (role isolada, nunca `github-actions-image-base`), um
preflight somente leitura (`DescribeRepositories`) confirma que os dois
repositórios lab existem, têm o nome exato e `imageTagMutability ==
IMMUTABLE` sem `imageTagMutabilityExclusionFilters`; qualquer divergência
aborta sem correção automática (Profile A: nenhum
`CreateRepository`/`PutImageTagMutability` em nenhum ponto do job). A
publicação reutiliza o padrão produtivo (`skopeo copy --all
--preserve-digests`, `cosign sign`, `attest-build-provenance`,
`publish_sboms.py`) e delega a leitura de volta a
`scripts.pipeline.release.verify_publication` diretamente do workflow —
exatamente como o publicador real já faz — em vez de importar esse módulo
dentro de `retry_lab_publish.py`, que pertence ao domínio `runtime` e não
pode depender do domínio `release`
(`tests/unit/pipeline/governance/test_repository_layout.py`). A
autoverificação de assinatura/provenance/SBOM usa comandos próprios
(`cosign verify`, `gh attestation verify`, `cosign verify-attestation`) com
a identidade do próprio laboratório
(`https://github.com/alric-corp/alric-containers-image-base/.github/workflows/partial-retry-lab.yml@refs/heads/main`),
nunca a identidade do produto, e não altera
`policies/release/signing-identities.json`. `finalize` só produz `PASS` se
`validated_digest == copied_digest == remote_digest` para runtime e dev,
mais assinatura/provenance/SBOM verificados com a identidade correta;
qualquer divergência aborta.

O job nunca chama `promote-stable.yml`, `recover-stable.yml`,
`verify_stable.py` nem `docker buildx imagetools create --tag stable` —
confirmado por teste dedicado, não apenas por ausência observada. A
evidência é preservada em
`runtime-lab-p1-02-publication-<run_id>-<attempt>` (retenção 30 dias,
`overwrite: false`, `if-no-files-found: error`).

Testes novos: `tests/unit/pipeline/runtime/test_retry_lab_publish.py` (36
testes cobrindo role/conta/região exatos, rejeição de `image-base-*`/
`stable`/`latest`/tag externa, determinismo da tag, attempt 1 nunca publica,
attempt 2 exige `reused=true`, `selected_attempt` deve ser 1, run/revisão
incompatíveis falham, mismatch runtime/dev falha, assinatura/provenance/SBOM
obrigatórios com a identidade certa, `signing-identities.json` inalterado,
nenhuma chamada de criação/reconfiguração de repositório) e extensões em
`tests/unit/pipeline/runtime/test_retry_lab.py` (job novo no inventário,
permissões mínimas exatas em `lab-publish`, ausência de privilégio de
publicação nos demais jobs, bind antes de qualquer auth AWS, artifact de
publicação sem overwrite, reuso direto de `verify_publication`/
`publish_sboms` em vez de wrapper). `renovate.json` passou a cobrir também
o pin do Skopeo dentro de `partial-retry-lab.yml`
(`test_actual_skopeo_pins_are_both_visible_and_managed` atualizado para 3
ocorrências, todas geridas).

```text
PUBLICATION_JOB_IMPLEMENTATION = IMPLEMENTED
PUBLICATION_JOB_LOCAL_VERIFICATION = PASS
PUBLICATION_INFRA_DESIGN = PROPOSED
PUBLICATION_INFRA_APPLIED = NO
AWS_EXECUTION = NOT RUN
PUBLICATION_CONTINUATION = PENDING
P1-02 HOSTED_ACCEPTANCE = PENDING
```

Pendente: revisão independente desta implementação; decisão externa de
Cloud/IAM sobre a role/repos isolados (nada aplicado); só depois disso uma
execução hospedada real poderia ser autorizada — não ocorreu nesta sessão.

## Correção F1/F2 da revisão adversarial do job de publicação — 2026-09-15

A revisão independente adversarial retornou **CHANGES REQUIRED** com dois
achados concretos e reproduzidos, ambos corrigidos nesta rodada. Nenhum
recurso AWS foi criado/alterado; nenhum workflow foi despachado.

- **F1 (HIGH)** — o OCI que `lab-publish` efetivamente revalida e publica
  nunca era comparado, por digest, ao `index_digest`/`dev_index_digest` que
  o gate de retry/reuse aprovou. Como `validated-oci-<framework>` é
  publicado com `overwrite: true` no reusable
  (`.reusable-workflows/.github/workflows/validate-apko-images.yml`), o
  artifact baixado por `lab-publish` não era garantidamente o mesmo,
  bit a bit, que `lab-retry` gateou. Reproduzido: `finalize()` retornava
  `PASS` com um digest de runtime completamente diferente do aprovado pelo
  gate. Corrigido com uma nova função,
  `retry_lab_publish.require_gate_layout_binding(gate, verified_runtime_digest,
  verified_dev_digest)`, que não importa `scripts.pipeline.release` (domínio
  `runtime` preservado) e exige `verified_runtime_digest == gate.index_digest`
  e `verified_dev_digest == gate.dev_index_digest`, com os dois digests já
  validados em formato canônico. Um novo step, "Validate revalidated OCI
  digests against the retry/reuse gate", roda logo após "Revalidate OCI
  layouts locally before push" e antes de "Configure AWS credentials" — sem
  `continue-on-error`, sem `if`, com os outputs anteriores passados por
  `env:` (não interpolados em `${{ }}` dentro de `run:`, conforme o guard de
  hardening já existente). `finalize()` agora também recebe esse
  `layout-binding.json` e reexige a mesma cadeia
  (`gate_digest == verified_digest == validated_digest == copied_digest ==
  remote_digest`) para runtime e dev antes de declarar `PASS` — a
  invariante não depende só do step bash.
- **F2 (MEDIUM)** — `digest_equal()` comparava só igualdade de string, sem
  validar que os valores eram digests sha256 reais. Reproduzido: três
  cópias da string `"not-a-real-digest"` passavam como iguais. Corrigido
  reutilizando o validador canônico já existente,
  `contract_evidence.digest()` (mesmo usado por `retry_lab.valid_gate`),
  aplicado a cada um dos três valores antes de compará-los.

`final-result.json` passou a registrar também `gate_digest`/
`verified_digest` por imagem (runtime e dev), tornando a comparação
auditável sem depender de reconstruir o raciocínio a partir de
`gate.json`/`layout-binding.json` separados.

Testes novos: `GateLayoutBindingTests` e `DigestFormatTests` em
`test_retry_lab_publish.py` (o cenário de substituição de artifact via
`overwrite: true` é testado explicitamente, tanto no guard pré-AWS quanto
em `finalize`), mais extensões em `FinalizeTests` (publicação
internamente coerente mas divergente do gate; runtime/dev trocados;
`layout_binding` referenciando outro gate). `test_retry_lab.py` ganhou
testes confirmando a posição exata do novo step (por nome de step real,
não só por texto) entre a revalidação OCI e a autenticação AWS, e que ele
usa `env:` em vez de interpolação direta.

```text
PUBLICATION_JOB_IMPLEMENTATION = IMPLEMENTED
PUBLICATION_JOB_LOCAL_VERIFICATION = PASS
PUBLICATION_INFRA_DESIGN = PROPOSED
PUBLICATION_INFRA_APPLIED = NO
AWS_EXECUTION = NOT RUN
PUBLICATION_CONTINUATION = PENDING
P1-02 HOSTED_ACCEPTANCE = PENDING
```

Nenhuma execução real foi feita. Pendente: nova revisão independente desta
correção antes de qualquer integração adicional.
