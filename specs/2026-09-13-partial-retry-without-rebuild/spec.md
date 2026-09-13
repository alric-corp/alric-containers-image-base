# SPEC — P1-02 Partial Retry Without Rebuild

## Propriedade

Uma publicação reexecutada pode reutilizar contrato funcional aprovado de
attempt anterior do mesmo workflow run, somente para o mesmo índice OCI
validado que será publicado. Reexecutar publicação não reconstrói, reempacota
nem resolve uma nova imagem base.

## Requisitos

- R1: a fronteira é repository + run_id. run_attempt identifica tentativas
  dentro dessa fronteira, não uma nova execução independente.
- R2: relatórios de amd64/arm64 pertencem ao mesmo artifact/attempt/framework,
  registram run_id, run_attempt, repository e revisão do producer e concordam
  sobre os digests do índice e manifests efetivamente verificados. Para
  contratos compilados, o par -dev atual também precisa corresponder.
- R3: selecionar numericamente o maior attempt disponível cujo conjunto de
  digests corresponde ao candidato atual. Só aprovar se ambos reports passaram.
- R4: ausência, corrupção, formato inválido, identidade divergente, duplicação
  ambígua ou conflito dentro de um artifact falham. Não misturar plataformas
  de attempts distintos nem aceitar JSON que só declare status passed.
- R5: falha do producer mais recente deste framework bloqueia, mesmo quando
  falhou antes de criar novo report. Success herdado entre attempts permite
  reutilizar o report anterior; não exigir igualdade entre attempt do job
  herdado e attempt do artifact.
- R6: não esconder falha mais recente para o mesmo candidato buscando um PASS
  antigo. Reports válidos de candidatos anteriores podem ser descartados por
  digest; evidência malformada/ambígua não vira aprovação por fallback.
- R7: preservar scan, cobertura funcional planejada, gate de trust, publicação
  por digest, Cosign, provenance, SBOM, stable promotion/read-back e isolamento
  de frameworks M13. Skips de cobertura existentes continuam explícitos.
- R8: guardar a decisão do gate, artifact/attempt escolhidos e digests junto
  à evidência de publicação. Hosted acceptance só passa após rerun real.

## Limites

Reuso exige artifacts não expirados e APIs/downloads disponíveis. Relatórios
legados sem identidade obrigatória falham; não serão migrados por heurística.
Run_id registrado é o run produtor do relatório, não o input opcional
artifact-run-id do dispatch diagnóstico. Esse dispatch não publica em outro run.
Integridade do ZIP GitHub e integridade OCI são controles diferentes.

## Fora do escopo

Wolfi key, IAM/OIDC, Veracode, Sigstore ADR, mirror, Renovate, zlib workaround,
VEX, admission, runner ARM nativo e RFC ampla. Sem commit, push, PR ou
auto-aprovação; revisão independente posterior pelo Opus 5 MAX.

## Aceite

[acceptance.md](acceptance.md) define casos; [plan.md](plan.md) descreve meios.
HOSTED ACCEPTANCE = NOT RUN até executar o plano hospedado registrado.
