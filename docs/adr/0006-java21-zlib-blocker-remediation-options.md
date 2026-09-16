# ADR-0006 — Java 21: opções de remediação para o bloqueio zlib (CVE-2026-85091)

| Informação | Valor |
| --- | --- |
| Estado | **PROPOSED — decisão do Tech Lead PENDING** (mesmo padrão do ADR-0002) |
| Data | 16/09/2026 |
| Owner | Containers Products (`@alric-corp/github_xj7_maintainer`) |
| Decisão pendente | Tech Lead — ver "Pergunta objetiva" |
| Aplicação | Nenhuma ainda — este ADR não implementa nada, apenas registra a investigação e as opções |
| Origem | Ataque ao segundo framework da V1 (Java 21), golden path Go 1.26 já `CLOSED` |

## TL;DR

Java 21 chega até o scan e falha em exatamente um CVE (confirmado hoje,
não por analogia com outros frameworks). O pacote `zlib` do Wolfi que
`openjdk-21-jre` exige diretamente não tem, hoje, uma correção
**lançada**. Mas existe, sim, uma correção **já escrita e mesclada** no
repositório oficial `madler/zlib` — só não foi cortada como release, e o
próprio Wolfi já tentou (duas vezes) marcar o CVE como corrigido sem
nunca trocar o código-fonte compilado. `SECURITY_GATE_RELAXED = NO` em
toda a investigação: nada foi ignorado, reduzido ou contornado.

## 1. Target

```
JAVA21_RUNTIME = java21   (frameworks/java21.yaml — openjdk-21-jre)
JAVA21_DEV     = java21-dev (frameworks/java21-dev.yaml — openjdk-21 + busybox)
```

Ambos existem no catálogo; nenhuma variante nova foi inventada.

## 2. Baseline

`main == origin/main`, working tree limpo, `CATALOG_DEFINITIONS = 17`
(inalterado). Go 1.26/`go1-26-dev` não foram tocados nesta investigação —
nenhum arquivo de `frameworks/go1-*`, `.github/workflows/promote-stable.yml`,
`validate_ecr_repository.py` ou Terraform foi modificado.

## 3. Reprodução da falha (hoje, não por analogia)

