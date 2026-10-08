# Projeção offline de inventário SPDX

Este núcleo lê os três SPDXs já gerados para cada imagem da Factory, confere
seus subjects contra contexto externo e produz dois datasets Parquet locais.
Ele preserva os bytes originais e permite pesquisar componentes reportados.
Não é custódia HGC-04, autenticação do produtor, verificação de vulnerabilidade,
inventário de aplicações consumidoras ou autoridade de publicação/promoção.

## Entrada e vínculo

Execute a partir da raiz do consumer, com as dependências fixadas em
`requirements-dev.txt` instaladas em ambiente virtual:

```sh
python -B -m scripts.pipeline.analytics.normalize \
  --input /scratch/input/context.json --output /scratch/analytics
```

O JSON de entrada tem `schema_version: 1`, `origin` e `images`. Campos
desconhecidos nessa configuração são recusados. Caminhos locais são relativos
ao arquivo de contexto ou absolutos; não há aquisição GitHub, cliente cloud,
execução de artifacts ou download de layers. O diretório de saída deve ser
privado e controlado pelo chamador.

`origin` exige `repository`, `run_id`, `run_attempt`, `source_sha`, `event` e
`ref`. IDs são inteiros positivos de 64 bits e SHA de fonte tem 40 caracteres
hexadecimais minúsculos. `source_timestamp` é opcional e exige a descrição
externa `source_timestamp_origin`; a representação e seu offset são mantidos.
`spdx_created` vem separadamente de `creationInfo.created` do documento.
Nenhum horário é inventado usando a hora de processamento.

Cada elemento de `images` exige:

- `framework`: nome do framework, sem dependência de catálogo ou dos nomes Go.
- `image_repository`, `image_index_digest` e `platforms`: identidade externa
  esperada, com digests SHA-256 distintos para índice, `linux/amd64` e `linux/arm64`.
- `documents`: exatamente um índice e um documento para cada plataforma do
  contrato atual. Cada item tem `path`, `sbom_scope` (`index` ou `platform`) e
  `document_platform` (`null`, `linux/amd64` ou `linux/arm64`). Pode também ter
  `sha256` esperado dos bytes, `artifact_id` e `source_path` original.

Exemplo de um item de documento:

```json
{
  "path": "go1-26/sbom-x86_64.spdx.json",
  "sbom_scope": "platform",
  "document_platform": "linux/amd64",
  "sha256": "30487d1481bcfaa01fed56df9d95bb4e4b24fb13c145983eafaf5dd05393a8c6",
  "artifact_id": 11562328737,
  "source_path": "sbom/sbom-x86_64.spdx.json"
}
```

As expectativas devem vir do chamador, não do próprio SPDX. O perfil admite
`pull_request`, preservando `refs/pull/...`; não o normaliza para `develop`
nem infere release publicada ou stable. `push`, `schedule` e
`workflow_dispatch` requerem uma ref de branch/tag consistente. Essa checagem
é de consistência do contexto fornecido, não de autenticidade da API GitHub.

Três documentos opcionais por imagem permitem conferir vínculos existentes:

| Campo | Entrada | Conferência local |
| --- | --- | --- |
| `validation` | `path`, `reference` | Digest do índice, mapa de plataformas e os três registros `sboms` do OCI validado |
| `publication` | `path`, `remote_index_path`, `reference` | Digests copiado/remoto, bytes do índice publicado e plataformas |
| `candidate_identity` | `path`, `reference` | Run, attempt, source SHA e índice |

Esses JSONs e o índice remoto local são preservados com seus bytes originais.
A referência é proveniência declarada pelo chamador. Não se modifica
`candidate.json`, `manifest.json` v1 ou qualquer Store da Factory. O código
reutiliza, sem alterar, `oci_artifact.sboms`, `verify_publication` e o checksum
canônico de `release_manifest`. Não exige o layout OCI completo. O checksum
canônico (`predicate_digest`) é distinto de `sbom_sha256`, que identifica os
bytes originais, inclusive whitespace.

`hosted_verification` pode registrar `status` (`NOT_PROVIDED`,
`REPORTED_SUCCESS` ou `REPORTED_FAILURE`) e `reference`. É somente resultado
reportado. Os checks de vínculos usam `MATCHED`/`NOT_PROVIDED`; o hash usa
`MATCHED_EXTERNAL_SHA256` ou `SHA256_COMPUTED`. Todas as observações mantêm
`cryptographic_authenticity = NOT_REVALIDATED` e `publication_authority = false`.
Não há revalidação offline de assinatura Cosign/Sigstore nesta operação.

## Documentos e pacotes

O parser aceita o perfil Factory `SPDX-2.3`, com namespace URI,
`SPDXRef-DOCUMENT` e um único pacote `documentDescribes`, cujo checksum
SHA256 deve corresponder ao subject externo esperado. IDs de pacotes são
únicos dentro do documento. Relationships `DESCRIBES`/`DESCRIBED_BY` que
contradigam essa raiz são recusados. O helper existente da Factory confere
novamente os três subjects usando os nomes canônicos dos arquivos.

