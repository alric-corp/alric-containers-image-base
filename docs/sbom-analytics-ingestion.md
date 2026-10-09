# SBOM Analytics: snapshots S3 verificáveis

Este incremento publica um lote completo do normalizador por um **cliente S3
injetado**. Os testes usam exclusivamente um cliente em memória. Não configura
AWS, executa Athena, altera workflows ou ativa HGC-04. Não adiciona dependências:
PyArrow 21.0.0 e o schema analítico v1 permanecem os existentes.

## Entrada, plano e identidade

`prepare_snapshot(batch, destination, limits)` recebe um lote local concluído.
Antes do transporte, valida `complete.json`, seu schema/estado, hashes, tamanhos
e inventário. A lista permitida vem desse inventário e do contrato do normalizador,
nunca de um upload recursivo de diretório arbitrário. Somente estes caminhos são
aceitos:

```text
complete.json
reports/records.json
reports/normalization.json
analytics/sbom_observations/part-00000.parquet
analytics/sbom_packages/part-00000.parquet
raw/spdx/sha256=<sha256>/document.spdx.json
raw/records/sha256=<sha256>/record.json
```

São recusados symlinks, arquivos especiais, diretórios extras, caminhos inseguros,
duplicatas JSON, inventários incompletos, versões desconhecidas e bytes divergentes.
A validação usa uma cópia privada dos bytes congelados e o `read_completed`
existente: confere identidade/ordenação dos registros, vínculos de hash raw,
inventário e igualdade de registros/schema entre JSON e Parquet. Também confere
schema, versão, contagens e limites de autoridade do relatório de normalização.
Não reexecuta o produtor SPDX nem autentica os claims de origem do lote.

O plano congela bytes, caminhos, content types e metadata de aplicação em
estruturas imutáveis. Alterar a preparação depois disso não altera o envio.
`save_plan` conserva uma cópia local integral com `plan.json`; `load_plan` recusa
qualquer mudança e permite retomar sem os caminhos de preparação. Use diretórios
privados do chamador; isso não é sandbox contra outro processo que controle esses
diretórios, nem garantia de fsync após perda de energia.

Identidades diferentes têm funções diferentes:

- `batch_id`: SHA-256 dos registros canônicos do normalizador, **preservado**.
- Hash do arquivo: SHA-256 de seus bytes, incluindo a serialização Parquet.
- `snapshot_id`: SHA-256 do JSON canônico de `SnapshotPlan.identity()`. A preimagem
  contém protocolo 1, batch, schema 1, normalizador 1.0.0, destino externo
  (bucket/prefixo/região/owner) e inventário ordenado dos arquivos, com caminho,
  tamanho, hash, content type e metadata de aplicação.

Nova serialização com registros iguais conserva o batch e recebe outro snapshot.
Outro destino também recebe outro snapshot. Não se confundem igualdade lógica e
retry byte-idêntico. O ID não inclui limites operacionais, VersionIds futuros ou
o manifesto final; não há ciclo de hashes. Não se geram timestamps, assinaturas
ou arquivos aleatórios em um retry.

## Layout fechado e manifesto v1

```text
s3://<ANALYTICS_BUCKET>/<AUTHORIZED_PREFIX>/snapshots/<snapshot_id>/
  raw/spdx/sha256=<sha256>/document.spdx.json
  raw/records/sha256=<sha256>/record.json
  analytics/sbom_observations/part-00000.parquet
  analytics/sbom_packages/part-00000.parquet
  reports/records.json
  reports/normalization.json
  complete.json
  ingestion-manifest.json
```

Todos os arquivos do batch conservam os bytes originais, inclusive raw, relatórios,
marcador local e Parquets. O manifesto de ingestão é outro documento; não substitui
o `complete.json` nem muda IDs ou SPDXs. O layout fechado substitui, **para esta
fase**, a proposta anterior de acrescentar lotes a prefixos analíticos compartilhados
em `sql/sbom-analytics/README.md`. Snapshot não é partição obrigatória por run.
Histórico usa prefixos/objetos distintos, não versões antigas de um mesmo nome.

