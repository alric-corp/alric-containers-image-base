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

## Extensão de laboratório isolado — 2026-09-14

Requisitos locais posteriores aos snapshots acima:

- L1: workflow exclusivo de laboratório, somente dispatch explícito na main
  sandbox e SHA revisado informado igual ao SHA executado; nenhuma chamada
  pela fábrica normal e nenhum input de destino/credenciais.
- L2: produzir go1-26/go1-26-dev e testar amd64/arm64 pelos executores atuais.
  O gate real P1-02 verifica layouts, reports e metadados do mesmo run.
- L3: attempt 1 falha deliberadamente só depois do PASS do gate e upload da
  baseline. Falha anterior de build/scan/contrato não constitui cenário aceito.
- L4: attempt 2 exige selected_attempt=1, reused=true, passed=true; índices,
  manifests e hashes iguais, mesmos artifacts e producers herdados comprovados
  por metadados GitHub e falha anterior especificamente na barreira.
  Rerun completo não deve passar como ausência de rebuild.
- L5: preservar APIs paginadas, jobs/steps/horários, IDs, revisão, workflow ref,
  gate original e comparação. run_attempt de job copiado, ID isolado ou digest
  igual não bastam para provar herança.
- L6: nenhum caminho de AWS, ECR, OIDC, signing, promoção ou recovery neste
  workflow. Nenhum destino configurável; publicação real exigida pelo aceite
  completo anterior permanece fase posterior separada e não implementada.
- L7: retenção vigente: OCI 3 dias; reports/evidência 30 dias. Não mudar
  políticas globais. Expiração, metadados incompletos ou ambíguos falham fechado.
- L8: produção, seis adaptadores, biblioteca, pins e semântica P1-02 intactos.
  Testes locais e integração futura não equivalem a autorização de execução.

O laboratório implementa o ensaio de reutilização anterior à publicação.
P1-02 HOSTED_ACCEPTANCE permanece PENDING até os critérios completos;
EXECUTION_AUTHORIZED=NO nesta sessão.
