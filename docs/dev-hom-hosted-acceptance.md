# Aceite hospedado DEV → HOM e recovery (G07) — procedimento proposto

**Estado: NÃO EXECUTADO.** `G07_HOSTED_ACCEPTANCE=BLOCKED_BY_G01_AND_AUTHORIZATION`.
Este procedimento só pode rodar depois do encerramento do incidente DEV (G01)
e de uma autorização explícita do owner para cada escrita listada. O contrato
do fluxo continua em [DEV → HOM por release](dev-hom-promotion.md); aqui fica
somente o roteiro de aceite e o que conta como prova.

Não valem como prova: run de `promote-stable.yml` com `SUCCESS` enquanto HOM
está desabilitado (o job de promoção é pulado), publicação de imagem no ECR
(tag publicada não é release aprovada), testes locais e os recoveries
históricos de `main` (fluxo anterior, por imagem).

Regressões locais deste roteiro: `tests/unit/pipeline/release/test_lifecycle_acceptance.py`.

## 1. Identidade do código e dos workflows

Registrar antes de começar e conferir em cada run (logs e `GITHUB_SHA`):

- SHA de `develop` integrado (contendo a correção da G01) e blob de
  `scripts/pipeline/release/lifecycle.py`;
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

Usar somente uma release produzida depois do encerramento da G01:

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
  Frente A; `stable` DEV igual ao `state/*.json` do Store DEV.
- Um manifesto `DEV_STABLE` novo, criado depois da retomada.
- Health sem o alerta `stable_age_hours` desses membros, ou com causa conhecida.

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