`ingestion-manifest.json` é canônico e tem campos exatos:

| Campos | Contrato |
| --- | --- |
| `protocol_version`, `schema_version`, `normalizer_version` | 1, 1, `1.0.0` |
| `status`, `snapshot_id`, `batch_id` | `SNAPSHOT_COMPLETE`, identidade da publicação e batch original |
| `destination` | Bucket, prefixo, região e expected owner fornecidos externamente |
| `files[]` | Caminho relativo, key derivada, tamanho, SHA-256, content type, metadata de aplicação e VersionId observado ou null |
| `observations[]` | Registros originais de observação: origem, execução, subjects, caminhos raw e checks preservados |
| `verification` | Validação local, read-back de bytes, inventário exato e versões atuais conferidas naquele momento |
| `authentication`, `publication_authority` | `NOT_REVALIDATED`, false |
| `delete_protection`, `retention_availability` | `NOT_PROVEN`, `NOT_PROVEN` |

Não há hash autorreferente do manifesto. Seu hash e VersionId são registrados no
resultado externo; os próprios bytes passam pelo read-back. O leitor recompõe a
identidade do snapshot e o manifesto a partir dos arquivos recuperados, compara
os bytes e exige o conjunto exato. Campos, versões, tipos e hashes incompatíveis
são recusados. Uma observação de PR conserva seu evento/ref; não vira release ou
stable. Integridade local e resultados hospedados preservados não são nova
verificação criptográfica. `publication_authority=false` sempre permanece.

## Adapter e protocolo de publicação

`S3Adapter(client, destination, limits)` exige um cliente low-level fornecido pelo
chamador, cuja `meta.region_name` corresponda à configuração. Importação, construção
e planejamento não inicializam SDK, procuram credenciais ou leem `.iupipes.yml`.
Nenhum bucket/conta/role do laboratório é escolhido. O owner é uma string de 12
dígitos ou null explicitamente fornecido. Quando informado, `ExpectedBucketOwner`
acompanha PUT, GET e LIST. Buckets de diretório/access points não são suportados.

1. Validar e congelar o plano integral antes de qualquer chamada.
2. Se já há manifesto, recuperar/conferir o snapshot existente e compará-lo com a
   requisição. Um snapshot final inválido exige investigação, não reparo automático.
3. Para cada arquivo, executar **PutObject simples com `IfNoneMatch='*'`**, bytes
   congelados, ContentLength/Type, metadata e ChecksumSHA256. Não usar HEAD como
   proteção, overwrite, `upload_file` ou multipart automático.
4. Recuperar os bytes da versão retornada e recalcular SHA-256. Comparar também
   content type e toda metadata de aplicação. ETag não é usado como prova.
5. Conferir novamente todas as versões, seus objetos atuais e a listagem paginada
   completa do prefixo exclusivo. Só então congelar/criar o manifesto condicional.
6. Recuperar todo o snapshot pelo transporte e conferir o registro final antes de
   retornar `complete=true` e `catalog_eligible=true`.

A escrita condicional resulta em 412 se já existe objeto atual; o adapter lê e
compara, retornando `ALREADY_PRESENT_IDENTICAL` ou `CONTENT_CONFLICT`. O erro
409 `ConditionalRequestConflict` permite retry limitado do mesmo PUT; outros
409 são erros operacionais, não prova de conteúdo divergente. São as semânticas
documentadas de [conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html)
e [PutObject](https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html).

Timeout/conexão perdida/5xx podem ter ocorrido depois da gravação: o adapter
reconcilia por GET e comparação integral. Leitura inconclusiva ou objeto ausente
nesse caso retorna `WRITE_OUTCOME_UNKNOWN`, nunca sucesso presumido. Apenas
404 `NoSuchKey` em GET atual é ausência; acesso negado é erro. GET de VersionId
indisponível não usa latest como fallback. A versão específica requer
`s3:GetObjectVersion`; ver [GetObject](https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html).

LIST não usa delimitador e exige paginação completa, escopo exato, chaves únicas,
tamanhos válidos e tokens sem loop. Um limite excedido é erro, não inventário
completo. Ver [ListObjectsV2](https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectsV2.html).
Como Athena lê objetos atuais, uma versão histórica válida não basta: o leitor
também exige que a versão atual continue sendo a registrada.

