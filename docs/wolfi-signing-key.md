# P1-03 — Wolfi signing-key defense-in-depth

A chave pública em [melange/keys/wolfi-signing.rsa.pub](../melange/keys/wolfi-signing.rsa.pub)
e o [pin SHA-256 adjacente](../melange/keys/wolfi-signing-key.json) são insumos
revisáveis no repositório. Não são CAs TLS, não são segredo e não substituem
a chave efêmera usada para assinar o pacote Melange próprio.

Apko referencia `melange/keys/wolfi-signing.rsa.pub` desde a raiz. Melange
referencia `keys/wolfi-signing.rsa.pub` dentro de `/work`, onde o executor
monta `melange/`. O diretório canônico evita cópias da trust anchor e mantém
o contrato do reusable fixado. Package repositories permanecem iguais.

`pin_inventory trust` e `lint` verificam o SHA-256 dos bytes PEM, formato RSA
SPKI via OpenSSL e keyrings locais via PyYAML. `build_image` verifica o
arquivo/pin antes de lock/build sem PyYAML; Makefile e o job anterior ao
reusable executam `trust`. Chave ausente/alterada ou pin inválido bloqueia.
O manager deste pin é `human-review`; ele não é gerido por Renovate.

## Known Tooling Limitation

**A migração do keyring explícito, sozinha, não prova confiança exclusiva na
chave local.** O Apko fixado também descobre chaves em
`/apk-configuration`/JWKS da origem dos packages, inclusive com keyring local.
Melange utiliza Apko internamente. A análise e o teste adversarial desta
dependência foram verificados localmente e em execução hospedada real.
`contents.keyring` **≠ exclusive trust set**: o conjunto efetivo inclui
`explicit keyring + discovered keys`. Um adversário que comprometa
repository/CDN/TLS e sirva `apk-configuration`, JWKS e index/packages
assinados por outra chave pode introduzir confiança adicional aceita pelo
Apko. A implementação local não elimina esse risco.

A decisão arquitetural reformulou esta fatia como defense-in-depth:
reviewability, pin da chave explícita, rotação revisada e detecção de drift.
O teste anterior permanece **EXPECTED TOOLING LIMITATION REPRODUCED**.
Não é evidência de que um controle de exclusividade passou.

O 404 observado no endpoint oficial é um fato operacional datado: nessa
consulta discovery é no-op. Não há garantia de continuidade desse estado,
nem gate ou requisito permanente de HTTP 404. A evidence registra a consulta.

### Reconfirmação no Apko fixado atual (13/10/2026)

A análise e o teste adversarial acima foram feitos no pin anterior (v1.2.43).
O pin atual do reusable (`apko@sha256:7fcdcd1c…`) executou **v1.4.6, commit
`51c298aa`**, conforme `./apko version` no job 115257202930 do run
38385657268. O comportamento foi reconferido no código-fonte dessa versão,
sem novo teste adversarial:

- `InitDB` chama discovery (`/apk-configuration` → JWKS) para todo
  repositório de build http(s), inclusive em `apko build --lockfile`; erros
  de discovery são ignorados e não há opção para desabilitá-la. Repositórios
  locais ou `file://` não fazem discovery.
- A verificação do índice aceita qualquer assinatura validada por qualquer
  arquivo de `/etc/apk/keys`: chaves explícitas e descobertas.
- `apko lock` grava no lock as chaves configuradas mais as encontradas por
  uma requisição de discovery **própria**; a resolução faz outra requisição.
  Chaves de `--keyring-append` não são gravadas.
- O build com lockfile instala pelos checksums do lock (Q1, SHA-1 do control,
  e `datahash` SHA-256 do data): não troca bytes depois do lock, mas herda a
  confiança usada na resolução.

O log do lock registra `Discovered 0 auto-discovered keys` nesse run. É um
fato datado daquela requisição, não garantia de exclusividade.

## Superfície de confiança verificada localmente

`wolfi_trust.config_errors`, executado por `pin_inventory trust` antes do
reusable e por `lint`, trata como superfície revisada não só o keyring, mas
também as origens: `repositories` deve ser exatamente
`https://packages.wolfi.dev/os` onde aparecer; `build_repositories`,
`runtime_repositories` e `baseimage` (índice instalado sem verificação de
assinatura) são rejeitados; `include` só pode apontar para configurações
escaneadas de `distroless/`. Assim, uma mudança de configuração não amplia
origem de pacotes nem de discovery sem revisão explícita desta regra. Isso
não bloqueia chaves que a origem venha a anunciar.

