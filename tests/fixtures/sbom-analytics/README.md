# Fontes do golden path SPDX

`sources.json` registra o ZIP e os seis membros originais, com SHA-256,
tamanho, contagens observadas e artifact ID. Os bytes permanecem na fixture
existente `tests/fixtures/hgc04/materials.zip`, sem cópia ou modificação.
O helper `tests/unit/pipeline/analytics/fixture_support.py` confere esses
hashes antes de materializar somente os documentos selecionados em scratch.

Origem histórica: `alric-corp/alric-containers-image-base`, run
`37806495087`, attempt `1`, push / `refs/heads/develop`, commit
`4c1783e8c2a36e0f79f453b2f080a23a0eeea0d3`. O ZIP curado tem SHA-256
`7a1f477dcea027f4f8b338d3b50aa50d26c6d9b5b01fb37bb328e23d594003a4`.
Sua proveniência é a seleção histórica documentada no README HGC-04;
não é aquisição atual autenticada nem prova de armazenamento produtivo.

| Framework | Documento | Bytes | Pacotes | SHA-256 original |
| --- | --- | ---: | ---: | --- |
| go1-26 | índice | 4252 | 3 | `86d4f728ebdb9f3214efff020eb2fcb83fb961b6b6f5a2843d9efcf405a0fbd0` |
| go1-26 | x86_64 | 22651 | 23 | `30487d1481bcfaa01fed56df9d95bb4e4b24fb13c145983eafaf5dd05393a8c6` |
| go1-26 | aarch64 | 22658 | 23 | `90908e34d2e9c4528a04649ed7fd8cc7f8d19f37804e3452521379676071ea39` |
| go1-26-dev | índice | 4264 | 3 | `e344d91e4257e7c4300bbca3caf147ffd73ead41fcb00f8383f0cbde96eca3f0` |
| go1-26-dev | x86_64 | 135871 | 124 | `c8c137eb8292cfe68850d75d6f334e4dae10b6c4726881638d8f3a7d48f6a920` |
| go1-26-dev | aarch64 | 135894 | 124 | `c690a3a6b4cc78bab26c999a1b795cc9b2917ce02af4e22a8df85725b3e0f778` |

Os seis documentos são SPDX-2.3, namespace
`https://spdx.org/spdxdocs/apko/`, com uma raiz `documentDescribes` e checksum
SHA256 OCI. `creationInfo.created` é `2026-10-08T16:08:48Z`. Há 2/21/21
relationships no runtime e 2/190/190 no dev. Há pacotes homônimos, PURLs,
licenças e records de layers/fontes; não são fixtures vazias de subject.

As identidades esperadas de OCI vêm de `tests/fixtures/hgc04/expected.json`,
independentemente do SPDX. Os registros locais de validação/publicação e
candidate identity também vêm da seleção histórica, como materiais distintos.
O timestamp externo é o committer date preservado em `acquisition/context.json`,
com essa origem explicitamente registrada. O resultado hosted é apenas
reportado, não revalidado criptograficamente pelo normalizador.

Casos inválidos e campos opcionais são criados em diretórios temporários.
Não se versionam credenciais, chaves privadas, layers OCI, caches ou dossiês
cloud adicionais. `HISTORICAL_ANALYTICS_TEST_INPUT` não concede autoridade
de release, custódia, publicação ou promoção.
