# HANDOFF — P1-04

Baseline main `dd037cc9a8dc2b3585d9941666ba508ecca87c9a`, PR #59 integrado.
Objetivo e critérios em [spec](spec.md) e [acceptance](acceptance.md).
Proposta local implementada e verificada, sem IAM aplicado e sem auto-aprovação.

Revisão independente posterior pelo Claude Code. Não aplicar exemplos,
alterar trust/pipeline, conceder novas permissões, executar sandbox ou
criar commit/push/PR sob a autorização desta sessão.

## Entrega

- [Contrato canônico](../../docs/iam-permission-contract.md): inventário por
  operação, camadas, OIDC, limite stable e pedido técnico para Cloud/IAM.
- [Proposals](../../policies/aws/proposals/factory-permissions/README.md):
  três templates, fixture sintética e inventário testado (18 operações).
- [Renderizador](../../tools/render_iam_proposal.py): somente local; não aplica
  IAM nem escreve no checkout. Templates brutos contêm placeholders.
- [Evidence](evidence.md): fontes oficiais, versões, históricos e checks desta
  execução; 323 unitários (23 específicos e seis documentais incluídos),
  24 integração, três lints, contexto e diff PASS.

## Pontos que a revisão deve preservar

1. Profile compatível inclui execution + provisioning; CreateRepository é
   condicional, PutImageTagMutability é incondicional. Pré-provisionar não
   permite remover este último grant sem mudar o publicador posteriormente.
2. Publisher com PutImage no mesmo repo pode mover stable. A exceção de
   mutabilidade não isola principal; não há condition key IAM image tag.
3. ListImageReferrers é API mapeada a BatchGetImage, não action IAM própria.
4. AWS aceita claims GitHub extras na trust; somente aud/sub do conjunto
   documentado permanecem disponíveis na sessão. Proposta adiciona repo/IDs/ref,
   sem impor job_workflow_ref nos caminhos diretos. Recovery depende da
   trust para negar ref indevida; não tem guard main no job.
5. Policy anexada/inline, restrições adicionais e JWTs atuais não foram
   coletados. A proposta não é reconstrução das permissões efetivas.
6. Testes offline não são simulador IAM nem evidência de autorização real.

## Próxima etapa externa, sem execução agora

Cloud/IAM fornece parâmetros reais, lista de recursos, policies adicionais
e decisão sobre provisionamento/risco residual. Segurança avalia escopo;
GitHub admins confirmam IDs/claims/ref. Containers Products mantém inventário
e executores, conforme ADR-0003, sem migrar obrigatoriamente workflows.

Após revisão e nova autorização: validar JSON no Access Analyzer, simular
casos pertinentes e executar laboratório isolado, com role/repos distintos
da fábrica, negativos reais e evidence sanitizada. Procedimento, casos e
reversão estão no contrato. Não conceder grants para o observador à role
da fábrica e não usar stable corrente para negativos.

AWS_VALIDATOR_CHECKED, AWS_SIMULATION_CHECKED e SANDBOX_EXECUTION_VERIFIED:
NOT RUN. CORPORATE_ACCEPTED: EXTERNAL_PENDING. Somente
LOCAL_STRUCTURE_VALIDATED: PASS. IAM alimenta P0-03, não inicia seu checklist
integral. Aceites P1-01 limitado/P1-02/P1-03/P1-08 permanecem como na baseline.
Árvore deixada na main, com alterações locais não staged para revisão.
