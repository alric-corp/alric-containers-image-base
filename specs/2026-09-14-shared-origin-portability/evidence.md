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
