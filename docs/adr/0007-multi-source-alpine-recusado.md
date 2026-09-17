# ADR-0007 — Multi-source com Alpine v3.24: tecnicamente aprovado, adoção recusada

| Informação | Valor |
| --- | --- |
| Estado | Proposto (Aceito com a aprovação de code owner do PR que o integra) |
| Data | 17/09/2026 |
| Owners | Containers Products (`@alric-corp/github_xj7_maintainer`) |
| Relacionado | [ADR-0001](0001-dotnet8-fora-do-lote-padrao.md) (mantido, não substituído), [ADR-0006](0006-java21-zlib-blocker-remediation-options.md) |
| Aplicação | **Nenhuma.** Este ADR registra uma decisão negativa: nada muda no produto |

## Contexto

`dotnet8` está fora do lote padrão desde o ADR-0001 porque o gate de CVE o
bloqueia e a correção não existe na origem: o `APKINDEX` do Wolfi para em
`dotnet-8-sdk 8.0.127-r0`, enquanto o `security.json` do próprio Wolfi declara
cinco CVEs corrigidas em `8.0.131-r0` — uma versão que o Wolfi nunca publicou.

Uma sequência de POCs investigou usar outra distribuição de pacotes só para esse
framework. O resultado técnico foi positivo em todas as frentes, executado sobre
artifacts reais nas duas arquiteturas:

| Verificação | Resultado |
| --- | --- |
| Alpine v3.24 como fonte para `dotnet8`/`dotnet8-dev` | build multiarch PASS |
| Correção na origem | `dotnet8-sdk 8.0.131-r0`, `aspnetcore8-runtime 8.0.31-r0`; **5/5** CVEs rastreadas e corrigidas no `secdb` do Alpine — verde verdadeiro, não silêncio de advisory |
| Trivy | PASS, `OS=alpine/3.24`, 0 achados bloqueantes |
| Contrato funcional | PASS nas duas arquiteturas: non-root 10000, raiz somente-leitura, CA/TLS nos dois sentidos, `dotnet publish` multi-stage sem rede, runtime sem SDK/shell/apk |
| SBOM | lacuna encontrada e resolvida: o apko só descreve pacotes cujo `.apk` embute SBOM do Melange, e o `abuild` do Alpine não embute — completar o documento a partir do `apko.lock.json` do mesmo build fecha isso |
| Keyring | o apko descobre chaves Alpine pela rede e as une à keyring declarada, sem knob para desligar; conferir a keyring efetiva do lock entre `lock` e `build` faz isso falhar fechado (detecção determinística, não prevenção) |
| Publisher | nenhum special case necessário: fonte de pacotes é assunto de composição, não de publicação |

O `include` do apko é string única e faz APPEND de listas, então a fonte só pode
ser escolhida pela cadeia que o framework entra — não por override. Isso foi
medido, não presumido.

## Decisão

**Não adotar.** `dotnet8` e `dotnet8-dev` não são oficializados, Alpine não vira
fonte suportada e o modelo multi-source não entra no produto.

O motivo não é técnico e sim de custo/benefício sobre a janela de suporte
restante: o **.NET 8 chega ao fim do suporte LTS em novembro de 2026**, e
`dotnet10`/`dotnet10-dev` já estão no catálogo, verdes no caminho Wolfi padrão,
sem exceção alguma para carregar. Adotar significaria manter permanentemente um
segundo contrato de confiança, o monitoramento de rotação de chave de uma
segunda distribuição e o caminho de completude de SBOM — por cerca de dois meses
de suporte.

Havia ainda um risco residual que só fazia sentido aceitar se a adoção
compensasse: as imagens Alpine trazem `zlib 1.3.2-r0`, que o `secdb` do Alpine
não rastreia para `CVE-2026-85091` — o padrão de falso verde que o ADR-0006
documentou. Recusada a adoção, essa exposição não entra no produto.

## Consequências

- O catálogo permanece com 17 definições, todas Wolfi. `WOLFI_DEFAULT = YES`.
- `dotnet8` continua exatamente como o ADR-0001 o deixou: no catálogo, fora dos
  três lotes, bloqueado pelo gate de CVE, com a exceção registrada em
  `policies/operations/health.json`. Nada é declarado READY.
- `dotnet8-dev` não existe como produto.
- Lote padrão, escopo do schedule, publisher e gates de segurança: inalterados.
- **.NET 10 é o caminho suportado** para consumidores que precisam sair do .NET 8.
- Os POCs continuam válidos como evidência técnica. Se algum dia existir um
  segundo caso de uso real para multi-source — um que não dependa de um runtime
  em fim de vida — esta investigação é o ponto de partida, e a conclusão a
  revisitar é a de custo, não a de viabilidade.

## Critério de reversão

Reabrir a discussão apenas se **ambas** valerem: existir um framework suportado
(não em fim de vida) sem correção viável no Wolfi, **e** houver dono disposto a
manter o contrato de confiança da segunda fonte e a rotação de chaves dela. Um
caso isolado e temporário não justifica a governança permanente — foi
exatamente essa a conta que reprovou a adoção aqui.
