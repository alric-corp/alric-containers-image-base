# M05 — Revisar o plano de infraestrutura DEV

**Dependências:** M04 e contrato do executor corporativo disponível.  
**Tipo de trabalho:** Plan autorizado; nenhum apply.

## Objetivo desta sessão

Conferir o que o executor pretende criar/alterar em DEV antes de autorizar infraestrutura.

## Consultar somente

- `.github/workflows/infra-registry.yml`, `.iupipes.yml` e `infra/ecr/`.
- `registry.yml` no SHA consumido: contrato de plan/apply, ref, autenticação, backend e permissões GitHub.
- Testes focados de catálogo ECR e do caller de infraestrutura.

Amplie a leitura apenas para a dependência necessária a um achado concreto. Caminhos completos são relativos à raiz do repositório; nomes curtos identificam workflows/scripts já citados no inventário.

## Executar

1. Confirme ambiente DEV, conta, região, diretório e `expected-ref` no contrato real. Não introduza backend/provider/state do LAB no módulo de recursos.
2. Inspecione por que o plan solicita permissões GitHub de escrita. Comentários/checks podem ser parte do executor, mas cada grant precisa de justificativa. “Sem apply” não significa token GitHub somente leitura.
3. Identifique como o executor gerencia state/backend/locking. Não criar bucket alternativo ou executar Terraform fora do contrato corporativo para contorná-lo.
4. Após autorização para plan, execute o caminho existente e preserve sua identidade: source SHA, reusable SHA, run e artefato de plano, quando houver.
5. Revise recursos e políticas esperados: catálogo, mutabilidade com exceção `stable`, criptografia, lifecycle e org-pull. Confira o Organizations ID com dado real, não por semelhança com o LAB.
6. Diferencie bootstrap de ausência de drift. Antes do primeiro apply, um plano com criações aprovadas é esperado; não exigir `No changes`. Se o comando usar `-detailed-exitcode`, classifique pelo contrato efetivamente executado.

## Critérios de aceite

- Plano legível, vinculado à revisão e exclusivamente a DEV.
- Mudanças esperadas enumeradas e prontas para revisão humana.
- Sem destruição, substituição ou destino inesperado não aprovado.
- Nenhum apply executado; plano não confundido com infraestrutura pronta.

## Quando parar

Plano inclui remoção/substituição não autorizada, recurso fora de DEV, state errado ou permissão sem explicação. Não corrigir aplicando.

## Resultado específico

Além do bloco curto de entrega definido em [CONTEXTO.md](CONTEXTO.md), informe:

```text
PLAN_SOURCE_SHA =
PLAN_RUN_OR_ARTIFACT =
PLANNED_CHANGES =
PLAN_READY_FOR_APPROVAL =
```

Use valores observados ou `NÃO_VERIFICADO`; não preencha PASS antecipadamente. Atualize somente a linha deste marco e o checkpoint em [PROGRESSO.md](PROGRESSO.md).

## Prompt para a sessão

```text
Leia TODO/marcos-dev/CONTEXTO.md, TODO/marcos-dev/PROGRESSO.md e
TODO/marcos-dev/05-terraform-plan-dev.md.
Execute somente M05. Revise o plan DEV pelo executor corporativo existente. Não
execute apply nem crie backend. Inspecione apenas o caller, o módulo ECR e o
contrato externo necessário. Entregue as mudanças e a identidade exata do plano para
aprovação.
Ao terminar ou bloquear, entregue o resumo curto e atualize PROGRESSO.md.
```

---

**Base documental:** Análise fornecida: seções 7.1, 8.2 e Gate 2. Contexto de migração: Terraform Model 2 preservado, recursos em `infra/ecr/`. Este marco é um roteiro; não comprova que as ações já foram realizadas.
