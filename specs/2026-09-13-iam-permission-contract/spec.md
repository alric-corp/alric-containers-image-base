# SPEC — P1-04 — Contrato de permissões IAM da fábrica

## Objetivo

Entregar inventário rastreável, exemplos JSON de autorização e plano de
validação para Cloud/IAM, coerentes com a main que incorpora PR #59.
Proposta local revisável não é permissão efetiva nem aplicação na AWS.
A autoria dos workflows federados permanece no [ADR-0003](../../docs/adr/0003-controles-seguranca-workflows-federados.md).

## Requisitos

- R1: preservar baseline, políticas ativas, workflows, executores e trabalho existente.
- R2: cada permissão proposta referencia operação, job/step, ferramenta/API,
  recurso, condições, justificativa e fonte; distinguir código, documentação,
  execução histórica e necessidade ainda não confirmada.
- R3: separar trust, identity, repository e restrições adicionais, além do
  token GitHub. Policies anexadas e permissões efetivas desconhecidas não
  podem ser inferidas dos comandos que funcionaram.
- R4: proposta compatível inclui provisionamento executado pelo publicador,
  isolado dos statements recorrentes. Pré-provisionamento é opção futura
  com pré-requisitos, sem refatorar a pipeline.
- R5: actions explícitas, região/conta/repositórios delimitados, exceção de
  Resource estrela justificada, parâmetros corporativos conhecidos e fixtures
  sintéticas. Nenhum exemplo é carregado pelos workflows ativos.
- R6: explicitar se publisher com PutImage pode mover stable no mesmo recurso;
  não simular condição inexistente por tag Docker nem alegar isolamento.
- R7: trust OIDC atual separado da proposta; documentar claims suportadas,
  presença por caminho e uso trust/sessão. Sem credenciais para PR/fork/shared.
- R8: validação local estrutural com negativos, sem simulador IAM próprio;
  diferenciar validação AWS, simulação, execução sandbox e aceite corporativo.
- R9: plano futuro com alvos isolados, positivos/negativos, evidence e reversão;
  handoff Cloud/IAM identifica parâmetros, dependências e decisões pendentes.

## Restrições e conclusão

Sem aplicação IAM, mudança de trust/sub/Environments, policies ativas ou
recursos AWS; sem dispatch/rerun, notificações, staging/commit/push/PR/merge.
Nenhuma nova infraestrutura, novo controle de release ou encerramento de
outra fatia. P1-01 mantém hosted PASS limitado; P1-02/P1-03 PENDING; P1-08
aceite operacional completo pendente. Revisão posterior pelo Claude Code;
prontidão local não significa autorização aplicada ou homologação.
