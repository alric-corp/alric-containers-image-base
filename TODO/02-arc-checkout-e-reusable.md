# M02 — Provar checkout e acesso ao reusable no ARC

**Dependências:** M01; variáveis de runner configuradas para o job escolhido.  
**Tipo de trabalho:** Smoke hospedado pequeno; um dispatch ou rerun somente após autorização.

## Objetivo desta sessão

Comprovar o caminho GitHub → runner corporativo → repositório privado → reusable, antes de gastar recursos com imagens.

## Consultar somente

- `.github/workflows/ci.yml` e a definição do job leve escolhido.
- `policies/governance/reusable-workflows.json` e os dois callers de validação/runtime.
- Apenas os logs de setup e checkout do run em análise.

Amplie a leitura apenas para a dependência necessária a um achado concreto. Caminhos completos são relativos à raiz do repositório; nomes curtos identificam workflows/scripts já citados no inventário.

## Executar

1. Confirme `runs-on` usando a variável corporativa correta e o runner efetivamente alocado. Não usar fallback para `ubuntu-latest`.
2. Confira `contents: read` efetivo, eventual sobrescrita de permissões e configuração do checkout. Não remover `persist-credentials: false` só para tentar corrigir acesso.
3. Verifique se a variável de runner está disponível no repositório caller. O reusable também precisa usar jobs com seleção corporativa adequada.
4. Prefira um caminho leve existente. Caso precise de um smoke novo, proponha o menor diff e explique os triggers antes de criar PR. Não disparar o motor da Factory apenas para testar checkout.
5. Após autorização, execute uma única tentativa leve. Registre runner, job, SHA e resultado de checkout. Confira a resolução do reusable privado pelo SHA consumido; não execute build completo para provar apenas a chamada.
6. Classifique separadamente: job não agendado, acesso GitHub negado, Git transport, ação não permitida ou chamada privada indisponível. Um HTTP 403 não identifica sozinho todas essas causas.

## Critérios de aceite

- Runner corporativo efetivamente iniciou o job.
- Checkout do repositório terminou sem 403.
- Caminho de consumo privado do reusable e SHA foram verificados no nível exercitado.
- Nenhuma imagem construída/publicada e nenhuma configuração AWS modificada.

## Quando parar

Se houver 403, registre a camada e o log mínimo. Não enfraqueça allow list, não troque para SSH/PAT e não tente outra forma de comando para escapar de uma negativa de ferramenta.

## Resultado específico

Além do bloco curto de entrega definido em [CONTEXTO.md](CONTEXTO.md), informe:

```text
ARC_RUNNER_USED =
CHECKOUT_RESULT =
REUSABLE_ACCESS_RESULT =
SMOKE_RUN_ID =
```

Use valores observados ou `NÃO_VERIFICADO`; não preencha PASS antecipadamente. Atualize somente a linha deste marco e o checkpoint em [PROGRESSO.md](PROGRESSO.md).

## Prompt para a sessão

```text
Leia TODO/marcos-dev/CONTEXTO.md, TODO/marcos-dev/PROGRESSO.md e
TODO/marcos-dev/02-arc-checkout-e-reusable.md.
Execute somente M02. Prepare o smoke mínimo de checkout/acesso ao reusable no ARC.
Não execute build. Se já houver evidência válida na revisão atual, reutilize-a. Caso
precise de run novo, apresente o comando e o custo/escopo antes de pedir uma
autorização única.
Ao terminar ou bloquear, entregue o resumo curto e atualize PROGRESSO.md.
```

---

**Base documental:** Análise fornecida: seções 4, 5.2 e 8.2; informação do usuário de que runners públicos não atendem à allow list corporativa. Este marco é um roteiro; não comprova que as ações já foram realizadas.
