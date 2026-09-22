# Progresso — ativação DEV

Este arquivo é o checkpoint para troca de sessão. A baseline de origem relata implementação, mas os marcos abaixo **não foram executados por este pacote**. Marque conclusão apenas com evidência da revisão/ambiente corretos.

## Baseline da execução

```text
REPOSITORIO = itau-corp/itau-xj7-container-image-base
BRANCH_ATUAL = NÃO_VERIFICADO
BASELINE_SHA_COMPLETO = NÃO_VERIFICADO
REUSABLE_SHA_COMPLETO = NÃO_VERIFICADO
AWS_CONTA_DEV_CONFIRMADA = NÃO_VERIFICADO
AWS_REGIAO_DEV_CONFIRMADA = NÃO_VERIFICADO
ULTIMO_MARCO_TRABALHADO = NENHUM
PROXIMO_MARCO = M00
PROMOCAO_AUTORIZADA = NÃO_VERIFICADO
```

Não registre secrets. IDs/contas só devem permanecer aqui se permitido pela política do repositório.

## Marcos

| Marco | Escopo | Estado | Evidência / SHA / run |
|---|---|---|---|
| M00 | [Registrar a baseline e o escopo de DEV](00-baseline-e-escopo.md) | NÃO_VERIFICADO | — |
| M01 | [Fechar Settings, variáveis e aprovações do GitHub](01-github-settings-e-variaveis.md) | NÃO_VERIFICADO | — |
| M02 | [Provar checkout e acesso ao reusable no ARC](02-arc-checkout-e-reusable.md) | NÃO_VERIFICADO | — |
| M03 | [Provar capacidades de build e rede do ARC](03-arc-ferramentas-arquiteturas-e-rede.md) | NÃO_VERIFICADO | — |
| M04 | [Vincular identidades, IAM e OIDC ao DEV real](04-identidades-iam-e-oidc-dev.md) | NÃO_VERIFICADO | — |
| M05 | [Revisar o plano de infraestrutura DEV](05-terraform-plan-dev.md) | NÃO_VERIFICADO | — |
| M06 | [Aplicar e verificar infraestrutura DEV](06-terraform-apply-e-readback-dev.md) | NÃO_VERIFICADO | — |
| M07 | [Fechar certificados e confiança corporativa](07-certificados-e-trust-corporativo.md) | NÃO_VERIFICADO | — |
| M08 | [Publicar o primeiro candidate Go em DEV](08-candidate-go-dev.md) | NÃO_VERIFICADO | — |
| M09 | [Promover e verificar o primeiro stable DEV](09-primeiro-stable-dev.md) | NÃO_VERIFICADO | — |
| M10 | [Ativar e observar a operação agendada](10-schedules-e-saude-operacional.md) | NÃO_VERIFICADO | — |
| M11 | [Certificar o catálogo completo em DEV](11-certificacao-full-do-catalogo.md) | NÃO_VERIFICADO | — |
| M12 | [Executar aplicações consumidoras nas duas arquiteturas](12-apps-consumidoras-multiarch.md) | NÃO_VERIFICADO | — |
| M13 | [Validar recovery DEV e fechar o aceite](13-recovery-dev-e-fechamento.md) | NÃO_VERIFICADO | — |

Estados: `NÃO_VERIFICADO`, `EM_ANDAMENTO`, `PARCIAL`, `BLOQUEADO`, `CONCLUIDO`.

## Checkpoint da última sessão

Substitua o bloco abaixo; não acumule uma transcrição de cada conversa.

```text
DATA_UTC =
MARCO =
O_QUE_FOI_CONFIRMADO =
O_QUE_MUDOU =
O_QUE_NAO_FOI_EXECUTADO =
BLOQUEIO_EXATO =
INPUT_OU_APROVACAO_NECESSARIA =
PROXIMA_ACAO_UNICA =
```

## Bloqueios ativos

Preencha somente os bloqueios atuais, com responsável e critério de liberação. Não marque `EXTERNAL_INPUT_REQUIRED` para algo que já pode ser consultado com o acesso autorizado disponível.

| Item | Informação/ação faltante | Responsável | Como comprovar liberação |
|---|---|---|---|
| A preencher após M00 | — | — | — |

## Índice de evidências

Guarde aqui apenas referências curtas para planos aprovados, inventários de digests, runs e relatórios necessários aos próximos marcos. Evidência sensível permanece no armazenamento corporativo autorizado.