Não se trata de um validador completo da especificação SPDX. Os campos usados
pela projeção são validados; outros permanecem nos bytes raw. Relationships
são preservados no original, com contagem na observação. Não se deduz
dependência direta/transitiva pela ordem de `packages[]`, nem arquitetura
do componente a partir da plataforma do documento.

Nome, versão, expressões e valores especiais de licença (`NONE`,
`NOASSERTION`), supplier e download location são copiados sem trim, mudança
de caixa, normalização Unicode ou conclusão jurídica. Ausência é `null`.
`externalRefs` ausente produz arrays `null`; presente e vazio produz `[]`.
Todas as referências externas são mantidas em um array de structs, e todos
os PURLs explicitamente declarados ficam em um array. Não se fabrica PURL
nem se expande uma linha em um produto cartesiano de referências.

## Schema, identidade e repetição

O contrato de colunas/tipos/nullability está em
[`schemas/sbom-analytics/v1.json`](../schemas/sbom-analytics/v1.json), com
`schema_version = 1` e `normalizer_version = 1.0.0`. O mapeamento puro de SPDX
fica separado da escrita Parquet.

`sbom_observations` tem uma linha por documento e contexto completo de
execução/framework/subject/proveniência. `observation_id` é SHA-256 do registro
canônico sem o próprio ID. Contextos distintos, inclusive runs/attempts e
referências de aquisição diferentes, permanecem distinguíveis. Caminho local
de preparação, ordem dos inputs e horário da execução não entram no ID.
`documentNamespace` não é chave: os seis documentos históricos usam o mesmo
namespace apko. Um subject também pode ter documentos diferentes.

`sbom_packages` usa a chave `(sbom_sha256, package_spdx_id)` dentro da versão
do normalizador. Nome/versão iguais não colapsam pacotes distintos. Linhas de
pacotes são compartilhadas entre observações do mesmo documento; documentos
com bytes diferentes mantêm hashes e pacotes separados.

Os registros são ordenados por suas chaves. `batch_id` é o SHA-256 dos
registros canônicos das duas tabelas. Retry do mesmo input/contexto encontra
o mesmo lote, confere inventário, bytes raw e Parquet e retorna
`ALREADY_PRESENT_IDENTICAL`, sem reescrever arquivos. Conteúdo alterado no
destino ou lote incompleto causa erro; não há overwrite automático. Um lock
local por lote recusa escritor simultâneo com diagnóstico para retry. Após
interrupção abrupta, um lock/staging órfão exige inspeção do operador; não é
promovido ou removido automaticamente.

