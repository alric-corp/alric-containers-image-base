# SQL proposto para Athena

Nada neste diretório cria recursos ou executa consultas remotas.
`tables.sql` propõe duas tabelas externas com os tipos explícitos do schema
v1. São usados [Parquet SerDe](https://docs.aws.amazon.com/athena/latest/ug/parquet-serde.html)
e os [tipos Hive de DDL do Athena](https://docs.aws.amazon.com/athena/latest/ug/data-types.html).
As tabelas físicas têm sufixo `rows_v1`; `views.sql` fornece as duas relações
lógicas deduplicadas e o inventário de plataforma.

Substitua `<ANALYTICS_BUCKET>` e `<DATASET_PREFIX>` somente numa integração
autorizada. Não há bucket escolhido/aprovado neste PR, inclusive o de HGC-04.
A organização futura proposta é:

```text
s3://<ANALYTICS_BUCKET>/<DATASET_PREFIX>/
  raw/spdx/sha256=<digest>/document.spdx.json
  raw/records/sha256=<digest>/record.json
  analytics/schema=v1/normalizer=1.0.0/sbom_observations/<batch_id>.parquet
  analytics/schema=v1/normalizer=1.0.0/sbom_packages/<batch_id>.parquet
  reports/<batch_id>/...
  query-results/...
```

O batch local inclui raw, relatórios e Parquet; cada `LOCATION` Athena inclui
**somente** os Parquets da respectiva tabela/versão. A futura ingestão deve
conferir o lote completo e enviar cada categoria ao prefixo correto. Nunca
aponte a tabela à raiz do lote. Histórico usa objetos/registros distintos,
sem depender de S3 VersionId de um nome sobrescrito.

Não há particionamento inicial: seis documentos não justificam uma decisão
de volume. Se o histórico justificar, uma futura revisão pode propor mês
de observação com origem temporal definida e catalogação correspondente.
Não se propõem partições por run, digest ou nome de pacote, nem um arquivo
por componente. Os arquivos são por lote, com IDs determinísticos.

Lotes distintos podem compartilhar documentos/pacotes. As views removem
linhas completas idênticas **antes** do join para não multiplicar o inventário.
Conflito de conteúdo para `(sbom_sha256, package_spdx_id)` dentro da mesma
versão é erro de ingestão, não escolha de latest. O demo local recusa esse
conflito. Parquets de outras versões de schema/normalizador ficam em outro
prefixo; não os misture nas mesmas tabelas.

## Parâmetros e interpretação

As consultas usam [parâmetros posicionais `?` do Athena](https://docs.aws.amazon.com/athena/latest/ug/querying-with-prepared-statements.html),
em cláusulas WHERE. Valores são fornecidos separadamente, na ordem indicada;
não faça substituição de texto SQL com nomes de componentes. O demo usa os
bindings parametrizados do SQLite.

| Consulta | Parâmetros na ordem | Resultado |
| --- | --- | --- |
| `01_find_images.sql` | Nome exato do componente | Identidades distintas de imagem/plataforma, sem duplicar observações |
| `02_versions.sql` | Nome exato do componente | Versões reportadas, inclusive `null`, com quantidade de identidades de imagem/plataforma |
| `03_runtime_vs_dev.sql` | Repository, run, attempt, source SHA e plataforma comuns; framework/SPDX SHA-256 runtime; framework/SPDX SHA-256 dev | Alinhamento dos SPDXIDs reportados na mesma execução/plataforma, mostrando os dois lados |
| `04_compare_digests.sql` | Plataforma comum; índice/SPDX SHA-256 esquerdo; índice/SPDX SHA-256 direito | Comparação por digests/documentos explícitos, sem latest/tag |
| `05_trace_original.sql` | `observation_id` | Origem, subjects, SHA-256 raw, checksum canônico distinto, caminho raw e referências dos registros |

As consultas usam um filtro comum de execução/plataforma (03) ou plataforma
(04), sem parâmetros independentes que possam trocar a arquitetura de um lado. O demo
usa uma única plataforma para ambos e recusa índices ausentes/ambíguos.
Quando houver mais de um SPDX para o mesmo subject, selecione o SHA-256 do
documento explicitamente; não elimine essa distinção.

`SAME_REPORTED_NAME_VERSION` compara somente esses dois campos para o mesmo
SPDXID reportado. Não afirma equivalência de código, PURL, licença ou
identidade universal; os PURLs/purpose dos dois lados ficam disponíveis.
IDs diferentes não são colapsados por nome/versão. As consultas não expandem
arrays de PURL, não classificam dependências e não inferem CVEs.

## Prova local e limites

`python -B -m scripts.pipeline.analytics.demo --help` descreve a execução
offline com Parquet previamente lido/conferido. O SQLite usa texto JSON
para arrays/structs e troca apenas `CREATE OR REPLACE VIEW` por `CREATE VIEW`.
Os SELECTs das cinco consultas são os mesmos arquivos propostos para Athena.
São testados filtros, identidades, joins, deduplicação e contagens. DDL
Athena, tipos aninhados nativos e leitura hospedada Parquet continuam
**NOT_PROVEN / ATHENA_EXECUTED = NO**.

O inventário conta registros SPDX não-root dos documentos de plataforma;
inclui layers/fontes reportados. A consulta de imagens distintas conta
`(image_repository, image_index_digest, subject_digest, document_platform)`.
Observações históricas são contadas por `observation_id` separadamente.
Não são aplicações consumidoras nem implantações. Nenhum resultado é
autoridade de segurança, publicação, promoção ou custódia.
