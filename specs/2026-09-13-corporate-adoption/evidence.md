# EVIDENCE — P0-03

## Baseline e método
Raiz do checkout do repositório alric-containers-image-base. Início em
feat/iam-permission-proposal, HEAD 1620e0170ec4cc8de1758cd737385333a86834eb,
árvore limpa. Origin fetch/push:
https://github.com/alric-corp/alric-containers-image-base.git.

PR #60 lido via gh: MERGED em 2026-09-14T01:41:30Z, base main, merge
3af67d47869b6370f72fcfad1d16cde673cb7f57. Fetch e fast-forward autorizados:
HEAD == main == origin/main == esse merge; commit P1-04 é ancestral.
Nenhum merge de PR, rebase ou descarte executado.

Biblioteca canônica: origin fetch/push
https://github.com/alric-corp/alric-containers-reusable-workflows.git,
main local limpa b574bd487e7c598c12ab6c6e584a523e03caaa45, sem alteração.
Executores efetivamente consumidos: .reusable-workflows no SHA
7a9b055a462eeb8552d3404c26538b44e8ccd83f, limpo.
Instruções persistentes dos dois repositórios lidas.

Leitura local e consulta GitHub do PR; nenhuma coleta operacional ampla,
chamada AWS ou operação corporativa. Relógio observado nesta preparação:
2026-09-14 01:54:13 UTC (13/09, São Paulo). Números de operação anteriores
são apenas referenciados com suas fontes, não apresentados como nova coleta.
Não havia spec/checklist P0-03 canônico; seções corporativas dispersas passam
a apontar a um único pacote, sem substituir seus contratos.

## Fontes e rastreabilidade

O [pacote canônico](../../docs/corporate-adoption.md) liga 20 itens PAR a
arquivos/campos, configuração de origem, entrada/fornecedor corporativos,
forma de ajuste e testes CA. Define sete etapas A–G e 18 critérios de destino,
sem alterar os contratos utilizados como fonte:

- [IAM P1-04](../../docs/iam-permission-contract.md) e
  [propostas](../../policies/aws/proposals/factory-permissions/README.md):
  execution + provisioning, mutabilidade incondicional, limites de stable,
  trust por nome/IDs e ausência de comprovação de autorização efetiva.
- [Consumo](../../docs/consumer-verification-contract.md),
  [ADR-0002](../../docs/adr/0002-sigstore-trust-model.md) e
  [ADR-0003](../../docs/adr/0003-controles-seguranca-workflows-federados.md):
  identidade por índice, três evidências distintas, serviços de transparência
  e decisões externas separadas da autoria dos workflows.
- [Reuso](../../docs/m09-m12-reusable-workflows.md),
  [arquitetura](../../docs/repository-architecture.md) e
  renomeação, conferidos com callers,
  resolvedor e checkout: origem literal, referências internas por SHA,
  permissões aninhadas e acesso privado não resolvido pelo token padrão.
- [Composição](../../docs/image-composition.md), manifesto/receitas/helpers
  de certificados e [Wolfi](../../docs/wolfi-signing-key.md): mecanismos
  existentes não comprovam âncoras corporativas nem trust exclusiva.
- [Operação P1-08](../../docs/m11-m04-operational-health.md), health.json,
  workflows e scripts: retenção, proxies e limites permanecem; nenhum
  emissor externo foi criado e nenhum SLA foi aprovado.

As fontes executáveis específicas constam nas linhas PAR e CA; leitura dos
handoffs e roadmap foi restrita às dependências da adoção, sem copiar material
conceitual ou levantamentos corporativos integrais. Apoio de leitura em
subtarefas não constitui revisão independente nem aprovação desta entrega.

Consultas oficiais complementares, sem operação externa de escrita:

