# M11 — Certificar o catálogo completo em DEV

**Dependências:** Caminho DEV candidato comprovado em M08; primeira promoção M09 e capacidade/custo revisados antes de ampliar escrita.  
**Tipo de trabalho:** Um dispatch FULL autorizado; publica candidates, não stable.

## Objetivo desta sessão

Exercitar todos os artefatos pelo mesmo engine sem transformar o schedule normal em FULL por acidente.

## Consultar somente

- `.github/workflows/catalog-certification.yml`, lote fixo e chamada ao build engine.
- Catálogo `frameworks/*.yaml`, planners de contrato/promoção e limites de matrix.
- Evidências do novo run FULL, não os resultados históricos do LAB como substitutos.

Amplie a leitura apenas para a dependência necessária a um achado concreto. Caminhos completos são relativos à raiz do repositório; nomes curtos identificam workflows/scripts já citados no inventário.

## Executar

1. Confira lote exato e mapeamento: .NET10, Go1.25/1.26 e Java21/25 com seus cinco pares; Node22/24 com runtime/dev independentes na promoção; Python3.13/3.14 sem companion. Esperado na baseline: 16 artefatos, 11 unidades.
2. Revise capacidade por job e paralelismo. Compartilhar o lock de publicação impede publicação simultânea no domínio previsto, mas não dimensiona CPU/memória de todas as legs.
3. Informe que o dispatch escreve candidates reais no ECR. Após autorização, execute uma vez usando o engine existente, sem rebuild independente de conferência.
4. Confira build, plataformas, scan, trust, contratos, publicação, assinatura, SPDX, provenance e consumo por digest para cada artefato. Registre falhas e resultados parciais com escopo correto.
5. Gere inventário completo com run/attempt/source SHA, tags, digests e timestamps. Não exigir exatamente 16 objetos em `describe-images`: manifests e evidências também podem estar no registry.
6. Deixe stable e o escopo diário inalterados. O soak pode transcorrer enquanto M12 testa apps; não há necessidade de esperar stable para executar M12.
7. Promoção FULL e expansão do schedule exigem decisão posterior. Um FULL candidato aprovado não comprova, sozinho, stable/recovery de todos os frameworks.

## Critérios de aceite

- Cobertura real 16/16 de artefatos e 11/11 de contratos/unidades aplicáveis, ou parcialidade explícita.
- Inventário fechado por run/attempt/revisão, sem seleção de “mais recente”.
- Stable e schedules não alterados por este marco.
- Evidência suficiente para alimentar M12.

## Quando parar

Lote diferente, scan/trust/contrato inválido, falta de evidência ou mutação inesperada. Não repetir o FULL inteiro automaticamente para corrigir uma leg.

## Resultado específico

Além do bloco curto de entrega definido em [CONTEXTO.md](CONTEXTO.md), informe:

```text
FULL_RUN_ID_ATTEMPT =
ARTIFACTS_PUBLISHED_AND_VERIFIED =
UNITS_VERIFIED =
CANDIDATE_INVENTORY_LOCATION =
```

Use valores observados ou `NÃO_VERIFICADO`; não preencha PASS antecipadamente. Atualize somente a linha deste marco e o checkpoint em [PROGRESSO.md](PROGRESSO.md).

## Prompt para a sessão

```text
Leia TODO/marcos-dev/CONTEXTO.md, TODO/marcos-dev/PROGRESSO.md e
TODO/marcos-dev/11-certificacao-full-do-catalogo.md.
Execute somente M11. Prepare uma certificação FULL corporativa pelo workflow
existente, com custo e escopo explícitos. Só faça o único dispatch após autorização.
Entregue o inventário dos candidates para App Certification; não promova stable nem
altere o schedule.
Ao terminar ou bloquear, entregue o resumo curto e atualize PROGRESSO.md.
```

---

**Base documental:** Análise fornecida: seção 7.2 e escopo V1. Contexto da referência: 16 artefatos e 11 unidades; contagens devem ser confrontadas com o catálogo corporativo. Este marco é um roteiro; não comprova que as ações já foram realizadas.
