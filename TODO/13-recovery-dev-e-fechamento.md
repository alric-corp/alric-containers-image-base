# M13 — Validar recovery DEV e fechar o aceite

**Dependências:** Stable DEV comprovado; destino anterior aprovado disponível; controles de recovery revisados.  
**Tipo de trabalho:** Primeiro revisão em leitura; ensaio de escrita somente com aprovação específica.

## Objetivo desta sessão

Preparar uma recuperação verificável sem declarar coordenação de par que o código ainda não implementa.

## Consultar somente

- `.github/workflows/recover-stable.yml`, trust/ref efetivos e lock compartilhado com promoção.
- Verificadores usados pelo recovery, `promotion-quarantine.json` e evidências dos destinos atual/anterior.
- Somente os testes de recovery e de pair/outcome relacionados ao ensaio.

Amplie a leitura apenas para a dependência necessária a um achado concreto. Caminhos completos são relativos à raiz do repositório; nomes curtos identificam workflows/scripts já citados no inventário.

## Executar

1. Faça primeiro uma revisão sem mutação: branch autorizada, conta DEV, role, aprovação operacional, concorrência e origem dos digests. Não depender de um comentário antigo sobre `main` como guard.
2. Confirme se o recovery segue individual por framework. Se seguir, registre que duas execuções separadas não são uma recuperação coordenada de par.
3. Para testar compiled pair, proponha e revise antes o mecanismo necessário de autorização dos dois destinos, writes, read-back e tratamento parcial. Não improvise duas chamadas e rotule o resultado como atômico/pair-aware.
4. Defina com o operador um cenário mínimo e digests já existentes/aprovados. Não reconstruir a release anterior, não publicar uma segunda release só por conveniência sem autorização.
5. Só após aprovação do cenário e dos controles, execute o recovery previsto. Revalide plataformas, assinatura, provenance, scan atual e destino antes da escrita; faça read-back independente depois.
6. Trate a quarentena do digest retirado pelo processo versionado. Não declarar concluído se o próximo ciclo ainda pode repromovê-lo sem que o operador conheça e aceite essa condição.
7. Feche o relatório distinguindo: candidate DEV, stable DEV, FULL, apps, schedules e recovery. HOM continua fora do aceite. Falha simulada em teste não é falha parcial comprovada no ECR real.

## Critérios de aceite

- Recovery de DEV tem controles de origem, destino e autorização explícitos.
- Escopo individual ou coordenado relatado com honestidade.
- Ensaio autorizado, quando realizado, possui read-back, evidência e tratamento de repromoção.
- Aceite final não confunde implementação, smoke, teste local e execução corporativa real.

## Quando parar

Destino não aprovado, guard/coordenação insuficiente ou falta de plano para falha parcial. Entregue o menor trabalho de código necessário e mantenha o ensaio de escrita bloqueado.

## Resultado específico

Além do bloco curto de entrega definido em [CONTEXTO.md](CONTEXTO.md), informe:

```text
RECOVERY_SCOPE_SUPPORTED =
RECOVERY_RUN_RESULT =
QUARANTINE_STATUS =
DEV_ACCEPTANCE_LIMITATIONS =
```

Use valores observados ou `NÃO_VERIFICADO`; não preencha PASS antecipadamente. Atualize somente a linha deste marco e o checkpoint em [PROGRESSO.md](PROGRESSO.md).

## Prompt para a sessão

```text
Leia TODO/marcos-dev/CONTEXTO.md, TODO/marcos-dev/PROGRESSO.md e
TODO/marcos-dev/13-recovery-dev-e-fechamento.md.
Execute somente M13. Primeiro revise os controles reais de recovery DEV. Não execute
mutação sem cenário e digests aprovados. Se compiled pair não for coordenado,
registre o bloqueio e proponha uma correção mínima; não simule prontidão com duas
recuperações independentes.
Ao terminar ou bloquear, entregue o resumo curto e atualize PROGRESSO.md.
```

---

**Base documental:** Análise fornecida: seções 6.2 e 8.2. Ajustes da revisão: guard de branch explícito, limitação do recovery individual e quarentena operacional. Este marco é um roteiro; não comprova que as ações já foram realizadas.
