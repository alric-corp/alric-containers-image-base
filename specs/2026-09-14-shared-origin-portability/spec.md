# SPEC — P0-03: portabilidade da origem compartilhada

## Objetivo

Permitir configurar uma origem GitHub.com explicitamente aprovada para a
biblioteca, sem aceitar migração parcial, referência móvel ou checkout
divergente. É subfatia técnica do [pacote de adoção](../../docs/corporate-adoption.md),
sem reescrever a spec documental ou encerrar o P0-03 operacional.

## Propriedades obrigatórias

- R1 — Origem esperada em declaração versionada e revisável, validada antes
  de produzir comandos/URLs/outputs; não inferir de ambiente, uses ou remote.
- R2 — Literais GitHub de callers/actions e checkout coerentes com a origem.
- R3 — Inventário de pontos obrigatórios independente do prefixo encontrado;
  ausência, origem inesperada ou formato inválido falham sem reduzir cobertura.
  Dependências legítimas de terceiros permanecem fora dessa identidade.
- R4 — SHA completo; reusables e checkout usam um release comum; action tem
  pin próprio, consistente nos usos locais e internos do release consumido.
- R5 — Checkout com identidade/origem, revisão e bytes verificados. Override
  de diretório não aprova outra origem/revisão/conteúdo; falhas não têm fallback.
- R6 — Dependabot, documentação ativa de origem/pins e testes correspondentes
  acompanham a declaração; snapshots históricos ficam preservados.
- R7 — Seis adaptadores, APIs, artifacts, permissões e identidade de signing
  preservados; sem nova credencial, autenticação ou secrets herdados.

## Limites

Origem operacional sandbox e pins reais permanecem. Origem alternativa só
em fixtures locais. Suporte a GitHub.com; sem GHES, novos runners ou mecanismo
de acesso privado. Acesso privado corporativo é EXTERNAL_PENDING. Configuração
local não prova acesso remoto nem aprovação de execução corporativa.

Não modificar IAM, imagens, scanner/versão, PKI/Wolfi, assinatura/provenance,
SBOM, seleção/retry/recovery, health ou proteções. Sem staging, commit, push,
PR, merge de PR, AWS, dispatch/rerun ou operação corporativa nesta sessão.
Fixtures podem criar repositórios Git temporários para testar commits reais.

## Aceite e revisão

Critérios em [acceptance.md](acceptance.md). Revisão independente posterior
pelo Claude Code; testes locais não são auto-aprovação. Separar implementação,
verificação, revisão, integração de release, hosted e corporate acceptance.
