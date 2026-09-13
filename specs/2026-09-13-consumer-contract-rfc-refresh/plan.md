# PLAN — P1-09 + P1-10

## Pesquisa
Baseline origin/main e3ed68259f66af41e8054a4c0ac29a54082ddd60 (merge PR #55).
Ler contexto persistente, RFC/README, arquitetura/composição/release, policies,
ADRs, specs/evidence e executores locais/compartilhados fixados. Fontes oficiais
confirmam semântica dos comandos; consultas remotas são somente leitura.

## Estratégia
1. Registrar matriz de controles IMPLEMENTED/PARTIAL/EXTERNAL/DEFERRED com fontes.
2. Criar docs/consumer-verification-contract.md como fonte canônica do consumo.
3. Atualizar incrementalmente RFC e entradas README/docs; preservar históricos.
4. Validar comandos por flags/policies e referências por testes documentais simples.
5. Executar checks exigidos e registrar resultados e limites reais.

## Decisões
A unidade assinada suportada é o índice multiarch, não manifest de plataforma.
Comandos de consumidor não substituem aprovação corporativa, scan ou admission.
Não executar operações autenticadas de consumo/build apenas para validar exemplos.
Evidence existente será datada e identificada; ausência de aceite continua pendente.

## Risco e rollback
O risco é overclaim documental. Confrontar claims com código e distinguir estado
local/hosted/corporativo. Rollback consiste em descartar exclusivamente este diff
documental por revisão; não há efeito em artifacts ou configuração remota.

## Validação
make test-unit; make test-integration; make lint-local; make lint-shared;
make lint-workflows; python3 -B tools/check_ai_context.py; git diff --check.
Acrescentar testes focados em links, paths, identidade e comandos documentados,
sem parser Markdown genérico ou controles novos da pipeline.
