# ACCEPTANCE — 2026-09-16: V1 de referência Go 1.26

| ID | Requisito | Critério observável | Comando ou inspeção |
| --- | --- | --- | --- |
| A01 | R1 | Job `promote` de `promote-stable.yml` não executa (schedule ou dispatch) sem `vars.STABLE_PROMOTION_AUTHORIZED == 'true'` | `actionlint`; `gh variable list` (variável ausente); leitura do `if:` no arquivo |
| A02 | R2 | `scripts/verify-image.sh` roda fora do repositório (sem `python3 -B -m scripts...`) e reporta PASS/FAIL para assinatura, SBOM e provenance de um digest real | Execução real: `./scripts/verify-image.sh go1-26 sha256:6582880f… --account 712107929769 --region us-east-1` → `RESULTADO: PASS` |
| A03 | R3 | `pipeline-health` não gera `alert` de `publication_age_hours`/`stable_age_hours` para framework fora de `execution_scope.current`; `default_batch.py lint` continua reportando 17 no catálogo / 1 excluído (inalterado) | `make test-unit` (6 testes novos); `python3 -B -m scripts.pipeline.catalog.default_batch lint` |
| A04 | R4 | Cada um dos 17 itens do catálogo tem causa de bloqueio individual, com evidência (não suposição) e dono classificado | Ver tabela em `evidence.md`; 13 relatórios Trivy baixados e parseados um a um |
| A05 | — | Lista de ECRs necessários para expansão, sem provisionar nenhum nesta rodada | `aws ecr describe-repositories` (só 2 hoje) vs. `frameworks/*.yaml` (17) |

## Negativos e limites

- **A01 negativo:** com a variável ausente (estado real hoje), um
  `workflow_dispatch` manual de `promote-stable.yml` deve ser **recusado**
  pela condição do job, não só pelo cron. Não testado em execução hospedada
  real nesta sessão (exigiria disparar o workflow) — verificado por leitura
  do `if:` e por `actionlint`; teste hospedado do caminho negativo fica como
  item de aceite futuro, não bloqueante para esta spec.
- **A02 negativo:** `tests/integration/scripts/test_verify_image.py` cobre
  falha de assinatura, falha de provenance, digest não resolvido e todos os
  guardas de argumento — com stubs, não rede real. A execução real (A02
  positivo) usou o digest hospedado comprovado
  `sha256:6582880f48e9374df03b241c28242c28772086fef50ebcaf87e03662f95916bc`.
- **A03 negativo:** framework com exceção **e** fora de escopo simultaneamente
  não foi exercitado (nenhum framework real está nos dois hoje); a ordem de
  precedência no código é `out_of_scope` antes de `known` — registrado como
  limite, não como lacuna bloqueante.
- **A04 limite:** a causa exata pela qual `go1-25-dev` resolve `zlib` na
  árvore de dependências e `go1-26-dev` não resolve **não** foi rastreada até
  o pacote Wolfi específico que introduz a diferença — está fora do escopo
  desta spec (ver "Fora do escopo" em `spec.md`); o fato observado (uma
  resolve, a outra não) está confirmado por execução real, só a causa raiz
  de empacotamento upstream não foi perseguida.

## Aceite externo

Nenhum aceite externo é exigido por esta spec especificamente. A revisão do
PR que a implementa segue o fluxo normal do repositório (CODEOWNERS + checks
`test`/`lint-workflows` obrigatórios) — diferente do PR #72 (T01), que foi
mergeado sob urgência operacional real (cron armado) antes da criação
formal desta pasta de spec.
