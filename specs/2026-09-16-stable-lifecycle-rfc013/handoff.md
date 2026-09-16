# HANDOFF — 2026-09-16: `stable` + lifecycle de 7 dias

- Repositórios: `alric-corp/alric-containers-image-base` (preflight,
  binding, ADR-0005) e `alric-corp/alric-containers-registry` (Terraform:
  mutability exclusion, lifecycle policy).
- Objetivo e pasta da spec: `specs/2026-09-16-stable-lifecycle-rfc013/`.
- Estado do diff: ver PRs abertos nesta sessão em cada repositório.
- Tasks concluídas: T01–T04 (código + testes + docs). T05–T10 (execução
  real) pendentes no momento da escrita deste arquivo — ver `tasks.md`.
- Verificações e resultados: ver `evidence.md`.
- Decisões e hipóteses pendentes: nenhuma bloqueia o código; a execução
  real (T05–T10) depende só da revisão dos PRs e da disponibilidade para
  rodar os workflows de Infra/promoção.
- Dependências/autorizações ainda necessárias: revisão de CODEOWNERS nos
  dois PRs antes do merge; nenhuma decisão externa nova além do que já
  estava aprovado (RFC-013 sempre descreveu `stable` e lifecycle de 7 dias
  como o modelo pretendido).
- Próximo passo: mergear os dois PRs, executar T05 (reconciliação
  one-time), depois T06–T10 em sequência, registrando cada resultado em
  `evidence.md`.

Confirme o estado real do Git antes de continuar.