`wolfi_trust.lock_observation` classifica offline um `apko.lock.json` como
`PINNED_ONLY`, `UNEXPECTED` ou `INVALID`. Os locks originais do run público
37806495087 (fixture HGC-04) registram somente a chave fixada e as origens
revisadas. Por causa da requisição separada descrita acima, `PINNED_ONLY`
detecta uma ativação não adaptativa de discovery (por exemplo, uma mudança
legítima do upstream); não prova que todo índice resolvido só verificaria
com a chave local. Nenhum gate consome essa observação: usá-la como relatório
ou bloqueio exige decisão do owner.

## Monitoramento operacional

O `pin_inventory check` existente no health diário compara a fonte oficial
`sources.distribution` com o SHA local/esperado. Resultado `same` é saudável;
`divergent`, `unavailable` ou `local-invalid` falha o passo e o job de saúde
após preservar a evidência. Há timeout de 20s e limite de tamanho. O próprio
job e seu resumo são o canal de alerta, com os donos/escalação definidos em
[health.json](../policies/operations/health.json).

Falha fechada para o **alerta** evita tratar uma consulta inconclusiva como
saúde. Esse job não é dependência de build, validação ou promoção. Nenhum
preflight de build consulta a signing key remota; indisponibilidade do
monitor não impede por si só um build que verifica packages com a chave
local. Nem mismatch nem erro de rede escrevem chave ou pin.

## Procedimento de rotação

1. Receber anúncio oficial ou alerta de divergência. Tratar divergência como
   sinal para investigar, nunca como autorização para confiar.
2. Dono de Containers Products confere a nova chave por pelo menos duas
   fontes oficiais de distribuição independente: endpoint Wolfi e arquivo
   no repositório oficial `wolfi-dev/os` em commit confirmado pela API/GitHub.
   Consultar URLs e commits atuais; não assumir o fingerprint desta entrega.
3. Baixar cada arquivo em diretório temporário separado da chave versionada;
   validar RSA SPKI PEM e comparar SHA-256 dos bytes exatos. Registrar URLs,
   commit, horário, digests e igualdade. Se divergir, **STOP** e blocker.
4. Preparar PR atualizando conjuntamente chave pública, `expected_sha256` e
   fontes do JSON. Registrar legitimidade da rotação, evidência de anúncio
   quando disponível, impacto e testes. Nenhum comando de build faz repin.
5. Executar `make check` (`test-unit test-integration lint-local
   lint-workflows`), `actionlint`, check de contexto e diff; mínimos reais e
   negativos de chave errada/ausente. Preservar a evidência da limitação de
   discovery; reavaliá-la se o comportamento das ferramentas mudar, sem
   exigir sua eliminação como aceite local desta fatia.
6. Revisor humano/code owner aprova a mudança e sua evidência antes de merge.
   Só então builds futuros usam o novo par como chave explícita. Assinatura válida
   não equivale a package seguro: preservar todos os gates de CVE existentes.

Rollback exige restaurar o último par revisado por PR, com a mesma validação.
Se esse par não verifica mais os packages atuais, aceitar o bloqueio até
uma rotação legítima; nunca baixar e confiar automaticamente nem usar
`--allow-untrusted`.

## Corporate handoff — P0-03

Caso o ambiente corporativo exija trust boundary independente da origem
Wolfi, usar repository mirror/proxy controlado que não exponha
`apk-configuration`/JWKS e restringir egress do build à origem aprovada:

```text
Corporate Build → Internal Wolfi Mirror → APKINDEX + packages
                       │
                       └── no apk-configuration/JWKS
Verificação com a chave Wolfi local revisada; egress somente à origem aprovada.
```

Requisito posterior para Cloud/Network/Security, sem tecnologia de mirror
definida nesta spec. Mirror e egress não foram implementados aqui.
Um mirror só remove a discovery se não expuser `apk-configuration`; a
confiança passa então a depender da configuração revisada desse mirror.
Outra opção suportada pelo Apko fixado é resolver contra uma cópia local
(`file://`) do índice, verificada antes somente com a chave fixada, pois
repositórios locais não fazem discovery. Qualquer opção exige desenho
próprio e um ensaio autorizado de chave negativa em repositório isolado;
nenhuma foi implementada.

## Upstream follow-up

Recomendar issue futura em [chainguard-dev/apko](https://github.com/chainguard-dev/apko)
por modo suportado equivalente a `explicit-keys-only`/`--no-key-discovery`:
desativar repository key discovery, preservar signature verification e usar
somente o keyring explícito. Nenhuma issue foi aberta nesta sessão.