Run real e recente, caminho normal de validação (PR #75, `pull_request`,
`Validate full catalog for shared-impact PR`), job
[`104691986201`](https://github.com/alric-corp/alric-containers-image-base/actions/runs/35064550485/job/104691986201):

| Step | Resultado |
| --- | --- |
| `Build multi-architecture OCI artifact once` | `success` |
| `Scan both architectures` | **`failure`** |

Relatório Trivy baixado e parseado individualmente, as duas arquiteturas:

```
amd64: CVE-2026-85091  zlib  1.3.2.1_rc20260601-r0 -> 1.3.3-r0  MEDIUM  status=fixed
arm64: CVE-2026-85091  zlib  1.3.2.1_rc20260601-r0 -> 1.3.3-r0  MEDIUM  status=fixed
```

**Confirmado, não assumido**: mesma CVE, mesmo pacote, mesma
`FixedVersion` que os outros frameworks bloqueados — mas verificado
independentemente para `java21` especificamente, com evidência própria.

## 4. Cadeia de dependência concreta

Log real do `apko build` (mesmo job) lista os ~35 pacotes resolvidos.
Cruzado com o `APKINDEX` ao vivo (campo `D:`, dependências declaradas):

```
openjdk-21-jre (21.0.12.1-r2)
  depends: ... so:libz.so.1 ...          <- direto
libpng (1.6.58-r3, puxado por openjdk-21-jre p/ suporte AWT/PNG)
  depends: ... so:libz.so.1              <- direto
freetype (2.14.3-r6, puxado por openjdk-21-jre p/ fontconfig/renderização)
  depends: ... so:libz.so.1              <- direto
                    ↓
        so:libz.so.1 (virtual/soname)
                    ↓
        zlib = 1.3.2.1_rc20260601-r0     <- único provedor no repo configurado
```

Não é "o Wolfi traz zlib": é `openjdk-21-jre` exigindo `libz.so.1`
diretamente (JAR/`java.util.zip`/AWT), reforçado por duas dependências
transitivas do próprio stack gráfico do JRE. Isso não é eliminável sem
remover o JRE inteiro (ver opção B, seção 7).

Por que Go 1.26 não é afetado: binários Go são estaticamente linkados
(sem `so:libz.so.1`), e `go-1.26`/`busybox` não têm nenhuma aresta de
dependência até zlib — não é coincidência de sorte, é ausência real de
vínculo.

## 5. APKINDEX / upstream — investigação completa

Origem efetivamente configurada pela fábrica (`distroless/image-base.yaml`):
`https://packages.wolfi.dev/os` — confirmado no arquivo, não assumido.

**`FIXED_PACKAGE_AVAILABLE = NO`**, mas com uma nuance importante que uma
checagem superficial do `APKINDEX` não revela:

- `zlib.net` (site oficial) e a API de releases do GitHub
  `madler/zlib` confirmam: a release atual é **1.3.2** (fev/2026). **Não
  existe release 1.3.3** em lugar nenhum — nem tag, nem tarball, nem
  anúncio.
- A CVE real (`CVE-2026-85091` = `GHSA-g5fp-32jq-cfw2`, publicada
  03/09/2026): heap buffer overflow em `gz_vacate()` (`gzwrite.c`) ao
  chamar `gzprintf()`/`gzvprintf()` após um stall de escrita não
  bloqueante, com ponteiro de buffer externo obsoleto.
- **O Wolfi já tentou "corrigir" isto duas vezes** (`zlib.yaml`,
  commits públicos `wolfi-dev/os`): `epoch: 5 → 6` (13/09/2026,
  comentário `# GHSA-g5fp-32jq-cfw2`) e depois `6 → 7` (mesmo
  comentário). **As duas vezes, o pipeline continua fazendo
  `git-checkout` do mesmo `expected-commit: da607da7...`, tag `v1.3.2`
  — nenhum patch, nenhuma mudança de fonte.** O binário resultante é
  idêntico ao anterior. Isso explica por que o Trivy continua bloqueando
  mesmo depois dessas duas tentativas: não há correção real no código, só
  bookkeeping de epoch.
- **A correção real já existe upstream, só não foi lançada**: commit
  [`e3dc0a85b7`](https://github.com/madler/zlib/commit/e3dc0a85b7032e98380dec011bc8f2c2ee0d8fca)
  (05/04/2026, "Avoid undefined behavior in gzwrite.c", autor Mark Adler
  — o mantenedor do projeto), na branch default do repositório oficial —
  **é o commit mais recente do repositório inteiro**, sem nenhum commit
  posterior tocando `gzwrite.c`. O diff:

  ```c
  -    if (strm->next_in + strm->avail_in <= state->in + state->size)
  +    if (strm->next_in == NULL ||
  +        strm->next_in + strm->avail_in <= state->in + state->size)
  ```

  Corresponde exatamente ao mecanismo descrito na CVE (ponteiro externo
  obsoleto/NULL usado em aritmética de ponteiro sem checagem).

## 6. Não-bypass

Nada disto foi feito: exceção de CVE, allowlist, redução de severidade,
desligar o scanner, alterar exit code, remover pacote sem entender a
dependência, pin consciente de versão vulnerável, ou marcar o scan como
opcional.

```
SECURITY_GATE_RELAXED = NO
```

## 7. Opções de remediação avaliadas

| Opção | Viável? | Motivo |
| --- | --- | --- |
| A. Pacote corrigido já disponível em outro repositório Wolfi confiável | **NÃO** | Único repositório configurado é `packages.wolfi.dev/os`; nenhum canal alternativo oficial foi identificado. Usar uma origem diferente é decisão corporativa de rede/mirror, fora do escopo técnico desta investigação |
| B. Atualização de dependência que elimina a necessidade de zlib | **NÃO** | `openjdk-21-jre` exige `so:libz.so.1` diretamente — não há como rodar uma JRE sem isso. Não é uma dependência substituível por outra biblioteca |
| C. Package próprio via Melange, usando release oficial corrigida | **Precondição falsa como enunciada** | Não existe release oficial 1.3.3 — mas existe o commit oficial não lançado (`e3dc0a85b7`), o que reabre a opção sob uma forma ligeiramente diferente (ver seção 8) |
| D. Aguardar upstream | **Sempre viável, sem custo, sem risco** | zlib corrigido eventualmente sai como release; ou o Wolfi finalmente atualiza `expected-commit` no próprio `zlib.yaml` |

## 8. Spike: viabilidade de um zlib próprio via Melange (não implementado)

Objetivo do spike: determinar viabilidade, não introduzir bypass. Nada
abaixo foi publicado como solução; é avaliação.

- **Source oficial**: `https://github.com/madler/zlib`, seria o mesmo
  repositório que o próprio `wolfi-dev/os/zlib.yaml` já usa hoje — não é
  uma fonte nova ou menos confiável.
- **Commit fixo**: `e3dc0a85b7032e98380dec011bc8f2c2ee0d8fca`. Pinado por
  hash, exatamente como o Wolfi já pina por `expected-commit` — mesmo
  modelo de confiança que a fábrica já aceita para o pacote de CAs via
  Melange.
- **Checksum**: não aplicável da mesma forma que um tarball assinado —
  o pin é o próprio hash do commit Git (SHA-1 do commit), verificado pelo
  `git-checkout` do Melange contra o `expected-commit`, igual ao padrão
  já usado pelo Wolfi. Nenhum checksum adicional foi calculado nesta
  investigação porque nenhum build foi executado.
- **Build dependencies**: idênticas às do `zlib.yaml` atual do Wolfi
  (autoconf, automake, build-base, busybox, ca-certificates-bundle,
  glibc-2.44-dev, libtool) — reaproveitáveis sem mudança.
- **Runtime files / ABI**: o commit `e3dc0a85b7` só modifica uma
  checagem de ponteiro em `gzwrite.c` (2 linhas), não a API pública nem
  o layout binário de `libz.so.1` — risco de quebra de ABI para os
  consumidores (`libpng`, `freetype`, `openjdk-21-jre`) avaliado como
  **muito baixo**, mas não testado nesta rodada (nenhum build foi
  executado — não há `docker`/`melange` disponíveis nesta máquina para
  compilar e comparar binário real).
- **amd64 / arm64**: a receita do Wolfi já compila as duas arquiteturas
  pelo pipeline padrão (`autoconf/make` + `strip`); nada no commit é
  específico de arquitetura.
- **Pacotes que dependem de `libz.so.1`**: `openjdk-21-jre`, `libpng`,
  `freetype` (java21), e — por extensão, se o pacote fosse promovido a
  uso geral — qualquer outro framework do catálogo com a mesma cadeia
  (java25, nodejs22/24, python3-13/14, dotnet10; não confirmado
  individualmente nesta rodada, focada em Java).
- **Conflito com o pacote Wolfi**: exigiria configurar o `apko` da
  fábrica para consultar um repositório Melange local com prioridade
  sobre `packages.wolfi.dev/os` para a resolução de `so:libz.so.1`
  (mesmo padrão já usado para o pacote de certificados via
  `--repository-append`/`--keyring-append`), e versionar o pacote
  próprio acima do que o Wolfi publica para que o resolvedor o prefira.
- **SBOM / scan**: um zlib próprio teria SBOM gerado normalmente pelo
  pipeline existente (nada muda no mecanismo de SBOM); o **scan
  precisaria ser reexecutado contra o binário real** para confirmar que
  o Trivy para de reportar `CVE-2026-85091` — não presumido, a validar
  quando/se isto for construído de verdade.

**Conclusão do spike: tecnicamente viável, com risco baixo e bem
compreendido — mas não construído nem testado nesta rodada.** Nenhuma
evidência de build real existe ainda; nada disto deve ser lido como
"pronto para produção".

## 9. Classificação

```
JAVA21_BLOCKER = SAFE_CUSTOM_PACKAGE_POSSIBLE
```

Não é `OUR_CODE` (nada no nosso pipeline está errado — o gate está
correto). Não é puramente `UPSTREAM_WOLFI` sem alternativa (existe, sim,
uma alternativa tecnicamente segura, só que exige decisão de manter um
pacote fora do Wolfi temporariamente). Não é `EXTERNAL_DECISION_REQUIRED`
no sentido de "não sabemos o que fazer tecnicamente" — sabemos
exatamente o que seria necessário; a decisão pendente é de escopo/risco
aceitável, não de investigação.

## 10. Impacto sobre as famílias

Um zlib próprio, se aprovado, beneficiaria potencialmente todos os
frameworks hoje bloqueados pela mesma CVE (13 no total, ver matriz de
`specs/2026-09-16-v1-reference-go126/evidence.md`), não só Java — mas
esta investigação não expandiu escopo para validar isso individualmente
em cada framework; documentado aqui como consequência esperada, não
como fato verificado para todos.

## 11. Manutenção futura

Se aprovado, o pacote próprio deve ser **explicitamente temporário**:
critério de remoção = Wolfi publicar `zlib` com o código de
`e3dc0a85b7` (ou posterior) incorporado — verificável comparando o
`expected-commit`/tag do `zlib.yaml` upstream contra o commit da
correção. Revisão obrigatória, não indefinida (mesmo padrão do
ADR-0001/dotnet8).

## Pergunta objetiva para o Tech Lead

> Queremos manter temporariamente um package `zlib` próprio na fábrica
> (buildado via Melange a partir do commit oficial `e3dc0a85b7` do
> repositório `madler/zlib`, que já contém a correção da
> `CVE-2026-85091` mas ainda não foi lançado como release), enquanto o
> Wolfi não publica a versão corrigida — ou preferimos aguardar o
> upstream?

```
TECH_LEAD_DECISION_REQUIRED = YES
```
