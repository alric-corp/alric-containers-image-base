# SBOM Analytics: vínculo de artifacts de build à origem declarada

`scripts/pipeline/analytics/artifact_binding.py` é o chamador fino entre a
aquisição de um integrador (inclusive o corporativo) e o caminho existente
`artifact_input.stage` → normalizador. Ele não substitui nenhum dos dois e não
altera `normalize.py`: acrescenta somente a recusa de origem divergente antes
de qualquer saída ficar visível.

É opt-in. Nenhum workflow o chama, não há ingestão automática, e o resultado é
um diretório local para o normalizador. Não baixa nada, não chama GitHub nem
AWS, não executa membros do artifact e não exige registro HGC-04.

## Interface mínima

O integrador fornece, explicitamente, um manifesto v1 e os arquivos que ele
referencia (caminhos relativos ao manifesto):

| Campo | Origem esperada | Uso |
| --- | --- | --- |
| `origin` | Run que produziu os artifacts: `repository`, `run_id`, `run_attempt`, `source_sha`, `event`, `ref` (mesma forma do normalizador) | Copiado sem inferência para o contexto; o normalizador recusa campo ausente ou extra |
| `repository_id` | ID numérico do repositório produtor | Comparado com `workflow_run.repository_id`/`head_repository_id` |
| `image_registry`, `repository_prefix` | Configuração vigente do integrador | Nome do repositório da imagem; nenhum default |
| `archive_digest_policy` | Decisão do integrador: `REQUIRED` ou `RECORD_ONLY` | Se o digest do ZIP na API é obrigatório |
| `sample_classification` | `SYNTHETIC`, `SANITIZED`, `LAB_REAL` ou `REAL_AUTHORIZED` | Registrado no recibo; não muda as verificações |
| `artifacts[].path` | ZIP baixado de `archive_download_url` (ou diretório extraído, só em `RECORD_ONLY`) | Bytes hasheados uma vez; o staging usa a cópia desses bytes |
| `artifacts[].api_record` | Resposta salva de `GET /repos/{owner}/{repo}/actions/artifacts/{id}` | `id`, `name`, `workflow_run.{id, repository_id, head_sha}` obrigatórios |
| `artifacts[].expected_subjects` | Índice e plataformas de fonte independente: evidência de publicação ou record verificado pelo consumidor | Comparados com `validated-index.json` antes e depois do staging |
| `artifacts[].subjects_source` | Referência textual dessa fonte | Registrada; não é interpretada |

Os seis membros consumidos continuam os de `artifact_input`
(três SPDX, `apko.lock.json`, `build-inputs.json`, `validated-index.json`).

## Recusas

| Código | Condição |
| --- | --- |
| `ARTIFACT_RECORD_INCOMPLETE` | Registro da API sem `id`, `name` ou `workflow_run.{id,repository_id,head_sha}` |
| `ARTIFACT_ID_DIFFERS`, `ARTIFACT_NAME_DIFFERS` | Registro de outro artifact |
| `ARTIFACT_ATTEMPT_DIFFERS` | Nome não é `sbom-<framework>-<run_attempt>` |
| `ARTIFACT_RUN_DIFFERS` | `workflow_run.id` diferente de `origin.run_id` |
| `ARTIFACT_REPOSITORY_DIFFERS` | Repositório produtor (ou head de fork) diferente |
| `ARTIFACT_SOURCE_DIFFERS`, `ARTIFACT_BRANCH_DIFFERS` | Commit ou branch do run diferentes da origem |
| `ARCHIVE_DIGEST_DIFFERS`, `ARCHIVE_SIZE_DIFFERS` | Bytes do ZIP diferentes do registro da API |
| `ARCHIVE_DIGEST_NOT_PROVIDED`, `ARCHIVE_NOT_VERIFIABLE` | Sem digest na API ou diretório extraído com política `REQUIRED` |
| `SUBJECT_DIFFERS` | Plataformas do `validated-index.json` diferentes das esperadas |
| `STAGING_REFUSED` | Recusa do `artifact_input`/normalizador: hash, subject SPDX, revisão, lock, índice esperado, origem incompleta |

Fatos opcionais ausentes (`head_repository_id`, `head_branch`, `size_in_bytes`,
`expired`, digest em `RECORD_ONLY`) aparecem como `NOT_PROVIDED` em
`binding-receipt.json`; nunca são deduzidos de outro campo.

## Uso

```sh
python -B -m scripts.pipeline.analytics.artifact_binding \
  --manifest /scratch/input/binding.json --work /scratch/bound
python -B -m scripts.pipeline.analytics.normalize \
  --input /scratch/bound/context.json --output /scratch/analytics
```

`/scratch/bound` recebe o diretório do `artifact_input` (`context.json`,
`staging-receipt.json`, bytes verificados) mais `binding-receipt.json`, ou não
é criado. Recusas saem em JSON no stderr com `status`, `code` e `message`.

## O que isto não prova

O recibo declara `cryptographic_authenticity: NOT_REVALIDATED`,
`publication_authority: false`, `ingestion: NOT_PERFORMED` e
`hosted_execution: NOT_PROVEN`. O vínculo prova coerência entre bytes,
registro da API, origem e subjects informados. Não prova assinatura, que o
registro da API foi obtido de uma sessão autorizada, IAM, rede, destino S3 ou
namespace de catálogo. Esses itens dependem da homologação corporativa.

Os testes portáveis usam somente amostras `SYNTHETIC` geradas no teste; os
testes `LAB_REAL` ficam em módulo separado. Registros de GitHub Enterprise
Server e o sample corporativo completo permanecem NOT_VERIFIED até um sample
autorizado ser fornecido pelo integrador corporativo.
