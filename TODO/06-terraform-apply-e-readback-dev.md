# M06 — Aplicar e verificar infraestrutura DEV

**Dependências:** M05 aprovado; autorização explícita de escrita para conta/revisão/plano.  
**Tipo de trabalho:** Escrita de infraestrutura exclusivamente pelo executor autorizado.

## Objetivo desta sessão

Provisionar os ECRs de DEV e provar a configuração final, sem abrir promoção.

## Consultar somente

- Identidade e resumo do plano aprovado em M05.
- Trechos de apply/read-back do executor corporativo e testes diretamente relacionados.
- Inventário real de ECR DEV em leitura após a execução.

Amplie a leitura apenas para a dependência necessária a um achado concreto. Caminhos completos são relativos à raiz do repositório; nomes curtos identificam workflows/scripts já citados no inventário.

## Executar

1. Exija autorização contendo conta DEV, região, source SHA e plano/mudanças aceitas. Os números devem vir do M05, nunca de valores copiados do LAB.
2. Confirme que a revisão a aplicar ainda é a aprovada. Se o executor gerar um novo plano, compare e submeta divergências antes de aplicar.
3. Use somente o mecanismo corporativo já previsto. Não faça um commit fictício apenas para disparar push, não use apply local alternativo e não contorne branch protection.
4. Execute uma única aplicação autorizada. Não realizar retry destrutivo automático em caso de erro ou timeout.
5. Faça read-back dos 16 repositórios esperados e das propriedades relevantes. Registre diferenças entre planejado e observado, não apenas o resultado agregado do workflow.
6. Rode o plan pós-apply pelo contrato disponível para comprovar ausência de mudanças pendentes. Só agora `No changes` é o resultado esperado do bootstrap concluído.
7. Confirme `STABLE_PROMOTION_AUTHORIZED=false`. Infra pronta não é release aprovada. Não disparar build nem promoção neste marco.

## Critérios de aceite

- Apply autorizado concluído e vinculado ao plano/revisão.
- ECRs e políticas DEV confirmados por leitura independente.
- Pós-apply sem alterações pendentes no escopo verificado.
- HOM/PROD e autorização de promoção não alterados.

## Quando parar

Falta de aprovação, revisão/plano divergente ou read-back incompatível. Preserve evidência de aplicação parcial e solicite decisão antes de qualquer correção.

## Resultado específico

Além do bloco curto de entrega definido em [CONTEXTO.md](CONTEXTO.md), informe:

```text
APPLY_RUN_ID =
ECR_CATALOG_READBACK =
POST_APPLY_PLAN =
STABLE_PROMOTION_AUTHORIZED =
```

Use valores observados ou `NÃO_VERIFICADO`; não preencha PASS antecipadamente. Atualize somente a linha deste marco e o checkpoint em [PROGRESSO.md](PROGRESSO.md).

## Prompt para a sessão

```text
Leia TODO/marcos-dev/CONTEXTO.md, TODO/marcos-dev/PROGRESSO.md e
TODO/marcos-dev/06-terraform-apply-e-readback-dev.md.
Execute somente M06. Primeiro confira o plano aprovado e a autorização explícita do
M06. Sem autorização, entregue somente o comando/caminho e pare. Com autorização,
aplique uma vez pelo executor corporativo, faça read-back e mantenha promoção
fechada.
Ao terminar ou bloquear, entregue o resumo curto e atualize PROGRESSO.md.
```

---

**Base documental:** Análise fornecida: Gate 2. Ajuste da revisão: kill switch permanece false após apply; bootstrap precede a publicação. Este marco é um roteiro; não comprova que as ações já foram realizadas.
