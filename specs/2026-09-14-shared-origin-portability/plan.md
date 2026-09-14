# PLAN — origem compartilhada

1. Confirmar pacote incorporado, baseline limpa e revisões reais dos dois
   repositórios; ler contratos e reproduzir os dois falsos PASS em fixtures.
2. Declarar somente a origem aprovada em policy versionada. Inventariar pontos
   esperados por workflow/job/action independentemente da origem encontrada.
3. Fazer resolvedor/CLI validar origem, pins, Dependabot e ligação do checkout;
   reutilizar Git HEAD/show e checks de inputs/hardening/retention existentes.
4. Testar migração coerente e parcial com repositórios temporários, CLI real,
   outputs e falhas da fronteira Git. Manter terceiros e adaptadores.
5. Atualizar documentação ativa e teste documental; nenhuma alteração de pin
   real ou do checkout consumido. Se necessário, preparar diff compartilhado
   separado; nunca simular release publicado no checkout de validação.
6. Executar checks do produto (e biblioteca somente se alterada), conferir
   escopo, registrar limitações e preparar revisão independente.

Sem gerador YAML, framework de migração ou novo sistema de dependências.
GitHub.com e credenciais existentes delimitam o suporte. Fonte de confiança
e comandos são estáticos/revisados; path local é apenas localização.

## Reversão e integração

A biblioteca canônica não exige alteração para o sandbox atual. Origem e pins
operacionais continuam reais e inalterados. A sequência de release para um
destino futuro está no [handoff](handoff.md); nenhum SHA futuro é antecipado.
Se a revisão rejeitar a mudança, corrigir/reverter somente os arquivos desta
subfatia por diff revisado, preservando trabalho alheio. Não há recurso externo
a reverter nesta sessão. Depois de uma adoção autorizada, eventual retorno deve
alinhar policy, literais, checkout, Dependabot e documentos ao release anterior
revisado e repetir os checks; nunca contornar o validador com override de path.
