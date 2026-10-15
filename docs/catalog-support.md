# Suporte das variantes do catálogo

Estar no catálogo significa que a Factory sabe construir e validar a variante.
Não significa que a série da linguagem ainda recebe correções. Este documento
separa as duas coisas para cada uma das 16 definições de `frameworks/`.

O registro versionado é
[`policies/governance/catalog-support.json`](../policies/governance/catalog-support.json):
status, pacote Wolfi que define a série, fonte upstream, evidência datada,
decisão pendente e alvo de migração. O owner é Containers Products; a revisão
seguinte vence na data `review_by` do arquivo. Um teste de consistência
confere que todas as definições têm status, que o pacote declarado é o que a
definição instala e que runtime e `-dev` de um par têm o mesmo status.

O registro não habilita nem bloqueia build, publicação ou promoção. Um scan
Trivy sem achados também não prova suporte: o scanner só conhece correções que
o distribuidor publicou.

## Status

| Status | Significado |
| --- | --- |
| SUPPORTED | O upstream mantém a série, segundo a fonte primária, e o pacote Wolfi recebeu atualização recente na data da revisão. |
| UPSTREAM_EOL | O upstream encerrou a manutenção da série. A variante continua no catálogo até a decisão do owner. |

Todos os pacotes vêm do repositório Wolfi, que é rolling-release: cada build
resolve a versão disponível naquele momento e registra o resultado no lock do
artifact. O Wolfi não publica uma política formal de suporte por série; a
evidência abaixo é a observação do índice de pacotes na data da revisão.

## Variantes (revisão de 2026-10-13)

| Variante | Papel | Pacote da série | Status | Evidência |
| --- | --- | --- | --- | --- |
| `dotnet10` | runtime | `aspnet-10-runtime` | SUPPORTED | .NET 10 LTS até 2028-11-14 |
| `dotnet10-dev` | dev | `dotnet-10-sdk` | SUPPORTED | .NET 10 LTS até 2028-11-14 |
| `go1-25` | runtime | — | UPSTREAM_EOL | Par de `go1-25-dev`; a imagem não contém Go |
| `go1-25-dev` | dev | `go-1.25` | UPSTREAM_EOL | Fim do suporte em 2026-08-19 (Go 1.27); Wolfi parado em 1.25.12 |
| `go1-26` | runtime | — | SUPPORTED | Série suportada até o Go 1.28; a imagem não contém Go |
| `go1-26-dev` | dev | `go-1.26` | SUPPORTED | Wolfi 1.26.9, mesmo patch upstream de 2026-10-08 |
| `java21` | runtime | `openjdk-21-jre` | SUPPORTED | LTS; atualizações no Wolfi em 2026-10-07 |
| `java21-dev` | dev | `openjdk-21` | SUPPORTED | LTS; atualizações no Wolfi em 2026-10-07 |
| `java25` | runtime | `openjdk-25-jre` | SUPPORTED | LTS; atualizações no Wolfi em 2026-10-05 |
| `java25-dev` | dev | `openjdk-25` | SUPPORTED | LTS; atualizações no Wolfi em 2026-10-05 |
| `nodejs22` | runtime | `nodejs-22` | SUPPORTED | LTS; Wolfi em 22.23.2, upstream em 22.23.3 |
| `nodejs22-dev` | dev | `nodejs-22` | SUPPORTED | LTS; Wolfi em 22.23.2, upstream em 22.23.3 |
| `nodejs24` | runtime | `nodejs-24` | SUPPORTED | LTS; Wolfi no patch upstream 24.21.0 |
| `nodejs24-dev` | dev | `nodejs-24` | SUPPORTED | LTS; Wolfi no patch upstream 24.21.0 |
| `python3-13` | runtime | `python-3.13` | SUPPORTED | Fase security até 2029-10 |
| `python3-14` | runtime | `python-3.14` | SUPPORTED | Fase bugfix até 2030-10 |

Java não tem uma data universal de fim: depende do distribuidor do OpenJDK.
O Node.js 22 está um patch atrás do upstream no índice Wolfi; isso é uma
observação para acompanhamento, não uma mudança de status.

## Go 1.25: decisão pendente

`G04_SUPPORT_DECISION=AWAITING_OWNER_APPROVAL`

Fatos, lidos em 2026-10-13:

- A [política do Go](https://go.dev/doc/devel/release) mantém cada versão maior
  até existirem duas mais novas. O Go 1.27.0 saiu em 2026-08-19; desde então a
  1.25 não recebe correções. O último patch foi o 1.25.14, de 2026-08-19.
- O índice Wolfi tem `go-1.25` somente até 1.25.12-r1, de 2026-07-22. O
  1.25.13, de 2026-08-13, trouxe correções de segurança e não foi publicado.
  Não há evidência de backport pelo distribuidor.
- A última certificação completa (2026-10-04) construiu `go1-25-dev` com
  `go-1.25` 1.25.12-r1 e o scan não encontrou achado bloqueante, porque o
  banco de vulnerabilidades do distribuidor não registra correção para a série.
- `go1-25` não contém o toolchain: o conteúdo é a mesma base do `go1-26`. O
  risco está nos binários compilados com `go1-25-dev`, que embutem a biblioteca
  padrão da 1.25.
- Não há consumidor conhecido fora do repositório. No ECR do LAB, os dois
  repositórios Go 1.25 não têm imagem com tag nem `stable`; restam apenas filhos
  de plataforma e attestations de índices expirados, sem pull depois da
  publicação. Dentro do repositório, o par é usado pela certificação completa,
  pela certificação de aplicações e pelos contratos de runtime.
- O golden path é o par Go 1.26 e não muda.

Alternativas para o owner:

| Alternativa | Efeito | Custo e risco |
| --- | --- | --- |
| A. Depreciar com janela de migração para `go1-26`/`go1-26-dev` | Mantém a definição durante a janela, sem novas adoções; a retirada do catálogo, dos ECRs e da certificação vira uma mudança separada, como no precedente do `dotnet8` (17/09/2026) | Exige comunicar a janela; nenhuma escrita AWS até a retirada aprovada |
| B. Manter com exceção e backport | Mantém a variante como suportada | Não há backport demonstrável: exigiria um pacote próprio da série 1.25 com correções, owner e prova por correção. Contraria a composição só com pacotes Wolfi |
| C. Retirar imediatamente | Remove a variante agora | Não autorizado nesta revisão; também exige mudança de Infra e IAM |

Recomendação técnica: alternativa A. A decisão, a janela e uma eventual
inclusão do Go 1.27 são do owner e entram em mudanças próprias.

## Migração de `go1-25-dev` para `go1-26-dev`

1. Troque o estágio de build para `image-base-go1-26-dev` e o estágio final para
   `image-base-go1-26`, fixando os dois por digest de um índice promovido.
2. O toolchain 1.26 compila módulos com `go 1.25` no `go.mod`, conforme a
   compatibilidade do Go; não é preciso mudar a diretiva para migrar.
3. Recompile, rode os testes da aplicação nas duas arquiteturas e confira a
   versão embutida com `go version -m <binário>`.
4. Imagens finais já implantadas não mudam sozinhas: a correção só chega no
   próximo build da aplicação.