| Fonte | Conclusão usada e limite |
| --- | --- |
| [GitHub: sharing](https://docs.github.com/en/actions/how-tos/reuse-automations/share-with-your-organization), [checkout privado](https://github.com/actions/checkout#checkout-multiple-repos-private), [reuso](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations) | Compartilhamento de Actions/reusables não equivale a acesso Git genérico pelo token do segundo checkout. Settings, visibilidade e viabilidade de forks internos ainda precisam ser confirmados no destino. |
| Trivy 0.72.0: [flags](https://github.com/aquasecurity/trivy/blob/v0.72.0/pkg/flag/db_flags.go), [DB](https://github.com/aquasecurity/trivy/blob/v0.72.0/pkg/db/db.go), [Java DB](https://github.com/aquasecurity/trivy/blob/v0.72.0/pkg/javadb/client.go) | Versão fixada pelos executores: defaults de DB GCR mirror → GHCR. Não usar a versão local de outra ferramenta como prova desses defaults. Dependências documentadas não são tráfego observado nem allowlist completa. |

## Verificação local desta execução

Checks iniciados em 2026-09-14 02:37:36 UTC (13/09 em São Paulo), na baseline
acima com alterações locais desta spec. Nenhuma contagem abaixo foi copiada
de uma revisão anterior. Comandos executados na raiz do checkout:

| Comando | Resultado observado |
| --- | --- |
| `python3 -B -m unittest tests.unit.pipeline.governance.test_consumer_documentation -v` | PASS, 6 testes. Inclusão do pacote e seis documentos em links/caminhos; exemplo Bash validado com bash -n. |
| `make test-unit` | PASS, 323 testes, 5,591 s; os 6 documentais estão incluídos, sem soma adicional. |
| `make test-integration` | Primeira execução: 24 testes, 1 erro de ambiente ao abrir socket local do servidor TLS (`PermissionError: Operation not permitted`). Repetição autorizada fora da restrição do sandbox: PASS, 24 testes, 11,333 s, sem alteração de código. |
| `make lint-local` | PASS; hardening, 52 pins em 49 arquivos, catálogo 17 / uma exclusão do lote automático. |
| `make lint-shared` | PASS; origem/SHA/inputs/hardening e retenção/agendamento em 11 workflows. |
| `make lint-workflows` | PASS; actionlint dos workflows do produto e dos dois executores consumidos. |
| `python3 -B tools/check_ai_context.py` | PASS. |
| `git diff --check` | PASS. |

A extensão documental reutiliza os testes existentes; não adiciona parser,
assert de status dinâmico ou simulação de autorização. Sucesso desses checks
valida estrutura/referências locais, não executa os critérios CA no destino.
O erro inicial de integração não foi tratado como negativo de segurança ou
regressão: a repetição exercitou o mesmo teste TLS com acesso ao socket local.
Não houve novo build de release, coleta de runs/artifacts ou laboratório AWS.

## Arquivos desta entrega

Onze arquivos, quatro existentes e sete novos, sem staging:

- README.md;
- RFC-013-Image-Base-Completa-com-Mermaid.md;
- docs/README.md;
- docs/corporate-adoption.md;
- tests/unit/pipeline/governance/test_consumer_documentation.py;
- specs/2026-09-13-corporate-adoption/spec.md;
- specs/2026-09-13-corporate-adoption/plan.md;
- specs/2026-09-13-corporate-adoption/tasks.md;
- specs/2026-09-13-corporate-adoption/acceptance.md;
- specs/2026-09-13-corporate-adoption/evidence.md;
- specs/2026-09-13-corporate-adoption/handoff.md.

Workflows, scripts de execução, policies/templates IAM, biblioteca, outras
specs e snapshots históricos permanecem inalterados. Não havia trabalho
alheio a preservar. Sem staging/commit/push/PR, AWS ou operações corporativas.

## Limites e aceite

P1-01 mantém o hosted PASS limitado registrado na evidence P1-09 (run
34768459323, e3ed682, go1-26/-dev, confirmed e digests iguais); P1-02/P1-03
continuam PENDING. Não foi coletada nova evidência para encerrá-los.
P1-04 continua com estrutura local validada e validador/simulador/laboratório
AWS NOT RUN, aceite corporativo EXTERNAL_PENDING. P1-08 mantém aceite
operacional incompleto, external_destination=null, envio NOT IMPLEMENTED e
entrega/ACK não comprovados. Nenhum estado de outra spec foi editado.

Todos os testes corporativos CA-01–18 permanecem NOT RUN. Acesso privado,
parâmetros, decisões, recursos, PKI e operação dependem dos responsáveis
autorizados. Os gaps operacionais foram preservados, não corrigidos.
Próxima fatia técnica recomendada: portabilidade da origem da biblioteca
compartilhada, fundamentada nos literais do resolvedor/callers e detalhada
no pacote; não implementada aqui. Revisão independente pelo Claude Code
permanece pendente. Esta evidence não é auto-aprovação ou homologação.