Os resultados do snapshot são `SNAPSHOT_CREATED`,
`SNAPSHOT_ALREADY_PRESENT_IDENTICAL` ou erro estruturado. Falhas não geram plano
de catalogação aprovado. Um envio parcial permanece no prefixo, sem promoção ou
exclusão; o mesmo plano congelado pode reconciliar os arquivos já gravados.
Uma resposta final perdida também exige read-back completo. Se o marcador foi
gravado mas seu read-back falhou, sua presença isolada não aprova o snapshot.

Não há transação multiobjeto, garantia contra mudança posterior, WORM ou prova
de disponibilidade futura. If-None-Match protege a criação contra o objeto atual;
exclusão/recriação e administradores precisam de controles externos. O fake usa
lock local, sem persistência entre processos nem prova de enforcement aplicado.

## CLI offline, API e diagnóstico JSON

Configuração local, com placeholders a substituir por uma decisão autorizada:

```json
{
  "protocol_version": 1,
  "destination": {
    "bucket": "<AUTHORIZED_BUCKET>",
    "prefix": "<AUTHORIZED_PREFIX>",
    "region": "<AUTHORIZED_REGION>",
    "expected_bucket_owner": null
  }
}
```

```sh
python -B -m scripts.pipeline.analytics.ingest \
  --batch /scratch/output/batches/<batch_id> \
  --config /scratch/ingestion-config.json \
  --plan-dir /scratch/frozen-upload-plan \
  --report /scratch/diagnostics/plan.json
```

Essa CLI somente congela o plano e retorna `NOT_UPLOADED`, sem SDK/rede. Para
integração futura, o chamador autorizado fornece o cliente; este PR não o cria:

```python
from scripts.pipeline.analytics.ingest import publish_reported
from scripts.pipeline.analytics.s3_ingestion import S3Adapter
from scripts.pipeline.analytics.snapshot import load_plan, recover_snapshot
from scripts.pipeline.analytics.catalog import catalog_plan

plan = load_plan("/scratch/frozen-upload-plan")
adapter = S3Adapter(authorized_low_level_client, plan.destination, plan.limits)
result = publish_reported(plan, adapter, "/scratch/diagnostics/ingestion.json")
# Somente se result["complete"] for True; catalog_plan refaz read-back obrigatório.
proposal = catalog_plan(adapter, plan.snapshot_id, database="poc_sbom", table_prefix="poc_snapshot")
# Nunca executa DDL. Recuperação não usa caminhos do produtor:
recover_snapshot(adapter, plan.snapshot_id, "/scratch/new-recovered-batch")
```

Sucesso e falha retornam JSON com etapa, código estável, batch/snapshot conhecidos,
operação/objeto, esperado/observado seguros, completude, elegibilidade e retry.
Não se expõem mensagens SDK, conteúdo SPDX, tokens ou URLs assinadas. O relatório
fica fora do batch, plano e configuração; pode ser substituído por outro diagnóstico
da mesma operação. Falha de escrita do relatório retorna `REPORT_WRITE_FAILED`,
mesmo se o snapshot foi enviado: reconciliar explicitamente, não presumir sucesso.
Sem sink válido/permissão, a CLI continua emitindo JSON de erro em stdout e exit 1;
a API retorna o erro. Não é possível prometer um arquivo onde a escrita foi negada.
Os diagnósticos da CLI **antiga** do normalizador permanecem textuais; não foram
alterados incidentalmente por este incremento.

Limites padrão do protocolo v1, com overrides externos limitados: objeto 64 MiB,
snapshot incluindo manifesto 256 MiB, 2.048 objetos incluindo manifesto, páginas
de até 1.000 objetos, 8 páginas, 3 PUTs por conflito condicional e reads em blocos
de 64 KiB. Manifesto/configuração/plano JSON têm limite de 4 MiB. Antes de ler
Parquet, conferem-se metadados, até 512 observações/250.000 pacotes, 4.096 row groups
por arquivo e expansão declarada agregada de 256 MiB; o leitor também confere
schema/valores. São margens sobre o golden path, não sandbox geral contra arquivos
arbitrários ou promessa de memória constante. Os máximos aceitos estão em `Limits`.

