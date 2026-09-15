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
