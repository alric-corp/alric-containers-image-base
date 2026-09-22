# Contexto mínimo — ativação corporativa DEV

## De onde este pacote parte

Base: análise fornecida pelo usuário sobre `develop` no commit abreviado `2801363`, mais os ajustes da revisão feitos na conversa. Não houve consulta ao repositório nem validação de execução durante a criação deste pacote. Confira a revisão real em M00.

Repositórios informados:

- Produto: `itau-corp/itau-xj7-container-image-base`.
- Executores: `itau-corp/itau-xj7-reusable-containers-products`.

O relatório descreve 13 workflows, 16 variantes e escopo automático V1 restrito a `go1-26`/`go1-26-dev`. Reusables usam SHA imutável. Infraestrutura é delegada ao executor corporativo, com recursos em `infra/ecr/`; não importar state/backend/provider do LAB.

## Destino

`develop` = DEV/default, testes internos e produção de candidates. `staging` = HOM, futuro ambiente final inicial dos usuários. `main` = PROD futuro, inativo. Cada ambiente terá `stable` independente. Este pacote ativa e certifica DEV; não implementa DEV → HOM.

Runners permitidos usam variáveis corporativas, com nomes a confirmar nas Settings:

```text
RUNNER_EKS_OD_1CPU_2GB
RUNNER_EKS_OD_2CPU_4GB
RUNNER_EKS_OD_4CPU_8GB
RUNNER_EKS_OD_8CPU_16GB
```

Exemplo de contrato informado: `runs-on: ${{ vars.RUNNER_EKS_OD_4CPU_8GB }}`. Não usar runner público como fallback. Capacidade e dimensionamento são por job, não por nome do workflow.

## Regras comuns

1. Uma sessão executa um marco. Leia este contexto, o checkpoint em `PROGRESSO.md` e o arquivo do marco; não carregue todos os Markdown, toda a RFC ou todo o histórico.
2. Valores do relatório são baseline, não estado atual. Leia o arquivo/Settings efetivo antes de alterar. Não invente IDs, contas, roles, endpoints ou SHAs.
3. Leitura e alterações locais ficam no escopo autorizado. Push, merge, dispatch, Settings, IAM, apply, publicação e movimentação de stable exigem autorização específica. Apresente uma única proposta completa por fronteira, não uma pergunta por comando de leitura.
4. Respeite o harness e políticas corporativas. Não contorne uma negativa com outro formato de comando, token, transporte ou ferramenta. Não use PAT, segredo estático ou TLS desativado como remendo.
5. Preserve worktrees, alterações de outras sessões, pins e gates. Nada de reset, stash, prune ou exclusão automáticos. Não cancele runs de outros trabalhos.
6. Antes de push/PR, avalie os filtros: uma mudança de workflow ou script pode disparar build caro. Não execute catálogo FULL ou suíte pesada para cada edição documental. Não remova checks exigidos para economizar.
7. Rode testes focados para código alterado. Use evidência existente apenas quando revisão, artefato e escopo coincidirem. `PASS com falhas` não é resultado válido: separe testes do marco e falhas da baseline.
8. Verde com jobs skipped não comprova execução. Diferencie `IMPLEMENTADO`, `TESTADO_LOCAL`, `TESTADO_ARC`, `NÃO_EXECUTADO` e `BLOQUEADO`.
9. Infra pronta não autoriza stable. Preserve o soak vigente, promoção por digest, read-back, trust, scan e identidade do par. Não enfraqueça gates para terminar a sessão.
10. Registre evidências sanitizadas; nunca copie tokens, chaves privadas, state bruto ou planos sensíveis para relatórios públicos. Não prometa monitoramento futuro sem mecanismo aprovado.

## Entrega curta padrão

```text
MARCO = Mxx
STATUS = CONCLUIDO | PARCIAL | BLOQUEADO
BASE_SHA =
WORK_SHA =
ARQUIVOS_ALTERADOS =
TESTES_E_EVIDENCIAS =
EFEITOS_EXTERNOS = NENHUM | DESCREVER
BLOQUEIO_OU_PROXIMA_ACAO =
```

Depois inclua os campos específicos do marco. Guarde logs completos no local aprovado e retorne apenas caminhos/run IDs e trechos necessários. Atualize `PROGRESSO.md` com um checkpoint curto, não outro relatório extenso.
