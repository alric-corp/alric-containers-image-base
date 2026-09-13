# PLAN — P1-08

1. Confirmar origem sandbox, árvore limpa, merge PR #58 e atualizar main
   somente por fast-forward. Ler contexto, roadmap e fontes operacionais.
2. Reconstruir health/pins/resumos/timing e testes; usar pesquisa auxiliar
   somente leitura. Consultar primeiro snapshots locais e depois uma janela
   explícita de runs/jobs/artifacts sandbox, com paginação e coleta datada.
3. Ampliar o documento canônico M11/M04: corrigir interpretações correntes,
   manter snapshots históricos identificados, definir indicadores, proposta
   de metas, matriz, runbook e plano futuro de validação de alertas.
4. Acrescentar referências incrementais no README/RFC/índice documental.
   Estender validação de links existente para documento/spec; comandos
   somente leitura e referências verificáveis, sem parser Markdown genérico.
5. Executar unit/integration, três lints, suite documental, check_ai_context
   e diff --check. Registrar resultados e pendências, sem Git remoto.

## Riscos e rollback

Risco principal é chamar proxy de disponibilidade/entrega ou transformar
limite técnico em SLA. Mitigar explicitando campos e limites de cada fonte,
sem corrigir implementação nesta fatia. Rollback restrito a documentação e
teste documental. Histórico/ADRs/specs anteriores não são reescritos.
