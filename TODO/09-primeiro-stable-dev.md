# M09 — Promover e verificar o primeiro stable DEV

**Dependências:** M08 concluído; soak real cumprido; autorização explícita dos digests a promover.  
**Tipo de trabalho:** Mutação controlada de stable DEV; sem rebuild.

## Objetivo desta sessão

Provar a promoção do par aprovado usando o fluxo real, sem confundir autorização de execução com seleção do artefato.

## Consultar somente

- `promote-stable.yml`, seleção relevante de `promotion_batch.py`/`find_promotion_candidate.py` e verificadores do par/read-back.
- Inventário do candidate M08, quarentena e estado de execuções de promoção/recovery.
- Somente o mecanismo atual de autorização/concorrência do ambiente DEV.

Amplie a leitura apenas para a dependência necessária a um achado concreto. Caminhos completos são relativos à raiz do repositório; nomes curtos identificam workflows/scripts já citados no inventário.

## Executar

1. Confirme os dois digests aprovados, existência, quarentena e configuração de `stable`. Calcule elegibilidade pelos timestamps ECR de cada membro e pela política vigente, relatada como mínimo de 6h. Não usar timestamp da tag nem zerar o soak.
2. Execute a seleção real em leitura. Uma seleção antecipada não garante a mesma seleção após esperar na fila. Se existirem candidates concorrentes ou a implementação não puder assegurar o par autorizado antes da escrita, pare e proponha o menor controle revisado; não confie em uma janela calculada a partir do último push do catálogo inteiro.
3. Defina um único operador, inventarie execuções pendentes e planeje a interação com o cron. O lock serializa operações, mas não impede uma segunda promoção autorizada depois. Não tratar “fora do minuto 17” como garantia de exclusividade.
4. Só após aprovação do par e do procedimento, autorize uma promoção. Não crie bypass de scan, assinatura, provenance, pair binding ou barreira pré-write.
5. Monitore sem cancelamento automático. Confira a seleção real, todas as verificações, ambas as escritas e read-backs. Duas writes ECR não são transação atômica; falha parcial deve permanecer explícita.
6. Feche a autorização conforme o procedimento aprovado e confirme o estado final. Não assumir reavaliação de jobs já admitidos ao mudar a variável.
7. Faça leitura independente de `:stable` para runtime/dev e verifique os digests aprovados. Pull comprova distribuição; execução funcional é uma evidência distinta.

## Critérios de aceite

- Par aprovado é exatamente o par observado em stable.
- Segurança, soak, pré-write e read-back foram executados, não pulados.
- Estado final do controle de promoção confirmado.
- Nenhum rebuild nem mutação de outros ambientes.

## Quando parar

Seleção ambígua, concorrência sem controle, soak incompleto ou falha parcial. Não repetir dispatch nem consertar stable manualmente. Ausência de execução não deve ser relatada como defeito da imagem.

## Resultado específico

Além do bloco curto de entrega definido em [CONTEXTO.md](CONTEXTO.md), informe:

```text
PROMOTION_RUN_ID_ATTEMPT =
APPROVED_PAIR_VS_OBSERVED =
STABLE_READBACK =
PROMOTION_CONTROL_FINAL_STATE =
```

Use valores observados ou `NÃO_VERIFICADO`; não preencha PASS antecipadamente. Atualize somente a linha deste marco e o checkpoint em [PROGRESSO.md](PROGRESSO.md).

## Prompt para a sessão

```text
Leia TODO/marcos-dev/CONTEXTO.md, TODO/marcos-dev/PROGRESSO.md e
TODO/marcos-dev/09-primeiro-stable-dev.md.
Execute somente M09. Verifique prontidão do primeiro stable DEV e apresente os
digests exatos e o procedimento de execução. Sem aprovação específica, não abra o
kill switch. Não use uma seleção em leitura como garantia contra mudança futura do
candidato durante a fila.
Ao terminar ou bloquear, entregue o resumo curto e atualize PROGRESSO.md.
```

---

**Base documental:** Análise fornecida: seção 6.1. Ajustes da revisão: promoção só depois do candidate aprovado; seleção temporal e kill switch não são autorização por digest. Este marco é um roteiro; não comprova que as ações já foram realizadas.
