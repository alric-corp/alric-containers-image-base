# M00 — Registrar a baseline e o escopo de DEV

**Dependências:** Nenhuma.  
**Tipo de trabalho:** Leitura; sem execução de workflows ou mudanças externas.

## Objetivo desta sessão

Descobrir o estado real da revisão em que você vai trabalhar e registrar apenas o necessário para os próximos marcos.

## Consultar somente

- Metadados Git: branch atual, SHA, status e worktrees.
- `PROGRESSO.md` deste pacote.
- Somente o resumo dos PRs ligados à migração, caso ainda exista trabalho não integrado.

Amplie a leitura apenas para a dependência necessária a um achado concreto. Caminhos completos são relativos à raiz do repositório; nomes curtos identificam workflows/scripts já citados no inventário.

## Executar

1. Registre branch e SHA completos. `2801363` é a revisão descrita na análise de origem, não uma exigência de que o repositório permaneça nela.
2. Execute `git status --short`, `git branch --show-current`, `git rev-parse HEAD` e `git worktree list`. Não remova worktrees, não use reset e não faça stash automático.
3. Separe alterações locais suas, de outra sessão e já integradas. Não inferir sessão ativa apenas pela existência de um worktree.
4. Confirme o escopo: `develop` produz DEV; `staging` será HOM e o ambiente final inicial para usuários; `main` está reservada e inativa. DEV e HOM terão `stable` independente. Este pacote ativa DEV, não implementa HOM.
5. Registre o último resultado de CI conhecido, com SHA e run, se disponível. “Código presente”, “testado localmente” e “testado no ARC” são estados diferentes.
6. Atualize `PROGRESSO.md` com baseline, bloqueios conhecidos e próximo marco. Não reexecute build para produzir uma baseline verde artificial.

## Critérios de aceite

- Branch, SHA e estado do working tree registrados.
- Trabalho paralelo identificado sem interferência.
- Escopo DEV e restrições de HOM/PROD explícitos.
- Nenhuma afirmação de prontidão baseada apenas no relatório antigo.

## Quando parar

Há alterações cuja autoria não é conhecida, conflito com outra sessão ou branch/repositório diferentes do esperado. Preserve tudo e peça apenas o esclarecimento necessário.

## Resultado específico

Além do bloco curto de entrega definido em [CONTEXTO.md](CONTEXTO.md), informe:

```text
BASELINE_SHA =
WORKTREE_STATE =
PARALLEL_WORK =
DEV_SCOPE_CONFIRMED =
```

Use valores observados ou `NÃO_VERIFICADO`; não preencha PASS antecipadamente. Atualize somente a linha deste marco e o checkpoint em [PROGRESSO.md](PROGRESSO.md).

## Prompt para a sessão

```text
Leia TODO/marcos-dev/CONTEXTO.md, TODO/marcos-dev/PROGRESSO.md e
TODO/marcos-dev/00-baseline-e-escopo.md.
Execute somente M00. Registre a baseline real e o escopo de DEV. Não altere código,
branches, worktrees, GitHub Settings ou AWS. Atualize somente o registro de
progresso com fatos verificáveis. Não releia a RFC nem o repositório inteiro.
Ao terminar ou bloquear, entregue o resumo curto e atualize PROGRESSO.md.
```

---

**Base documental:** Análise fornecida: visão geral, seções 13, 19 e 21. Ajuste de planejamento: separar estado relatado de estado verificado. Este marco é um roteiro; não comprova que as ações já foram realizadas.