PyArrow **21.0.0** é fixado para manter Python 3.9 do projeto, conforme os
[wheels publicados](https://pypi.org/project/pyarrow/21.0.0/). São usados tipos
Arrow explícitos, Parquet 2.6, Snappy e leitura de volta com comparação dos
registros e schema. Arrays vazios/opcionais não mudam tipos. O determinismo
é de registros e IDs; não se promete igualdade binária de Parquet entre
versões da biblioteca. Reprocessamento com outra versão do normalizador
deve usar dataset separado e decisão explícita de leitura/migração.

## Saída local e falhas

```text
<output>/batches/<batch_id>/
  raw/spdx/sha256=<sha256>/document.spdx.json
  raw/records/sha256=<sha256>/record.json
  analytics/sbom_observations/part-00000.parquet
  analytics/sbom_packages/part-00000.parquet
  reports/records.json
  reports/normalization.json
  complete.json
```

Todos os inputs são lidos e validados antes de publicar qualquer lote.
Os bytes são congelados; alterações posteriores nos caminhos de preparação
não alteram o lote preparado. Serialização, read-back Parquet e conferência
dos materiais ocorrem num diretório staging. `complete.json` é escrito por
último; só depois a renomeação local torna o lote visível em `batches/`.
O inventário cobre exatamente os arquivos previstos, com tamanhos e hashes,
sem hash circular do próprio marcador. Ele comprova integridade local,
sem assinatura, autoridade de custódia ou garantia de fsync/recuperação
após perda de energia. Não há transação ou publicação S3 nesta fase.

JSON malformado, chaves duplicadas, números não finitos, tipo/schema errado,
raiz ambígua, subject divergente ou qualquer documento inválido recusam o
lote inteiro. A CLI termina com exit 1 e diagnóstico; não descarta pacotes
para corrigir uma contagem. Inputs e outputs devem ser arquivos locais
regulares; symlinks de arquivos e destinos são recusados. Não se extrai ZIP
não confiável no normalizador. O helper de testes lê somente membros
selecionados da fixture versionada e conferida por SHA-256.

Limites v1: 32 MiB por documento/registro, 4 MiB de contexto, 128 MiB de
inputs por lote, no máximo 512 documentos (170 imagens com três documentos),
100.000 pacotes por documento, 250.000 pacotes por lote, 128 referências por
pacote e profundidade JSON 64. A contagem de relationships é limitada a
800.000 por documento. O parser primeiro limita bytes, depois profundidade
e quantidades. Esses limites têm margem sobre os documentos observados
(máximo 135.894 bytes e 124 pacotes); JSON/Arrow ainda precisam de memória
maior que os bytes em disco. A entrada é um lote local limitado, não um
endpoint público ou sandbox de dados arbitrários.

## Multiarch, consultas e significado das contagens

Os dois datasets mantêm os três documentos por imagem. A view
`sbom_inventory_v1` seleciona somente documentos de plataforma e exclui
`is_document_subject`. O índice permanece pesquisável nas observações;
seus pacotes não são somados ao inventário de cada arquitetura.

- **Componentes por imagem/plataforma/documento:** quantidade de registros
  SPDX de pacotes após excluir o subject. Inclui layers, diretórios e fontes
  que o produtor reportar; não equivale à quantidade de APKs instalados.
- **Imagens/plataformas com um componente:** identidades distintas
  `(image_repository, image_index_digest, subject_digest, document_platform)`;
  homônimos e observações históricas não multiplicam essa contagem.
- **Observações históricas:** IDs de observação distintos. O mesmo documento
  visto em dois runs conta duas observações, com um único conjunto lógico de
  pacotes na versão do normalizador.

As duas tabelas físicas Athena e as views/consultas propostas estão em
[`sql/sbom-analytics`](../sql/sbom-analytics/README.md). Views `DISTINCT`
eliminam linhas idênticas de lotes sobrepostos antes do join. Chaves iguais
com conteúdo diferente são erro de ingestão; não se escolhe a linha mais
recente. As comparações alinham os SPDXIDs reportados e mostram nome,
versão, PURLs e purpose de ambos os lados. SPDXIDs são locais ao documento:
esse alinhamento diagnóstico não cria uma identidade universal do componente.

Não se usa último run como stable, tags como identidade imutável, presença
de componente como prova de CVE, ou imagem como aplicação implantada.

## Golden path local reproduzível

O helper usa somente os seis SPDXs e registros selecionados já versionados
na fixture histórica HGC-04. Não baixa artifacts, não muda essa fixture e
não atribui custódia produtiva ao run histórico:

```sh
python -B -m tests.unit.pipeline.analytics.fixture_support --output /scratch/sbom-input
python -B -m scripts.pipeline.analytics.normalize \
  --input /scratch/sbom-input/context.json --output /scratch/sbom-output
```

O segundo comando informa o caminho completo do lote. Use-o no demo:

```sh
python -B -m scripts.pipeline.analytics.demo \
  --batch /scratch/sbom-output/batches/<batch_id> \
  --component wolfi-baselayout \
  --runtime-framework go1-26 --dev-framework go1-26-dev \
  --runtime-index sha256:95f9b605fcd56b3fdb90bdc1d1d152674ef538d9197a02870a9dbc4a08260d30 \
  --dev-index sha256:af0fcfdd88958d994e7d186e8edf301c510ec8b69d0b0eafe9e1a220226257d2 \
  --platform linux/amd64
```

São seis observações e 300 registros de pacote: runtime 3/23/23, dev
3/124/124 para índice/amd64/arm64. O inventário contém 22 registros por
plataforma runtime e 123 por plataforma dev. `wolfi-baselayout` versão
`20230201-r30` aparece em quatro identidades de imagem/plataforma. Na
comparação amd64: 20 IDs com mesmo nome/versão reportados, dois somente
runtime e 103 somente dev. Nomes/versões não substituem as chaves do pacote.

O demo lê lotes completos e o Parquet conferido, sem usar os caminhos de
preparação. Executa SQLite local em memória; arrays/structs são representados
como texto JSON apenas nessa demonstração. Isso verifica lógica relacional,
joins e contagens, **não** o leitor Parquet, tipos aninhados ou execução de
DDL do Athena. `ATHENA_EXECUTED = NO`.

## Integrações restantes

Faltam aquisição autorizada, ingestão S3, escolha de bucket/prefixo e acesso,
decisões de retenção e adoção, criação de catálogo/tabelas, deduplicação na
ingestão e prova hospedada Athena. Os prefixos são placeholders separados
para raw, Parquet, relatórios e resultados de consultas. O bucket de custódia
HGC-04 não é destino aprovado por esta proposta. Não se depende de versões
antigas do mesmo objeto S3 para consultar histórico.

Este PR não altera HGC-01/02/03/04, Store JSON, manifests v1, workflows,
pins, builds, scan, runtime, signing, publicação, stable, HOM/PROD, recovery,
proving/U3A, IAM/OIDC ou infraestrutura. Não adiciona observabilidade geral,
dashboards, Trivy, Datadog ou CloudWatch.
