# ADR-0007 — Fonte de pacotes por framework: Wolfi default, Alpine v3.24 como exceção governada do `dotnet8`

| Informação | Valor |
| --- | --- |
| Estado | Proposto (Aceito com a aprovação de code owner do PR que o integra) |
| Data | 17/09/2026 |
| Owners | Containers Products (`@alric-corp/github_xj7_maintainer`) |
| Substitui | [ADR-0001](0001-dotnet8-fora-do-lote-padrao.md) na parte "`dotnet8` fora do lote padrão" — a causa daquela exclusão deixou de existir |
| Aplicação | `policies/sources/package-sources.json`; `scripts/pipeline/governance/source_trust.py`; `scripts/pipeline/artifacts/sbom_completeness.py`; `distroless/sources/` |
| Revisão | `review_by` em `policies/sources/package-sources.json` (`2026-11-30`) |

## Contexto

O ADR-0001 tirou `dotnet8` do lote padrão porque o gate de CVE o bloqueava e a
correção não existia na origem: o `APKINDEX` do Wolfi publica no máximo
`dotnet-8-sdk 8.0.127-r0`, enquanto o próprio `security.json` do Wolfi declara
cinco CVEs corrigidas em `8.0.131-r0` — uma versão que o Wolfi nunca publicou.
Rebuild não resolvia, e a política do produto é zero exceções ao gate.

O Alpine v3.24 publica `dotnet8-sdk 8.0.131-r0` e `aspnetcore8-runtime
8.0.31-r0`. As cinco CVEs são **rastreadas** pelo `secdb` do Alpine e corrigidas
em `8.0.29-r0`/`8.0.31-r0`, ou seja, o silêncio do scanner ali é silêncio
rastreado, não ausência de advisory — diferente do caso `zlib`/Alpine
investigado no ADR-0006, onde o Alpine simplesmente não rastreava a CVE.

Trocar a base do catálogo inteiro para Alpine seria uma regressão: para CVEs de
2026 o Wolfi rastreia 4.426 contra 1.843 do Alpine. A decisão é, portanto, sobre
**uma** definição, não sobre a distribuição padrão da fábrica.

## Decisão

1. **Wolfi continua a fonte default** de todo o catálogo. Nenhuma das 16
   definições Wolfi muda: a composição resolvida por `apko show-config` é
   byte-idêntica à anterior.
2. A fonte de pacotes passa a ser **explícita e versionada**, separada da
   composição. `distroless/image-base.yaml` não declara mais `repositories`/
   `keyring`; eles vivem em `distroless/sources/<source>.yaml` e são escolhidos
   pela cadeia de `include` do framework. Isso é imposto pela mecânica do apko:
   `include` é string única e faz APPEND de listas, nunca override — declarar
   duas fontes na mesma cadeia produziria um artifact com dois keyrings.
3. **Alpine v3.24 é exceção autorizada apenas para `dotnet8` e `dotnet8-dev`**,
   nomeados em `framework_sources` com motivo, dono, ADR e `review_by`.
   Qualquer outro framework que entre nessa cadeia falha fechado.
4. `dotnet8` passa a ser um **par** `dotnet8` (runtime ASP.NET, sem SDK e sem
   shell) + `dotnet8-dev` (SDK e toolchain), como os demais frameworks
   compilados, e volta ao catálogo sem exceção de saúde.
5. `edge`, `latest`, rolling, auto-detecção e fallback entre fontes são
   proibidos: a release aparece no nome do arquivo, na URL e na policy.

## Controles que a decisão exige

- **Source trust (fail closed):** o par `(repositories, keyring)` que um
  framework resolve precisa casar exatamente com uma fonte declarada, e essa
  fonte precisa ser a autorizada para ele.
- **Keyring efetiva:** o apko descobre chaves Alpine pela rede
  (`https://alpinelinux.org/keys/`) e as une à keyring declarada, sem knob para
  desligar — `--keyring-append` só adiciona e `--ignore-signatures` enfraquece.
  Por isso a keyring efetiva registrada em `apko.lock.json` é conferida entre o
  `apko lock` e o `apko build`: toda chave precisa ser byte-idêntica a uma chave
  pinada e, quando descoberta, vir de uma origem permitida. Isso é **detecção
  determinística com falha fechada, não prevenção** — `KEYRING_REPRODUCIBILITY =
  PARTIAL`, e não deve ser descrito como STRONG.
- **SBOM:** o apko monta o SPDX agregando os SBOMs por-pacote que o Melange
  embute em `/var/lib/db/sbom/` dentro do `.apk`. Pacotes do `abuild` (Alpine)
  não trazem esse documento, então o apko não tem o que agregar e eles ficavam
  ausentes. O documento é completado a partir do `apko.lock.json` do mesmo build
  e conferido contra ele. O resultado é **APKO + LOCK COMPLETION** e não pode ser
  descrito como saída pura do apko.

## Consequências

- Catálogo passa a 18 definições: 16 Wolfi + 2 Alpine.
- O lote automático (schedule e push na `main`) **não muda**: continua o perfil
  P0-04 (`go1-26`, `go1-26-dev`). A seleção de framework passa a ser possível
  só no `workflow_dispatch` manual, validada contra o próprio catálogo por
  `scripts/pipeline/catalog/validate_inputs.py`.
- A promoção agendada para `stable` **não passa a incluir `dotnet8`**: o caller
  agendado continua com o perfil P0-04. Promover `dotnet8` exige o
  `workflow_dispatch` de `promote-stable.yml`, com a mesma janela de soak.
- O publisher não ganhou nenhum conhecimento de distribuição: fonte de pacotes é
  assunto da composição, não da publicação.
- A exceção de saúde de `dotnet8` é removida: o motivo registrado nela (o Wolfi
  não publicar a correção) não se aplica mais.

### Risco residual aceito, registrado explicitamente

As imagens `dotnet8`/`dotnet8-dev` trazem `zlib 1.3.2-r0` do Alpine. É a mesma
linha de `zlib` que o ADR-0006 investigou: o Wolfi rastreia `CVE-2026-85091` e
entrega `1.3.2.1_rc20260601-r0`; o `secdb` do Alpine **não rastreia** essa CVE,
então o Trivy fica em silêncio por ausência de advisory, não por correção — o
padrão de "falso verde" que aquela investigação documentou. O gate passa, e
passa por um motivo que não vale como prova.

Isso é aceito aqui porque: (a) a decisão é sobre `dotnet8`, cujo bloqueio real
(as cinco CVEs de .NET) tem correção comprovada na origem em ambas as bases de
advisory; (b) o risco fica **visível** — a completude de SBOM faz `zlib`
aparecer no SPDX publicado, onde antes nenhum pacote Alpine aparecia, então uma
análise downstream consegue enxergá-lo mesmo com o feed do Alpine em silêncio;
(c) nenhum outro framework herda essa exposição, porque a exceção é nominal.
O critério de revisão abaixo cobre a saída: se o `dotnet8` voltar ao Wolfi, esta
exposição termina junto.

## Critério de revisão

Rever até `2026-11-30`, ou antes se qualquer uma valer:

1. o Wolfi publicar `dotnet-8-sdk >= 8.0.131-r0` — nesse caso `dotnet8` volta à
   fonte default e a exceção é revogada;
2. o .NET 8 chegar ao fim do suporte LTS (novembro de 2026) — nesse caso a
   decisão é retirar o par do catálogo, não migrar de fonte;
3. surgir um segundo candidato a usar Alpine — nesse caso a exceção pontual
   precisa ser reavaliada como política, não estendida por precedente.
