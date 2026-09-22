# M01 — Fechar Settings, variáveis e aprovações do GitHub

**Dependências:** M00.  
**Tipo de trabalho:** Inventário em leitura; Settings só mediante autorização específica.

## Objetivo desta sessão

Definir onde cada configuração é lida e quais proteções precisam existir antes de uma execução privilegiada.

## Consultar somente

- `.github/workflows/workflow.yml`, `build-base-images.yml`, `promote-stable.yml`, `infra-registry.yml` e `app-certification.yml`: somente `if`, `with`, `vars`, `secrets`, `permissions` e `environment`.
- `.github/CODEOWNERS` e a seção de owners de `policies/operations/health.json`.
- Settings do repositório/organização em leitura, por acesso autorizado.

Amplie a leitura apenas para a dependência necessária a um achado concreto. Caminhos completos são relativos à raiz do repositório; nomes curtos identificam workflows/scripts já citados no inventário.

## Executar

1. Confirme a default branch nas Settings ou API do GitHub. `origin/HEAD` local não substitui essa evidência.
2. Monte uma tabela pequena: `configuração | consumidor | escopo necessário | presente? | responsável`. Inclua as quatro `RUNNER_EKS_OD_*`, região, role, conta esperada e `STABLE_PROMOTION_AUTHORIZED`.
3. Identifique onde cada expressão é avaliada. Não concentre automaticamente todas as variáveis no Environment `dev` se elas forem necessárias para resolver o caller ou agendar o job.
4. Confira quais jobs realmente declaram `environment: dev`, inclusive no reusable. Criar o Environment ou usar `secrets: inherit` não prova o vínculo. Não preencha valores duplicados para esconder uma dependência mal definida.
5. Confirme CODEOWNERS corporativo válido, acesso do time, proteções e checks exigidos. Não trate esses controles como mera limpeza posterior à ativação.
6. Registre o estado do kill switch. A condição desejada para o bootstrap é `false`. Liste schedules/jobs caros que podem disparar antes da prontidão; proponha uma contenção operacional explícita, sem alterar filtros nem desligar CI por conta própria.

## Critérios de aceite

- Default branch corporativa confirmada.
- Matriz de variáveis sem valores inventados e com escopo de consumo identificado.
- Aprovações/Settings faltantes têm responsável definido.
- Promoção não foi autorizada apenas porque a infraestrutura será criada.

## Quando parar

Settings inacessíveis, variável obrigatória ausente ou política de aprovação indefinida: registre o item como bloqueado. Não adicione PAT nem permissões de escrita para contornar a limitação.

## Resultado específico

Além do bloco curto de entrega definido em [CONTEXTO.md](CONTEXTO.md), informe:

```text
DEFAULT_BRANCH_VERIFIED =
VARIABLE_BINDING =
BRANCH_PROTECTION_VERIFIED =
PROMOTION_CONTROL_STATE =
```

Use valores observados ou `NÃO_VERIFICADO`; não preencha PASS antecipadamente. Atualize somente a linha deste marco e o checkpoint em [PROGRESSO.md](PROGRESSO.md).

## Prompt para a sessão

```text
Leia TODO/marcos-dev/CONTEXTO.md, TODO/marcos-dev/PROGRESSO.md e
TODO/marcos-dev/01-github-settings-e-variaveis.md.
Execute somente M01. Faça somente o inventário de Settings, variáveis e proteções de
DEV. Mostre onde cada variável é consumida e o que falta configurar. Não mude
Settings, não crie secrets e não habilite promoção. Não implemente HOM.
Ao terminar ou bloquear, entregue o resumo curto e atualize PROGRESSO.md.
```

---

**Base documental:** Análise fornecida: seções 6.1, 13, 17 e Gate 0. Ajustes da revisão: variáveis por escopo, Environment não implícito e promoção inicialmente fechada. Este marco é um roteiro; não comprova que as ações já foram realizadas.
