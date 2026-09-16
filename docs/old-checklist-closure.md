# Reconciliação dos checklists antigos — 09/09/2026

A revisão partiu da `main` em `7b2a81a`, após M13. Os itens históricos de
08/09 que aguardavam publicação OCI e promoção já tinham sido atendidos pelas
entregas seguintes; as caixas agora apontam para essas evidências. Os testes que
ainda faltavam foram executados nesta rodada, conforme a tabela.

| Item | Evidência e resultado |
| --- | --- |
| Seleção com ECR real | Snapshot de 102 entradas de `image-base-go1-26`: um digest `stable`, 82 entradas auxiliares/sem tag de build e quatro builds não estáveis ainda dentro de seis horas. Com soak 6, nenhum candidato; com soak 0, selecionado o build mais recente elegível. |
| Publicação OCI e promoção positiva antigas | [Publicação 34371208971](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34371208971) e [promoção 34372447340](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34372447340), já registradas nas entregas anteriores. O digest promovido foi `sha256:53f9a106b88e00773513d6cd3e2a62a3adaadef3e9f21d3720993793af2dd63e`. |
| R03 — reexecução completa | [Run 34402226000](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34402226000), tentativas 1 e 2: melange, build OCI, scans, publicação, assinatura e provenance concluídos. A tentativa 2 substituiu os artifacts reutilizáveis e publicou a tag `a2` sem colisão. |
| R03 — retry parcial | Tentativa 3 do mesmo run: publicador executado novamente; o GitHub exibiu os jobs de validação com novos IDs, mas manteve seus horários e steps da tentativa 2. Publicação 2 e 3 têm exatamente os mesmos digests de índice/manifests. Não houve novo build. |
| M03 — negativo autenticado | [Run 34402648331](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34402648331): OIDC e ECR login aprovados, seleção aprovada, cosign rejeitou o candidato com `no signatures found`, saída 10. Scan e promoção ficaram `skipped`. |
| M04 — cron real | Execuções `schedule` de build diário e promoção horária identificadas; horários medidos abaixo. O evento real foi observado, incluindo falhas visíveis, sem presumir cadência ou pontualidade garantidas. |
| M05 — PR de fork | [PR #33](https://github.com/alric-corp/alric-containers-image-base/pull/33), [run 34402787717](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34402787717): head no fork `TomasAlric/alric-containers-image-base`, SHA `819130a`. Token somente `Contents: read`/`Metadata: read`, `Secret source: None`; nenhuma etapa AWS, publicação e promoção puladas. 14 frameworks passaram; dotnet8 falhou no scan. Fast checks passaram. PR fechado sem merge. |
| M06 — último ECR mutável | `image-base-dotnet8` recebeu `IMMUTABLE_WITH_EXCLUSION`, com único filtro `stable`. Leitura de volta confirmou os 15 repositórios do catálogo com essa configuração. A mudança não publica imagens nem resolve/excepciona a CVE de dotnet8. |
| M14 — timeout real | [PR #34](https://github.com/alric-corp/alric-containers-image-base/pull/34), [run 34403555339](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34403555339): espera de 180s em job com limite de 1 minuto. Anotação do GitHub: `The job has exceeded the maximum execution time of 1m0s`. PR fechado sem merge. |

## Identidade, isolamento e limites dos testes

O negativo M03 executou **o próprio `promote-stable.yml` da main**, autenticado
pela role existente, contra `image-base-validation-nodejs24`. O workflow nessa
versão ainda aceita esse nome de teste; um futuro guard de catálogo M16 pode
exigir um caminho de teste isolado explícito. Não se deve remover o guard para
repetir o exercício.

Foi adicionada somente uma tag temporária, no formato aceito pelo seletor, ao
índice não assinado já existente
`sha256:b9074171f0fb0d2ff2d401beda4dcf41f58ebfe378fc23ada3b8d9ae3552c759`.
O `stable` do ECR isolado permaneceu em
`sha256:49d0c59ce62eae51bf5f507920d45fea626145e64fa8c3186afe62626e8d90ed`,
confirmado antes e depois por leitura AWS independente. A tag temporária foi
removida; o índice e sua referência original `review-pr1-ci-oci` foram preservados.
Nenhum `stable` de consumo foi movido nesta rodada. A fonte de assinatura esperada
e a trust policy não foram alteradas.

No R03, as tentativas completas produziram digests diferentes, o que é permitido:
`a1` apontou para `sha256:6ac3f4697aa928dd809875f430830da95ed9383e5d40cec8741a6d0cf5e9de57`
e `a2` para `sha256:b2e2422f6dd093a056e272a76dc21305f0d21c1862f8ca265e57fa5ce3203240`.
O retry **parcial** `a3` preservou o digest de `a2`, incluindo os dois manifests.
Os JSONs de publicação 2/3 foram baixados e comparados; os bytes dos índices
publicados também foram hasheados. Na consulta posterior ao rerun completo, o
inventário da API não listava mais `publication-go1-26-1`; a conclusão da primeira
tentativa está nos jobs/logs e sua tag está no snapshot ECR. Isso deve entrar na
política de preservação M11/M15: `retention-days` sozinho não é backup independente
de uma execução que será reexecutada.

No timeout, a API classificou job e run como **`cancelled`**, não `timed_out`.
A causa está comprovada pela anotação específica de limite excedido. Entre início
e conclusão do job decorreram 91s, incluindo preparação e encerramento; o timeout
de 1 minuto não implica término instantâneo no segundo 60. O limite reduzido foi
usado somente na branch descartável; os limites de produção permanecem os mesmos.

## Agendamento observado

| Run | Cron no commit executado | Slot anterior mais próximo (UTC) | Criação do run (UTC) | Diferença mínima slot→criação | Criação→primeiro job ativo |
| --- | --- | --- | --- | --- | --- |
| [34324698241](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34324698241) | `0 3 * * *` | 09/09 03:00:00 | 09/09 07:36:28 | 4h36m28s | 3s |
| [34390576742](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34390576742) | `17 * * * *` | 09/09 18:17:00 | 09/09 18:41:43 | 24m43s | 3s |

O campo `event=schedule`, os workflows nos respectivos commits e o roteamento dos
jobs distinguem build e promoção. A API consultada não fornece o instante nominal
original de enfileiramento: o slot mais próximo produz um **limite inferior**, não
uma medição exata da espera do scheduler, principalmente no cron horário. Os 3s
também não são atribuídos exclusivamente à fila de runner.

O cron horário falhou em `List images in repository` para `go1-26-dev`,
`dotnet10-dev` e `java21-dev`: seus ECRs ainda não existiam naquele momento
(`RepositoryNotFoundException` confirmado no log de java21-dev). Esses repositórios
já existem na leitura atual após as publicações posteriores. O sucesso de outros
jobs não foi usado para esconder as três falhas. M11 continua responsável por
monitoramento contínuo, lacunas de execução, SLA e alertas; uma amostra não prova
regularidade do agendamento.

## Evidências preservadas e trabalho restante

[Resultados e metadados](evidence/old-checklist-2026-09-09.json) e
[entrada ECR do seletor](evidence/ecr-selector-2026-09-09.json) permitem auditar
digests, horários, permissões e resultados sem depender somente das caixas da RFC.
O snapshot do seletor deve ser reproduzido usando `observed_at` da evidência como
`now` em `select_candidate`; usar a hora atual altera legitimamente a elegibilidade.

M07 ainda precisa separar go1-25/dotnet8/java25 e comprovar as promoções das novas
variantes. A publicação autenticada das seis variantes já existentes ocorreu no
[run 34398032502](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34398032502),
portanto a antiga frase “depende do merge na main” deixou de ser atual para a
publicação. M08/M10 têm a entrega parcial no PR #32; M09/M16 seguem no PR #28.
Esses itens, M11 e M15 não foram marcados como completos por esta reconciliação.
