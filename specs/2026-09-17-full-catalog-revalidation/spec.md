# SPEC — 2026-09-17 full-catalog-revalidation

## Objetivo

Revalidar as 17 definições do catálogo contra pacotes Wolfi atuais, Trivy
atual e advisory DB atual, usando o mecanismo real da fábrica (apko/melange
via `validate-base-images.yml`), para confirmar ou refutar a investigação do
[ADR-0006](../../docs/adr/0006-java21-zlib-blocker-remediation-options.md):
que `CVE-2026-85091` (zlib) deixou de bloquear o catálogo porque o Wolfi
publicou `zlib 1.3.2.1_rc20260601-r0` a partir do commit upstream
`e3dc0a85b7032e98380dec011bc8f2c2ee0d8fca` já identificado naquele ADR.

Resultado observável: uma matriz atual (build amd64/arm64, Trivy amd64/arm64,
contrato funcional, versão de zlib resolvida, CVE bloqueante) para as 17
definições, amarrada a um run real de CI, sem publicar nem promover nada.

## Requisitos

- R1: usar o mecanismo real da fábrica (apko/melange), não rootfs sintético,
  para as 16 definições fora de `dotnet8`.
- R2: não alterar framework YAML, severity gate, ignore policy, configuração
  do scanner, base distro (Wolfi→Alpine), execution_scope ou default batch.
- R3: não publicar candidate, não promover stable, não alterar ECR.
- R4: registrar Trivy version e o estado do advisory DB (não apenas
  PASS/FAIL) — `SCAN_VERDICT = f(image digest, scanner version, advisory DB
  state)`.
- R5: para `dotnet8` (fora de todos os lotes por
  [ADR-0001](../../docs/adr/0001-dotnet8-fora-do-lote-padrao.md)), produzir
  evidência sem reintroduzi-lo em nenhum lote.
- R6: atualizar ADR-0006 e a matriz do catálogo vigente sem apagar histórico
  nem duplicar estrutura de evidência já existente.

## Restrições e invariantes

- `SECURITY_GATE_RELAXED = NO` durante toda a investigação.
- Nenhum pacote Melange próprio (zlib) é criado nesta rodada.
- Nenhuma migração de framework para Alpine nesta rodada.
- O mecanismo de trigger (PR descartável) não deve alterar comportamento do
  produto — ver [evidence.md](evidence.md) para a justificativa da mudança
  comment-only usada para rotear o profile `FULL`.

## Fora do escopo

- Corrigir `dotnet8` (permanece [ADR-0001](../../docs/adr/0001-dotnet8-fora-do-lote-padrao.md)).
- Implementar captura de `Trivy DB UpdatedAt/DownloadedAt` no mecanismo de
  evidence do reusable workflow (`alric-containers-reusable-workflows`) — é
  uma mudança de pipeline revisada em outro repositório, fora do "sem
  alterar o produto" desta rodada; registrado como recomendação em
  [evidence.md](evidence.md).
- Rollout, arquitetura de repositórios e política de versões suportadas —
  decisões do Tech Lead subsequentes a este resultado, não desta spec.

## Dependências

Nenhuma: mecanismo, permissões (`gh` autenticado com `repo`+`workflow`) e
acesso ao Docker/CI já disponíveis nesta sessão.

## Conclusão

Ver [acceptance.md](acceptance.md) e [evidence.md](evidence.md).
