# HANDOFF — P1-03 Wolfi signing-key defense-in-depth

- Repositório: alric-containers-image-base, baseline
  `f792aecd4fbfa28bdb9fd44bf920c167f64c5653` inicialmente limpo.
- Objetivo: [spec.md](spec.md); aceite: [acceptance.md](acceptance.md).
- Decisão arquitetural independente informada pelo usuário em 13/09/2026:
  **READY TO REFORMULATE AND IMPLEMENT**. A propriedade local foi reformulada;
  o requisito original de exclusividade continua não satisfeito.
- Estado: **IMPLEMENTED + VERIFIED LOCALLY + RESIDUAL TOOLING RISK DOCUMENTED**.
  Sem commit/push/PR ou auto-aprovação; preparado para nova revisão independente.
- Fontes oficiais conferidas antes de editar: [evidence.md](evidence.md).
- Decisões: chave/pin adjacentes em `melange/keys/`, inventory existente,
  preflight offline e monitor remoto separado, sem auto-update.
- Lista completa de 27 arquivos em [evidence.md](evidence.md); inclui 6
  Markdown da spec. Nenhum teste útil removido, novo script adversarial,
  mudança no Apko ou relaxamento dos controles.
- Checks repetidos: 268 unitários, 24 integração e 17 Wolfi PASS; lints
  local/shared/workflows e actionlint dos workflows alterados exit 0.
  Actionlint amplo exit 1: três diagnósticos somente no workflow gerado
  `cve-triage.lock.yml`, reproduzidos no blob idêntico da HEAD. A exclusão de
  locks gerados do lint manual já existia; ver ressalva e logs na evidence.
  Contexto IA e diff check exit 0. Socket TLS/Docker e leituras remotas
  exigiram execução autorizada.
- Mínimos reais aarch64: lock/build Apko e build Melange exit 0; chave errada
  e ausente em fixtures Apko exit 1. Fontes/monitor: SHA-256 iguais.
- Os mínimos positivos foram repetidos nesta continuação. Os negativos
  reais de chave errada/ausente são os registros da execução anterior.
  Monitor atual same e comparação antes/depois: chave e pin intactos.

## Known Tooling Limitation

`contents.keyring` **≠ exclusive trust set**. Apko e a biblioteca usada por
Melange adicionam chaves do repository via `/apk-configuration`/JWKS ao
conjunto de verificação: `explicit keyring + discovered keys`. Não existe
opção oficial suportada de desativação seletiva nas versões avaliadas.

Um adversário com controle de repository/CDN/TLS e capacidade de servir
discovery, JWKS e index/packages assinados por outra key pode introduzir
essa key no conjunto aceito. O pin local e o monitor não eliminam esse risco.

**EXPECTED TOOLING LIMITATION REPRODUCED**: índice assinado pela RSA da
fixture foi rejeitado sem discovery (exit 1) e aceito com discovery (exit 0),
com chave adicional no lock. Evidência original preservada, não reexecutada
nesta reformulação. Não alegar execução de payload, assinatura do APK mínimo,
security control passed ou exclusive independent trust anchor achieved.

Wolfi oficial retornou HTTP 404 em 2026-09-13T03:07:44Z; lock real registrou
zero chaves descobertas. É observação operacional atual, não garantia futura
nem invariant de segurança.

## Corporate handoff — P0-03

Caso o ambiente corporativo exija uma trust boundary realmente independente
da origem Wolfi, utilizar repository mirror/proxy controlado que não exponha
`apk-configuration`/JWKS e restrinja egress do build à origem aprovada.

```text
Corporate Build → Internal Wolfi Mirror
                    ├── APKINDEX
                    ├── packages
                    └── no apk-configuration/JWKS
Verificação: local reviewed Wolfi key; egress restrito à origem aprovada.
```

Requisito posterior com Cloud/Network/Security. Não foi escolhida tecnologia
de mirror, implementada infraestrutura ou declarada adequação corporativa.
O requisito não é dependência do aceite local reformulado do P1-03.

## Upstream follow-up

Recomendar futura issue em [chainguard-dev/apko](https://github.com/chainguard-dev/apko)
por modo suportado equivalente a `explicit-keys-only`/`--no-key-discovery`,
desativando repository key discovery, preservando signature verification e
usando somente o keyring explicitamente configurado. **Issue não aberta.**

## Próximos aceites

Nova revisão independente do diff/spec/evidência reformulados antes de
integrar: **NOT RUN**. Nenhuma auto-aprovação nesta sessão.

Hosted acceptance: **NOT RUN**. Após autorização e merge, provar
`hosted build → local versioned key configured → preflight passes → normal
package verification/build continues`, sem exigir exclusividade de trust.
Eventual CVE zlib permanece BLOCKED_UPSTREAM separado; não reduzir controles.
Nenhuma ação remota de escrita foi realizada.

Confirme o estado real do Git antes de continuar.

## Atualização pós-integração — 2026-09-14

Os estados pré-merge acima são históricos. A [reconciliação](evidence.md#reconciliação-hospedada--2026-09-14)
registra main `8ed8260eba75d4f8b5d856cd1fba37a404a5129a`,
run 34852458933/1: preflight com pin correto, Melange e Apko lock/build
go1-26/go1-26-dev nas duas arquiteturas concluídos.
**Mínimo hosted PASS observado; lote PARTIAL / BLOCKED_UPSTREAM**.
O scan representativo nodejs22 bloqueou CVE-2026-85091 em zlib; nenhuma
correção/dispensa foi aplicada. A revisão independente desta coleta está
PENDING; ela não herda a aprovação da implementação.

Nenhuma execução adicional é necessária para repetir o mínimo já observado.
A ausência de lote verde e os requisitos corporativos continuam separados;
preservar integralmente a Known Tooling Limitation acima.
