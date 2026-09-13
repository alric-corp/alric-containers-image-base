# PLAN — P1-02

## Baseline e diagnóstico

Origin/main consultada: `285ada4d6948c2d7e7508dd0ba8883c38306c7a1`, merge do
P1-03; árvore inicial limpa. Branch local `feat/partial-retry-without-rebuild`.
Shared efetivamente consumido: `7a9b055a462eeb8552d3404c26538b44e8ccd83f`.

OCI usa `validated-oci-<framework>`, overwrite true após scan. Runtime usa
`runtime-<framework>-<run_attempt>`. Publicador procura somente attempt atual.
Reports já possuem index_digest/manifest_digest e, em compilados, digests do
par -dev; gate atual só compara status. Run/attempt/repository/revisão ainda
não constam nos reports. Código atual confirma o problema histórico.

## Implementação mínima no produto

1. Acrescentar contexto GitHub aos reports no módulo runtime do consumidor;
   o reusable já executa esse código. Não alterar shared ou pins das Actions.
2. Baixar runtime por pattern de suffix numérico no mesmo run/repository, sem
   merge de diretórios e preservando erro de checksum ZIP do download v8.
3. Obter metadados completos de artifacts e jobs desse run por API paginada.
   Isso detecta nomes duplicados, downloads incompletos e producer falho que
   não chegou a escrever reports, sem usar resultado agregado de outro framework.
4. Implementar seleção offline no domínio runtime: validar metadados,
   layouts flat (um match v8) e por artifact (múltiplos), JSONs e identidades;
   comparar índices/manifests com OCI atual verificado; ordenar attempts como int.
5. Para contratos compilados, baixar também o OCI validado atual do par -dev
   e conferir seus digests. É leitura/verificação adicional, não rebuild.
6. Gate guarda runtime-gate-result.json, incluindo artifact ID/nome/attempt,
   run corrente e digests. Publicação preserva esse resultado com suas evidências.
7. Testar domínio/CLI sem GitHub/AWS/Docker, incluindo limite de run, conflitos,
   falhas de jobs sem artifact, paginação e ausência. Repetir checks exigidos.

## Política de seleção

API deve estar completa e sem IDs/nomes ambíguos. Cada artifact relevante
precisa ter os dois reports completos e identidades coerentes. Erro de
estrutura/JSON/digest ausente falha fechado, inclusive em histórico disponível;
não ignorar corrupção para encontrar um PASS. Isso pode exigir um novo run
quando o histórico é inválido. Pares bem formados para outros digests não
são candidatos. Do conjunto que corresponde ao índice e ao par -dev atuais,
selecionar o maior attempt; exigir ambos status passed.

O job producer mais recente por framework deve ter concluído success. GitHub
pode copiar job success para um attempt maior sem executá-lo novamente;
timestamps/steps históricos R03 confirmam isso. Não exigir report daquele
attempt artificialmente. Job falho/cancelado/incompleto ou ambíguo bloqueia.

## Risco e rollback

Consulta/API/download inconclusivos bloqueiam publicação. Overwrite mantém
somente o OCI aprovado atual; não escolher report só por nome. API e padrão
do nome do producer são contratos do reusable fixado e devem ser retestados
quando esse pin mudar. Download do par -dev acrescenta IO aos contratos
compilados. Rollback deve preservar falha fechada e não reintroduzir gate
baseado só em status nem reconstrução automática no publicador.

## Hosted acceptance

Após revisão/merge, preferir falha transitória legítima depois de contrato
aprovado. Alternativa controlada: workflow de aceite isolado, revisado antes
de adicionar, com barreira determinística de attempt1 antes de escrita externa;
no attempt2 reexecutar somente jobs falhos e copiar a um destino de teste
autorizado mantendo verificação de digest. Não alterar IAM, provocar falha
de assinatura após publicação produtiva nem mover stable para testar.
Registrar run/attempts, jobs/timestamps, IDs de artifacts, digests, gate e
continuação de publicação. Não criar/acionar esse workflow nesta entrega.
