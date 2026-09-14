# EVIDENCE — origem compartilhada

## Baseline

Produto sandbox alric-corp/alric-containers-image-base. PR identificado pelo
título `docs: add corporate adoption package`, metadados e lista de 11 arquivos:
[#61](https://github.com/alric-corp/alric-containers-image-base/pull/61), MERGED
em 2026-09-14T04:40:52Z, merge 468cfe0fbde719a63bc94d205a4bbda24ed391f1.
Árvore inicial limpa na branch documental, b31338de146ab3b73b5d2111f9e3349a0276e402;
fetch e fast-forward autorizados para main, agora no merge acima.

Biblioteca sandbox alric-corp/alric-containers-reusable-workflows: main limpa
b574bd487e7c598c12ab6c6e584a523e03caaa45; fetch não trouxe avanço.
Remotes fetch/push dos dois checkouts correspondem aos respectivos repositórios
GitHub.com/alric-corp. Checkout consumido .reusable-workflows limpo no SHA
7a9b055a462eeb8552d3404c26538b44e8ccd83f; action setup-trivy no pin distinto
eea2d2f4c4102ded74204e4131c1417f444ae3fc. Nenhum deles foi substituído por main.

## Execução desta fatia

Execução local em 2026-09-14, raiz do checkout do produto. Python 3.9.6 e
actionlint 1.7.12. Nenhuma operação AWS/corporativa, dispatch ou rerun.

### Acoplamentos confirmados

| Ponto | Fonte / comportamento observado |
| --- | --- |
| Aprovação da origem | Antes, constante em `workflow_dependencies.py`; agora [policy versionada](../../policies/governance/reusable-workflows.json), com `schema_version=1` e `repository`. Sem origem inferida do ambiente, remote ou primeiro `uses` |
| Callers obrigatórios | `validate-base-images.yml/validate` → `.github/workflows/validate-apko-images.yml`; `test-runtime-images.yml/runtime` → `.github/workflows/test-runtime-images.yml`; ambos no SHA 7a9b055a462eeb8552d3404c26538b44e8ccd83f |
| Actions locais | Step `Install Trivy` nos jobs `promote-stable.yml/promote` e `recover-stable.yml/recover`; pin eea2d2f4c4102ded74204e4131c1417f444ae3fc |
| Referência interna consumida | `validate-apko-images.yml/validate`, step `Install Trivy`, mesma origem e pin da action. Foi lida na revisão 7a9b055, sem substituir pela main da biblioteca |
| Checkout do produto | `test-promotion.yml`, jobs `test` e `lint-workflows`: CLI `checkout` emite outputs consumidos por `actions/checkout`; path `.reusable-workflows`, `persist-credentials: false` |
| Lints / integração | `shared_workflows()` e `workflow_files()` conferem origem, HEAD, bytes dos dois YAMLs, API de inputs e Trivy; consumidores existentes preservam hardening/retention e contratos |
| Atualizações | `.github/dependabot.yml`, grupo `reusable-container-pipeline`, padrão literal da origem; comparação agora obrigatória no resolvedor |
| Documentação ativa | README, RFC, reuso e arquitetura: linha corrente com origem/SHA conferida pelo teste documental, sem depender de um pin que apareça apenas em snapshot histórico |
| Adaptadores | Os seis arquivos Python em `.github/scripts/` permanecem iguais; integração exercita CLI, códigos de saída e API runtime/supported/project |

O inventário obrigatório é definido por arquivo/job/step, antes de comparar
origens. Pontos extras no namespace aprovado também são rejeitados até sua
inclusão explícita; dependências legítimas de terceiros continuam aceitas.
A biblioteca main e o release consumido têm os mesmos conteúdos relevantes
de workflows/actions/contratos inspecionados, mas são commits distintos.

### Dois falsos PASS antes da correção

Reprodução em fixtures temporárias, antes de substituir o módulo, sem rede nem
alterar referências operacionais. O módulo copiado de b31338de tem os mesmos
bytes do módulo na baseline integrada 468cfe0f: SHA-256
`d15afdd0939c8f16163dedd9932aec4645fc419b0d425ccd902ef910ee1daeec`.

| Caso anterior | Observação |
| --- | --- |
| Controle: dois callers na origem esperada | Dois encontrados; SHAs diferentes rejeitados |
| Um dos dois callers em `fixture-other-owner/fixture-shared` | Somente um encontrado; nenhuma exceção: **FALSE_PASS_REPRODUCED** |
| Controle: três chamadas Trivy na origem esperada | Pins iguais aceitos; pins distintos rejeitados |
| Uma das três actions na origem inesperada | Somente duas reconhecidas; nenhuma exceção: **FALSE_PASS_REPRODUCED** |

O defeito era filtrar pelo prefixo antes de validar, reduzindo silenciosamente
a cobertura. O sucesso do script de reprodução indicou reprodução do defeito,
não aprovação de um controle. As regressões permanentes estão em
[test_workflow_dependencies.py](../../tests/unit/pipeline/governance/test_workflow_dependencies.py),
métodos `test_mixed_caller_origin_reproduced_false_pass_is_now_rejected` e
`test_mixed_tool_origin_reproduced_false_pass_is_now_rejected`.

### Implementação e limites observáveis

- Policy estrita, sem chaves duplicadas, schema desconhecido, URL/expressão ou
  nome inseguro. YAML ambíguo, pontos obrigatórios ausentes e refs malformadas
  falham antes de emitir novos outputs em `checkout`.
- Dois SHAs de reusable devem coincidir; SHA da action é independente, mas
  precisa coincidir entre usos locais e interno. Todos são 40 hexadecimais.
- `checkout` valida configuração local; não baixa a biblioteca. `lint` valida
  o checkout disponível: origem GitHub.com aprovada, HEAD exato e bytes de cada
  workflow consumido contra `git show`, com Git replace objects desabilitados.
  `REUSABLE_WORKFLOWS_PATH` só seleciona diretório.
- URLs de remote são metadados locais. A comparação não comprova que um commit
  foi publicado naquela origem nem atesta todos os arquivos da biblioteca ou
  os bytes da composite no seu SHA separado. Não há nova garantia de acesso
  privado. Erro de execução Git simulado é teste da fronteira, não negativa de
  autorização remota.
- `--root` exercita a CLI com árvores de fixture; o workflow continua chamando
  a configuração versionada do checkout, sem input/secret/var de origem.

Referências `uses` permanecem literais: a [sintaxe oficial do GitHub para
jobs.<job_id>.uses](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_iduses)
não admite contextos/expressões nesse campo (consulta em 2026-09-14). Não foi
introduzido gerador de YAML, mecanismo de autenticação ou host além de GitHub.com.

### Verificação executada nesta implementação

Todos os comandos abaixo concluíram com exit code 0. Contagens são desta
execução, não copiadas de outras specs.

| Comando / escopo | Resultado |
| --- | --- |
| `make test-unit` | **350 PASS**, 15.002 s; inclui os 37 testes do módulo do resolvedor e os seis documentais |
| `make test-integration` | **24 PASS**, 12.202 s; certificados/TLS, contratos do release consumido, seis adaptadores e retenção |
| `make lint-local` | PASS; hardening, 52 pins em 49 arquivos e lote do catálogo |
| `make lint-shared` | PASS; origem/SHA/bytes/inputs/Trivy e políticas existentes de retenção/cron |
| `make lint-workflows` | PASS; actionlint em 11 YAMLs locais/consumidos; nenhum workflow foi editado |
| `python3 -B -m unittest tests.unit.pipeline.governance.test_workflow_dependencies -v` | **37 PASS**, 10.625 s; CLI real e repositórios Git temporários, sem acesso remoto |
| Quatro negativos explícitos, comando abaixo | **4 PASS**, 0.756 s; todos rejeitam a referência divergente |
| `python3 -B -m unittest tests.unit.pipeline.governance.test_consumer_documentation -v` | **6 PASS**; links, identidade/pin corrente e exemplos documentais |
| `python3 -B -m scripts.pipeline.governance.workflow_dependencies checkout` | PASS; saída sandbox e SHA real 7a9b055a462eeb8552d3404c26538b44e8ccd83f |
| `python3 -B tools/check_ai_context.py` | PASS |
| `git diff --check` | PASS; arquivos novos também inspecionados, sem staging |

Execução explícita dos negativos:

```sh
python3 -B -m unittest \
  tests.unit.pipeline.governance.test_workflow_dependencies.DependencyTests.test_mixed_caller_origin_reproduced_false_pass_is_now_rejected \
  tests.unit.pipeline.governance.test_workflow_dependencies.DependencyTests.test_mixed_tool_origin_reproduced_false_pass_is_now_rejected \
  tests.unit.pipeline.governance.test_workflow_dependencies.DependencyTests.test_migrated_origin_rejects_one_caller_left_at_old_origin \
  tests.unit.pipeline.governance.test_workflow_dependencies.DependencyTests.test_migrated_origin_rejects_one_action_left_at_old_origin -v
```

O conjunto adicional cobre origem sintética aprovada até outputs/checkout/lint,
policy ausente/inválida, caller/action interna ausente ou divergente, SHA móvel,
releases distintos, pin próprio da action permitido, Dependabot divergente,
checkout ausente/adulterado/de outra origem, resposta Git inválida, falha Git e
terceiros conformes. A suíte unitária não depende do checkout compartilhado
opcional; a integração valida o release real. Testes específicos não são somados
novamente aos totais completos. Não ocorreu coleta operacional de runs.

### Arquivos da entrega

18 arquivos no produto: 11 modificados e sete novos. Nenhum arquivo na biblioteca.

Modificados:

- `.github/dependabot.yml` (comentários; padrão operacional preservado).
- `CONTRIBUTING.md`.
- `README.md`.
- `RFC-013-Image-Base-Completa-com-Mermaid.md`.
- `docs/corporate-adoption.md`.
- `docs/m09-m12-reusable-workflows.md`.
- `docs/repository-architecture.md`.
- `policies/README.md`.
- `scripts/pipeline/governance/workflow_dependencies.py`.
- `tests/unit/pipeline/governance/test_consumer_documentation.py`.
- `tests/unit/pipeline/governance/test_workflow_dependencies.py`.

Novos: `policies/governance/reusable-workflows.json` e os seis documentos desta
spec (`spec.md`, `plan.md`, `tasks.md`, `acceptance.md`, `evidence.md`, `handoff.md`).
Nenhum snapshot de spec anterior, workflow, adaptador, policy IAM/operacional,
catálogo, scanner ou caminho de signing/provenance/SBOM/release foi alterado.

### Estados separados

| Dimensão | Estado |
| --- | --- |
| LOCAL_IMPLEMENTATION | IMPLEMENTED |
| LOCAL_VERIFICATION | PASS, A01–A08 no escopo local descrito |
| INDEPENDENT_REVIEW | PENDING — Claude Code |
| SHARED_RELEASE_INTEGRATION | Nenhum novo release necessário para o sandbox atual; migração real a outra origem exige release/adopção posterior, NOT RUN |
| HOSTED_ACCEPTANCE | NOT RUN |
| CORPORATE_ACCEPTANCE / acesso privado | EXTERNAL_PENDING / NOT VERIFIED |

Não há auto-aprovação nem conclusão operacional do P0-03. P1-01 continua hosted
PASS limitado aos frameworks/runs anteriores; P1-02/P1-03 permanecem PENDING
(sem trust Wolfi exclusiva). Validações AWS/simulação/laboratório P1-04 NOT RUN,
aceite corporativo EXTERNAL_PENDING; aceite operacional P1-08 pendente; P0-02
e P0-04 não encerrados. A autorização de workflows federados não foi ampliada.

## Reconciliação hospedada — 2026-09-14

Os registros acima são o snapshot da implementação local. Esta seção registra
uma coleta posterior, somente de leitura, ainda sujeita à revisão independente
do encerramento; não atribui ao Claude Code revisão desta nova coleta.

### Integração e revisão efetivamente observadas

Coleta Git/GitHub entre 2026-09-14T14:06:38Z e 2026-09-14T14:11:30Z.
Produto inicialmente limpo na branch `feat/shared-origin-portability`, HEAD
`074fcb834576560de4f75a7bc15b2b9033dd3cae`; fetch/push origin apontam para
`alric-corp/alric-containers-image-base`. Fetch e fast-forward da main levaram
a `8ed8260eba75d4f8b5d856cd1fba37a404a5129a`, igual à origin/main observada.

[PR #62](https://github.com/alric-corp/alric-containers-image-base/pull/62)
MERGED em 2026-09-14T13:57:13Z. Head revisado `074fcb8…`; merge integrado
`8ed8260…`, com pais `468cfe0…` e `074fcb8…`. A aprovação adversarial
**Claude Code — APPROVE** é a informada pelo responsável e registrada no PR.
A API de reviews retornou lista vazia (página 1, per_page=100), e o campo
`reviewDecision` retornou `REVIEW_REQUIRED`, apesar do estado MERGED. Não há
review formal de GitHub a atribuir a um revisor nem mudança de proteções nesta
coleta. Aprovação relatada e integração são fatos distintos.

O PR executou merge de teste `991b784d189924d3a0cd71cb0db9d90cafaa4f99`.
A API Git confirmou seus pais `468cfe0…`/`074fcb8…` e tree
`32da61dfff228b393b078e644fdf4b3e98b039aa`, igual ao tree do head revisado e do
merge integrado. Isso permite interpretar esses runs pelo mesmo conteúdo,
sem tratar o run de PR como execução pós-merge.

### Janela, fontes e cobertura

Janela dirigida: runs criados em 2026-09-14T13:38:00Z–14:06:38Z, ligados ao
PR #62 ou ao commit integrado. Consulta `actions/runs?head_sha=8ed8260…`,
página 1/per_page=100: total 4, todos retornados (fast checks, build e dois
updates Dependabot; estes últimos não usados para aceite). O run de PR foi
identificado nos checks do próprio PR. Não é inventário de todo o histórico.

Para cada fast check abaixo: metadados do run, jobs do attempt 1, página
1/per_page=100, total 2/2; artifacts página 1/per_page=100, total 0/0; ZIP dos
logs do attempt disponível e lido integralmente nos dois jobs. Não houve
página restante, expiração ou falha de acesso nessas consultas. Não exigir
artifact inexistente quando o mecanismo preserva o resultado nos logs.

| Contexto / run | Revisão efetivamente checada | Jobs e resultado |
| --- | --- | --- |
| PR, [34850493723](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34850493723), attempt 1 | API head `074fcb834576560de4f75a7bc15b2b9033dd3cae`; checkout `991b784d189924d3a0cd71cb0db9d90cafaa4f99` (merge de teste) | `lint-workflows` 103996906662 SUCCESS; `test` 103996906678 SUCCESS |
| Main/push, [34852456390](https://github.com/alric-corp/alric-containers-image-base/actions/runs/34852456390), attempt 1 | API/checkout `8ed8260eba75d4f8b5d856cd1fba37a404a5129a` | `lint-workflows` 104003543818 SUCCESS; `test` 104003543517 SUCCESS |

### Critério → evidência operacional

Nos quatro jobs, steps 4, 5 e 6 (`Resolve reviewed reusable workflows`,
`Checkout reusable workflows at the caller SHA`, `Record reusable workflow
commit`) terminaram SUCCESS, nessa ordem. Nos dois jobs lint, actionlint,
hardening/pins e `Shared workflow and retention contracts` também SUCCESS.

Extratos mínimos do job **104003543818 na main**, em UTC:

```text
13:57:21.2892166  checkout do produto: 8ed8260eba75d4f8b5d856cd1fba37a404a5129a
13:57:22.5890710  python3 -B -m scripts.pipeline.governance.workflow_dependencies checkout
13:57:22.7363478  repository: alric-corp/alric-containers-reusable-workflows
13:57:22.7364093  ref: 7a9b055a462eeb8552d3404c26538b44e8ccd83f
13:57:22.7364754  persist-credentials: false
13:57:23.2280298  git log -1: 7a9b055a462eeb8552d3404c26538b44e8ccd83f
13:57:27.9844237  Shared workflow origin, SHA, inputs and hardening verified.
13:57:28.4899840  Retenção e agendamento conferidos em 11 workflow(s).
```

O resolvedor escreve em GITHUB_OUTPUT, sem imprimir seu conteúdo bruto. Os
valores acima são os inputs efetivamente recebidos pelo checkout subsequente;
o YAML dessa revisão liga esses inputs aos outputs `shared.repository/ref`.
Não houve inferência a partir apenas de teste unitário ou nome de diretório.

| Critérios | Cobertura nova e limite |
| --- | --- |
| A01/R1/R2 | Policy da revisão executada, CLI efetivamente chamada e outputs consumidos pelo checkout real na origem sandbox |
| A03/R4, A04/R5, A05 | SHA real conferido; lint da mesma revisão verifica origin, HEAD, bytes dos dois workflows e chamada Trivy interna. Pin da action permanece `eea2d2f4c4102ded74204e4131c1417f444ae3fc`, distinto do reusable |
| A06 | Resolvedor confere grupo Dependabot; teste documental corrente passou dentro dos unitários hospedados |
| A07 | Logs dos quatro jobs mostram Contents: read/Metadata: read e checkout sem credenciais persistidas; integração real exercita contratos/adaptadores |
| A02 e negativos de A03–A06 | Continuam provas de fixture; sua execução num runner GitHub não equivale a migração operacional para outra origem |
| A08 | Contextos PR/main e limites registrados; sem alegar acesso privado ou adoção corporativa |

No job test do PR: 350 unitários/24 integração PASS. No job test da main:
350/24 PASS, incluindo `test_real_callers_match_shared_api_and_tooling` e
contratos de retenção/adaptadores. São resultados **hospedados coletados**, não
novas execuções locais desta reconciliação e não contagens adicionais de aceite.

SHA-256 dos ZIPs coletados: PR
`0efc2c2e72df2ae853d8a5e71a26deb583bd2e3765f4ef0173ec55971495be36`;
main `3af80cfb74a022ea513da1c089034135c2d209a3e856943440867148bc84e92d`.
Hashes identificam os downloads; não substituem verificação de assinatura ou
procedência. ZIPs/logs integrais permanecem fora do repositório.

Correção do finding LOW — 2026-09-14: o hash do ZIP do run 34850493723
(attempt 1) acima foi corrigido após **dois downloads de confirmação**
pelo mesmo endpoint GitHub REST:
`/repos/alric-corp/alric-containers-image-base/actions/runs/34850493723/logs`.
Coletas concluídas em **2026-09-14T15:07:44Z** e **2026-09-14T15:07:45Z**;
ambas retornaram ZIPs de 26.348 bytes com o SHA-256 corrigido acima.
Esta verificação posterior corrige somente a rastreabilidade do ZIP;
os demais hashes, observações dos jobs/steps e estados de aceite permanecem
inalterados. Não foi reaberta a investigação dos runs.

### Estado corrente proposto

**HOSTED_ACCEPTANCE = PASS observado para o caminho operacional na origem
atual do sandbox**, tanto no PR quanto após merge na main. A conclusão desta
coleta ainda requer revisão independente. A implementação já tinha APPROVE;
não transferir essa aprovação automaticamente ao novo encerramento.

Origem alternativa: PASS em fixture; migração real a outra origem: NOT RUN;
acesso privado/interno: NOT VERIFIED; CORPORATE_ACCEPTANCE: EXTERNAL_PENDING.
Nenhum release novo da biblioteca necessário/adotado no sandbox. Biblioteca
canônica e checkout consumido continuam limpos nos SHAs registrados acima.
Falhas de imagens no outro workflow não invalidam o checkout/lint comprovado
aqui; também não são convertidas em publicação ou promoção aprovadas.

### Verificações locais desta reconciliação

Executadas em 14/09/2026, após os adendos documentais:

| Check | Resultado desta sessão |
| --- | --- |
| python3 -B -m unittest tests.unit.pipeline.governance.test_consumer_documentation -v | 6 testes PASS |
| make lint-local | PASS; hardening, 52 pins em 49 arquivos, catálogo/lote |
| python3 -B tools/check_ai_context.py | PASS, validação estrutural offline |
| Links locais dos 14 Markdown alterados e novas âncoras de reconciliação | PASS; usando link_targets existente, sem criar parser/teste novo |
| Preservação histórica | PASS: os nove arquivos anteriores de evidence/acceptance/handoff são prefixos byte a byte dos arquivos acrescidos |
| git diff --check | PASS |

Não se repetiu a suíte completa apenas para obter contagens: os 350/24 acima
são resultados dos runs hospedados identificados, não desta execução local.
As comparações dos reports/índices baixados estão na evidence P1-02; as de
chave/locks estão na evidence P1-03.

Escopo final: 14 Markdown, incluindo os nove adendos nas três specs e cinco
referências ativas; nenhum arquivo novo/untracked ou staged. Main/HEAD/
origin/main observada em `8ed8260eba75d4f8b5d856cd1fba37a404a5129a`.
Biblioteca canônica limpa em `b574bd487e7c598c12ab6c6e584a523e03caaa45`;
checkout consumido limpo em `7a9b055a462eeb8552d3404c26538b44e8ccd83f`;
pin da composite inalterado. Nenhum commit/push/PR ou execução operacional.

Tentativas auxiliares de leitura sem acesso não produziram dados válidos;
foram desconsideradas. As consultas concluídas descritas acima e nas outras
duas specs cobrem os totais/páginas declarados. A investigação não é inventário
fora da janela nem validação de acesso privado.
