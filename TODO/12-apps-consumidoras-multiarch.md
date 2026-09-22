# M12 — Executar aplicações consumidoras nas duas arquiteturas

**Dependências:** M11 com inventário FULL completo; autenticação de leitura e recursos ARC prontos.  
**Tipo de trabalho:** Um dispatch de testes de apps; AWS/ECR somente leitura, imagens derivadas locais.

## Objetivo desta sessão

Provar consumo real das imagens publicadas, antes ou depois de stable, sem criar novos candidates.

## Consultar somente

- `.github/workflows/app-certification.yml` e seu contrato `source-run-id`.
- Resolver/planner em `scripts/pipeline/consumer_apps/`, apenas o necessário para verificar inventário e matriz.
- Evidências e resumo de cada execução; fixtures de `tests/consumer-apps/` apenas se houver falha específica.

Amplie a leitura apenas para a dependência necessária a um achado concreto. Caminhos completos são relativos à raiz do repositório; nomes curtos identificam workflows/scripts já citados no inventário.

## Executar

1. Use o run corporativo FULL do M11, não o run do LAB e não um run que publicou só Go. Exija vínculo ao attempt/revisão e referências ECR por digest.
2. Confira sessão efetivamente limitada a leitura no mecanismo implementado; não confundir “nenhum comando de escrita encontrado” com impossibilidade IAM de escrever.
3. Após autorização, execute uma vez. A matriz esperada é .NET10; Go1.25/1.26; Java21/25; Node22/24; Python3.13/3.14, em amd64 e arm64: 9 × 2 = 18.
4. Confira uso de sete imagens dev nos estágios de build, incluindo as duas Node. São cinco pares compilados e dois cenários Node; não chamar os sete de compilados.
5. Verifique build/preparação real, runtime final correto, HTTP `/health`, `/ready`, `/info`, versão, arquitetura, UID/GID, raiz somente leitura, áreas graváveis permitidas, capabilities, no-new-privileges e shutdown conforme o contrato implementado.
6. Registre nativo versus emulado. Existência de manifest arm64 não substitui container arm64 executado.
7. Exija 18 resultados novos vinculados ao source run. Não reutilize relatórios antigos para preencher legs ausentes e não push as aplicações derivadas.
8. Informe que esta certificação permanece separada da promoção se o YAML não a conecta como gate. Integrá-la automaticamente é outra mudança, não parte deste teste.

## Critérios de aceite

- 18/18 execuções consumidoras aprovadas, ou falhas identificadas individualmente.
- 16/16 bases exercitadas pelo uso correto dos estágios de build/runtime.
- Digests do inventário FULL preservados e nenhuma dependência de `stable`.
- Nenhuma escrita no ECR, promoção, recovery ou novo candidate.

## Quando parar

Inventário incompleto, digest divergente ou falha de app/arquitetura. Preserve as demais evidências e classifique BASE_IMAGE, FIXTURE, RUNNER, EMULATION, NETWORK ou HARNESS sem mascarar a causa.

## Resultado específico

Além do bloco curto de entrega definido em [CONTEXTO.md](CONTEXTO.md), informe:

```text
APP_RUN_ID_ATTEMPT =
SOURCE_FULL_RUN =
PLATFORM_EXECUTIONS_PASSED =
BASE_ARTIFACTS_EXERCISED =
```

Use valores observados ou `NÃO_VERIFICADO`; não preencha PASS antecipadamente. Atualize somente a linha deste marco e o checkpoint em [PROGRESSO.md](PROGRESSO.md).

## Prompt para a sessão

```text
Leia TODO/marcos-dev/CONTEXTO.md, TODO/marcos-dev/PROGRESSO.md e
TODO/marcos-dev/12-apps-consumidoras-multiarch.md.
Execute somente M12. Execute somente a certificação de apps autorizada sobre o run
FULL corporativo registrado. Não use stable nem latest. Exija as 18 execuções reais
e preserve a distinção entre cinco pares compilados, dois cenários Node e dois
Python.
Ao terminar ou bloquear, entregue o resumo curto e atualize PROGRESSO.md.
```

---

**Base documental:** Análise fornecida: seção 7.3 e `app-certification.yml`. Contexto aprovado: nove cenários de app e dezoito execuções cobrindo dezesseis bases. Este marco é um roteiro; não comprova que as ações já foram realizadas.
