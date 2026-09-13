# SPEC — P1-09 + P1-10: Consumer Verification Contract + RFC Current State

## Objetivo
Um consumidor deve distinguir ponteiro stable, tag de build imutável e OCI index
digest, e verificar a origem do artifact conforme os mecanismos atuais. A RFC
representa a main observada, separando implementação, evidence e implantação corporativa.

## Requisitos
- R1: reconciliar controles e drift com workflows, scripts, policies e evidence da main.
- R2: definir níveis convenience, reproducible deployment e audited/verified consumption.
- R3: assinatura, provenance e SBOM usam a identidade concreta atual e o mesmo índice OCI.
- R4: distinguir disponibilidade de evidence de enforcement no consumo/runtime.
- R5: explicar P1-01 read-back pontual, P1-02 retry sem rebuild e P1-03 defense-in-depth.
- R6: separar sandbox de aceites corporativos externos, sem atribuir SLSA level formal.
- R7: documentação navegável com comandos e referências coerentes com fontes executáveis.

## Restrições e invariantes
Somente documentação, specs e testes documentais. Nenhuma mudança em workflows,
scripts de produção, catálogo, policies ou controles. Sem commit, push ou PR.
Revisão independente posterior pelo Opus 5 MAX; não há auto-aprovação.
A aprovação local de P1-01/02/03 não implica hosted PASS.

## Fora do escopo
Novos gates, IAM, PKI, mirror, Sigstore/scanner ADR, Renovate, watchdog,
Policy Controller, VEX, native ARM e workaround de zlib.

## Dependências
Cloud/Network/Security/AppSec e Containers Products precisam decidir e executar
os aceites corporativos; isso não impede entregar o contrato documental local.
Ver [acceptance.md](acceptance.md).
