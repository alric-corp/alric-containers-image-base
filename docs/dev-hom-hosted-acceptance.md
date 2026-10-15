# Aceite hospedado DEV → HOM e recovery (G07) — procedimento proposto

**Estado: NÃO EXECUTADO.** `G07_HOSTED_ACCEPTANCE=BLOCKED_BY_PREREQUISITES_AND_AUTHORIZATION`.
O incidente DEV (G01) foi encerrado em 15/10/2026
([registro](dev-hom-promotion.md#incidente-de-dev-stable-de-01102026-encerrado)).
Este procedimento ainda depende dos demais pré-requisitos da seção 8 e de uma
autorização explícita do owner para cada escrita listada. O contrato
do fluxo continua em [DEV → HOM por release](dev-hom-promotion.md); aqui fica
somente o roteiro de aceite e o que conta como prova.

Não valem como prova: run de `promote-stable.yml` com `SUCCESS` enquanto HOM
está desabilitado (o job de promoção é pulado), publicação de imagem no ECR
(tag publicada não é release aprovada), testes locais e os recoveries
históricos de `main` (fluxo anterior, por imagem).

Regressões locais deste roteiro: `tests/unit/pipeline/release/test_lifecycle_acceptance.py`.

## 1. Identidade do código e dos workflows

Registrar antes de começar e conferir em cada run (logs e `GITHUB_SHA`):

- SHA de `develop` integrado, posterior ao encerramento da G01 (que não
  alterou código), e blob de `scripts/pipeline/release/lifecycle.py`;
- `dev-stable.yml`, `promote-stable.yml` e `recover-stable.yml` nesse SHA;
- executor compartilhado pinado nos chamadores e SHA da action Trivy
  (`workflow_dependencies` verifica os dois);
- `policies/pipeline/promote-dev.json` e `promote-hom.json` lidos do mesmo SHA.

## 2. Ambiente e contas

| Item | DEV | HOM |
| --- | --- | --- |
| Conta / região | `712107929769` / `us-east-1` | `248908662184` / `sa-east-1` |
| Role do job | `itau-github-repo-factory-distroless-v1` (central) | `alric-image-base-factory-hom` |
| Release Store | `712107929769-image-base-releases-dev` | `248908662184-image-base-releases-hom` |
| GitHub Environment | `DEV`, somente `develop`, sem revisor | `HOM`, somente `develop`, sem revisor |

Valores de `policies/pipeline/config.json`. A existência e a configuração
atuais da role, do bucket e dos repositórios HOM **não foram verificadas por
esta frente**: o primeiro passo da janela é lê-las (seção 13).

## 3. Configuração DEV/HOM

- `promote-dev.json`: habilitado, soak 0, par `go1-26`/`go1-26-dev`.
- `promote-hom.json`: hoje `enabled=false`, soak 6 h. Habilitar é PR revisado;
  como `policies/**` dispara o build, o merge também gera uma publicação DEV.
- Com HOM habilitado, o cron horário (`17 * * * *`) promove a release elegível
  mais nova. Decisão do owner antes da janela: (a) revisor temporário no
  Environment `HOM`, para aprovar só o run do teste, ou (b) aceitar que o cron
  execute a promoção dentro da janela. Desabilitar ao final é outro PR.
- `infra/lifecycle/configure_github.py` só prepara Environments e não altera a
  proteção de `develop` depois da correção da Frente B; uma versão anterior
  reescreve a proteção e não deve ser executada.

## 4. Manifesto e release elegível

Usar somente uma release produzida por build posterior ao encerramento da
G01 (run `38759851987`, 15/10/2026); a release recuperada, `r38705617503-a1`,
é anterior:

- `releases/<release>/manifest.json` no Store DEV com `state=DEV_STABLE`,
  `dev_readback` igual aos digests das imagens e resultados consumidores das
  duas arquiteturas;
- soak de 6 h contado de `dev_stable_at`;
- par completo: os dois membros na mesma release.

Não usar release histórica cujos bytes não tenham sido relidos na janela.

## 5. Digests de índice e plataformas

Registrar do manifesto, por membro: digest do índice, digests `linux/amd64` e
`linux/arm64`, sujeitos dos três SPDX e tag imutável. Os mesmos valores devem
aparecer no read-back DEV, na cópia HOM, no `stable` HOM e no recibo.

## 6. Retenção e disponibilidade

- ECR DEV: imagens com tag expiram 7 dias após o push, exceto a apontada por
  `stable`. A promoção precisa ocorrer dentro dessa janela; um digest expirado
  bloqueia a cópia (fail-closed), não é pulado.
- ECR HOM: o bootstrap não define lifecycle por idade, para permitir recovery;
  confirmar por leitura que isso continua verdadeiro.
- Recovery exige os bytes do digest no ECR HOM e um re-scan aprovado hoje;
  uma release antiga com CVE nova é bloqueada, e esse bloqueio é resultado
  válido, não falha do teste.
- Artifacts GitHub: evidência de release 30 dias; OCI validado 3 dias.

## 7. Identidades e permissões

Ler, sem alterar: trust da role HOM com subject `…:environment:HOM`, policy
inline `factory-hom`, policy do bucket HOM, leitura do ECR DEV pela role HOM
e ausência de bypass de administrador nos Environments. Nenhuma credencial
humana ou de administrador participa das escritas; o operador só dispara
workflows.

## 8. Pré-requisitos da G01

- Holds de `go1-26` e `go1-26-dev` encerrados pela retomada autorizada da
  Frente A; `stable` DEV igual ao `state/*.json` do Store DEV. Atendido em
  15/10/2026 pelo run `38759851987`, conferido por leitura independente.
- Um manifesto `DEV_STABLE` novo, criado depois da retomada. Pendente: virá da
  primeira promoção automática posterior, que ainda precisa de observação
  independente.
- Health sem o alerta `stable_age_hours` desses membros, ou com causa conhecida.
  Causa conhecida: o proxy lê a promoção HOM e o fluxo anterior, não a
  promoção DEV atual, e o alerta continua enquanto HOM estiver desabilitado
  ([contrato operacional](m11-m04-operational-health.md)).

Sem isso, o aceite não começa.

## 9. Escopo das escritas

| Recurso | Escritas esperadas |
| --- | --- |
| ECR HOM `image-base-go1-26`, `image-base-go1-26-dev` | Tag imutável da release com referrers; tag `stable` |
| Store HOM | `releases/<id>/manifest.json`, `state/<membro>.json`, `events/r<run>-a<attempt>/{started,completed|failed}.json`, `promoted/<id>.json` |
| GitHub | Artifacts `release-hom-<attempt>`, `promotion-batch-<attempt>`, `recovery-<attempt>` |
| DEV | Nenhuma: a promoção só lê o ECR e o Store DEV |

Qualquer escrita fora desta lista interrompe a janela.

## 10. Teste positivo de promoção

1. Dispatch de `promote-stable.yml` com `release=<id>` (sem `resume-automation`).
2. Esperado: `release-outcome.json` com `status=PASS`; `promotion-batch.json`
   com `promoted=true`, read-back `confirmed` e o mesmo digest; no Store HOM,
   `promoted/<id>.json` com o checksum do manifesto e `state` sem hold.
3. Um novo dispatch da mesma release deve ser recusado sem cópia.

## 11. Testes negativos sem adulterar recursos

- Dispatch de release ainda em soak: recusado, sem escrita.
- Dispatch de id inexistente ou malformado: recusado.
- `recover-stable.yml` para release nunca promovida em HOM: recusado.
- Motivo de recovery em branco: recusado na validação.

Falhas de trust, scan, cópia, read-back ambíguo e interrupção abrupta exigem
adulterar ou interromper recursos; ficam nos testes locais ou num ambiente
isolado aprovado, nunca no HOM em uso.

## 12. Recovery de release previamente aprovada

1. Exige duas releases HOM promovidas (A e depois B).
2. Dispatch de `recover-stable.yml` com `release=A` e motivo operacional.
3. Esperado: `stable` HOM igual aos digests de A, `state` com `hold=true` e
   `high_watermark` de B (pausa pós-recovery), evento `completed.json` com
   `action=recovery`; nenhum `promoted/` novo.
4. Retomada: dispatch de `promote-stable.yml` com release explícita igual ou
   mais nova que B e `resume-automation=true`; esperado `PASS` e hold encerrado.

## 13. Verificação independente por leitura

Outra pessoa, com permissão somente de leitura, confere e guarda com hash:

- `aws ecr describe-images` (tag `stable` e tags da release) nos dois repositórios HOM;
- `oras manifest fetch` do índice HOM e dos filhos, comparados ao manifesto;
- `cosign verify-attestation` das SPDX nos sujeitos HOM;
- `aws s3api get-object` de manifesto, `state`, eventos e `promoted/` no Store HOM;
- runs, jobs e artifacts via `gh api`, com SHA, run e tentativa;
- DEV inalterado: `stable` e Store DEV iguais à leitura anterior.

## 14. Critérios de aceite

- Os dois membros promovidos juntos, com índice, filhos e attestations em HOM
  iguais ao manifesto e `stable` HOM confirmado por leitura independente.
- Recovery de uma release aprovada restaura os digests dela e mantém a pausa.
- Nenhum erro produziu `PASS` parcial; toda falha deixou holds e evento `failed`.
- Evidência com commit, workflows, contas, run/tentativa, digests e recibos.

## 15. Interrupção e rollback

Interromper se surgir escrita fora do escopo, divergência de digest, falha de
trust/scan ou qualquer `FAIL`. Não reexecutar às cegas e não editar `state/`
manualmente: inspecionar `events/` e holds, registrar e decidir com o owner.
ECR não oferece transação entre repositórios; um par parcial fica em hold
até a retomada explícita. Rollback é recovery para uma release HOM aprovada
anterior ou manter HOM pausado e desabilitar `promote-hom.json` por PR.

## 16. Modos operacionais

| Aspecto | M1 — promoção sujeita a revisor humano | M2 — promoção automática por cron e policy |
| --- | --- | --- |
| Mecanismo | `promote-hom.json` habilitado e revisor obrigatório no Environment `HOM` (`promote` e `recover` usam esse Environment) | `promote-hom.json` habilitado; o cron `17 * * * *` promove a release elegível mais nova depois do soak de 6 h |
| Quem decide o momento | O revisor aprova o run planejado e rejeita os demais | O scheduler, de melhor esforço |
| Candidato | O operador confere a release antes de aprovar; dispatch com `release=<id>` | A seleção mais nova elegível, que pode mudar se outra release completar o soak |
| Gates técnicos | Todos (manifesto, soak, quarentena, trust, re-scan, cópia, read-back, holds) | Os mesmos |
| Settings | Revisor em `HOM`. No LAB, sem `prevent_self_review` (com ele, quem dispara não aprova e o owner único trava) | Nenhuma |
| Riscos | Aprovação do próprio autor não é segregação de funções; cada run horário que chegar ao job pede aprovação até o fim da janela; esquecer de aprovar só adia (falha segura) | Promoção em horário não controlado; uma release diferente da planejada pode ser promovida; sem ponto humano antes da escrita |
| Saída | Remover o revisor, se o owner não o quiser permanente | Desabilitar `promote-hom.json` por PR |

**Recomendação para a primeira homologação: M1.** Na primeira escrita real em
HOM, controlar o momento e o candidato vale mais que a automação; o revisor
também cobre a recuperação (`recover-stable.yml` usa o mesmo Environment). M2
só depois de um aceite M1 completo e de decisão do owner sobre operação
contínua.

## 17. Monitoramento durante a janela

- Runs de `promote-stable.yml` e `recover-stable.yml`: conclusão e o passo de
  lifecycle (`release-outcome.json` em `release-hom-<attempt>` e `recovery-<attempt>`).
- `promotion-batch-<attempt>`: o health lê esse artifact do job
  `Authorize and promote stable candidates`; com HOM habilitado, o alerta
  `stable_age_hours` passa a refletir as promoções HOM confirmadas.
- Eventos de alerta do health (`alert-events.json`) e, se o destino externo já
  estiver aprovado, as entregas e ACKs correspondentes.
- Leitura pontual do Store HOM (`state/*.json`, `events/`) e das tags `stable`
  no ECR HOM depois de cada operação.

## 18. Falha parcial: diagnóstico e decisão

1. Não reexecutar. Ler `events/r<run>-a<attempt>/` (`started`, `failed`), o
   `state/*.json` dos dois membros (hold e `pending_release`) e as duas tags
   `stable` no ECR HOM.
2. Classificar: falha antes de qualquer escrita (sem hold novo; corrigir a
   causa e repetir o dispatch), escrita parcial (holds nos dois membros) ou
   escrita completa com falha de metadado (holds, `completed` e `failed` no
   mesmo evento).
3. Decidir com o owner: retomar a mesma release com `release=<id>` e
   `resume-automation=true` depois de corrigir a causa, ou recovery para a
   release HOM aprovada anterior. Nunca editar tags ou `state/` à mão.
4. Registrar o diagnóstico, a decisão e o run que reconciliou o par.

## 19. Cobertura do roteiro

| Requisito | Seções | Regressão local (`test_lifecycle_acceptance.py`) |
| --- | --- | --- |
| Pré-requisitos da G01 | 8 | — (operação da Frente A) |
| Environment HOM e revisores | 3, 16 | `test_disabled_hom_promotion_exits_without_touching_the_store` |
| Cron e automação | 3, 16 | `test_resume_requires_an_explicit_manual_dispatch` |
| Candidato autorizado | 4, 5, 10 | `test_missing_dev_approval_is_rejected_before_any_copy`, `test_quarantined_digest_is_rejected_before_copy`, `test_one_corrupted_dev_record_stops_selection_instead_of_splitting`, `test_release_identity_must_be_exact` |
| Read-back | 10, 13 | `test_target_tag_resolving_to_another_digest_blocks_the_release`, `test_persistent_ambiguous_readback_keeps_every_member_held`, `test_readback_failures_are_never_treated_as_no_stable` |
| Estados de hold | 12, 15, 18 | `test_abrupt_interruption_after_one_member_leaves_holds_and_no_pass`, `test_metadata_failure_after_the_tag_writes_re_holds_the_pair`, `test_stable_changed_outside_the_factory_blocks_before_holds_and_writes` |
| Recuperação | 12 | `test_receipt_bound_to_other_content_is_not_a_recovery_target`, `test_expired_bytes_invalid_trust_or_new_vulnerability_block_recovery`, `test_recovery_requires_an_operational_reason`, `test_successful_recovery_keeps_the_post_recovery_pause` |
| Falha parcial e reexecução | 15, 18 | `test_interruption_between_manifest_and_writes_completes_exactly_once`, `test_explicit_rerun_of_a_completed_promotion_is_refused_without_copy`, `test_divergent_hom_manifest_for_the_same_release_is_rejected` |
| Rollback | 15, 18 | `test_successful_recovery_keeps_the_post_recovery_pause` |
| Monitoramento | 17 | `test_failed_gate_never_reports_promotion_to_operational_health` |
| Evidências finais | 13, 14 | — (verificação hospedada por leitura) |
