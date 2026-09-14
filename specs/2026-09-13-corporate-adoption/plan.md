# PLAN — P0-03

## Como implementar
1. Confirmar PR #60 MERGED e avanço fast-forward autorizado em árvore limpa.
2. Ler instruções dos dois repositórios e contratos, specs/handoffs e roadmap
   pertinentes; procurar fonte P0-03 existente antes de criar outra.
3. Inspecionar apenas parâmetros/dependências reais nos callers, verificadores,
   PKI, ferramenta de reuso e operação; classificar ajustes sem implementá-los.
4. Criar docs/corporate-adoption.md como pacote canônico com mapa, papéis,
   sequência A–G, checklist de destino e próximos trabalhos.
5. Acrescentar somente referências no README/RFC/índice e ampliar o módulo
   documental existente para links/caminhos e sintaxe de exemplos.
6. Executar checks locais, registrar resultados reais, conferir diff e
   preservação das áreas proibidas, preparar handoff sem auto-aprovação.

## Escolhas
Tabelas e links reutilizam os mecanismos existentes, sem renderizador geral,
ADR novo, score agregado ou novos IDs de prioridade. IDs do checklist são
referências de aceite, não reordenação do roadmap.
Nenhum teste externo é executado. Não buscar inventário amplo de runs.

## Validação
make test-unit, make test-integration, make lint-local, make lint-shared,
make lint-workflows, módulo documental, check_ai_context e git diff --check.
Os testes documentais fazem parte do total unitário, sem soma duplicada.
