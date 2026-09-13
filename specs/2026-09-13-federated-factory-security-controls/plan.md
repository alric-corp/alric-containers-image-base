# PLAN — P1-06

## Pesquisa

Ler contexto persistente, RFC, ADRs/specs, contrato de consumo, scripts de
scan/OCI/release/runtime, workflows locais e shared no SHA consumido,
policies de saúde/release e evidence. Examinar os dois levantamentos locais
somente para síntese de interfaces/perguntas, sem copiar material restrito.

## Estratégia

1. Conferir baseline e ausência de spec/ADR P1-06 equivalente.
2. Criar ADR-0003 como fonte canônica da premissa e decisões externas.
3. Documentar controles, scanner, responsabilidades, evidências/interfaces
   condicionais e perguntas para segunda-feira.
4. Acrescentar referências curtas na RFC, índices, mapa do projeto e
   documentação de reuso/consumo; qualificar a direção histórica de migração
   para Veracode como hipótese anterior, preservando o registro original.
5. Estender o check de links documental existente para ADR/spec. Executar
   unit/integration, lints, check_ai_context, suite documental e diff --check.

## Decisões

Não criar uma segunda spec ou auditoria se já existir equivalente. Não
pesquisar produtos para escolher scanner nesta fatia: a decisão de
aplicabilidade é externa. A configuração técnica local é a evidência do
produto; relatos corporativos não comprovam sua configuração vigente.

## Riscos e rollback

Riscos: inferir dispensa corporativa, importar gate de outra esteira, atribuir
manutenção a Pipelines ou divulgar dados internos. Mitigar com categorias,
fontes e limites explícitos. Rollback restrito a documentos/teste documental.
Nenhuma infraestrutura ou pipeline muda com esta entrega.