## Catálogo e prova local

`catalog_plan` só retorna após novo read-back integral do armazenamento. Exige
database e prefixo de nomes externos começando por `poc_`; os nomes incluem o ID
completo do snapshot. Reutiliza `tables.sql`, `views.sql` e as cinco consultas,
alterando apenas identificadores e LOCATIONs. Antes de executar futuramente,
confirmar namespace/nomes novos e isolados: o código não consulta o catálogo.

As duas LOCATIONs exatas são:

```text
s3://<bucket>/<prefix>/snapshots/<snapshot_id>/analytics/sbom_observations/
s3://<bucket>/<prefix>/snapshots/<snapshot_id>/analytics/sbom_packages/
```

Cada uma contém somente o Parquet do respectivo schema. Raw, relatórios e markers
ficam fora. O marcador **não impede Athena de ler** um prefixo; seleção/catalogação
explícita é a barreira de completude. Não apontar tabelas ao ancestral de snapshots,
alterar latest/stable ou prometer transação entre as duas tabelas. Resultados de
consultas ficam num destino separado, a decidir. A raiz conhecida do snapshot +
`raw_spdx_path` relativo localiza os bytes originais, sem scratch do produtor.
O documento `proposal` é serializável em JSON; o executor futuro deve recusá-lo
quando `execute=false` e obter autorização própria antes de qualquer DDL.

```sh
python -B -m unittest tests.unit.pipeline.analytics.test_s3_ingestion \
  tests.unit.pipeline.analytics.test_snapshot tests.unit.pipeline.analytics.test_ingest -v
make check
```

O positivo usa os seis SPDXs históricos identificados em
[`tests/fixtures/sbom-analytics/sources.json`](../tests/fixtures/sbom-analytics/sources.json),
sem mudar fixtures HGC-04: congela, publica no fake, torna a preparação indisponível,
recupera num diretório novo, compara todos os bytes e lê os Parquets/consultas
SQLite existentes. Há 6 observações/300 registros, 22 componentes reportados por
plataforma runtime e 123 dev; comparação amd64: 20 mesmos nomes/versões reportados,
2 somente runtime e 103 somente dev. As comparações por SPDXID são diagnósticas,
e contagens não equivalem a pacotes instalados. Imports do normalizador ligados
ao modelo de release do laboratório continuam existentes e explícitos.
SQLite não prova DDL, nested types ou leitura hospedada Athena.

## Pré-requisitos da POC real e porte corporativo

Decisões externas ainda necessárias: bucket/prefixo autorizado, região/conta owner,
acessos limitados de escrita/leitura/versão/listagem (e KMS, caso aplicável), catálogo
e namespace/tabelas POC isolados, workgroup, saída das consultas, controles de
custo e retenção aprovados. Não se escolhe prazo corporativo ou bucket HGC-04 aqui.
O integrador deve fixar SDK compatível pelo canal aprovado, configurar endpoint,
timeouts/retries/credenciais externamente e testar parâmetros contra o serviço.

A prova real futura deve usar namespace isolado autorizado para concorrência,
conflito, versões, respostas perdidas e falhas, sem mutações destrutivas em releases.
Um consumidor novo recuperará apenas do S3, conferirá bytes/Parquet/queries e
catalogará somente o snapshot aprovado. Integridade, origem, criação única e
disponibilidade serão avaliadas separadamente. Este incremento não autentica a
projeção nem demonstra enforcement, exclusão protegida ou prova hospedada S3/Athena.

Porte ao Itaú continua separado: runners ARC/EKS, dependências pelo canal aprovado,
configuração corporativa autorizada, arquivos FROZEN preservados e classificação
dos novos caminhos no base-sync. Não lê configuração corporativa nem altera esses
repositórios. Não altera build/scan/runtime/signing/publicação, stable/HOM/PROD,
recovery, proving/U3A, IAM, retenção, workflows ou contratos de custódia.
