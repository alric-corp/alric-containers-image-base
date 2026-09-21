# Certificação controlada do catálogo

`Distroless - Catalog certification` (`catalog-certification.yml`) é um
entrypoint exclusivamente manual, executável na `main` após revisão/merge e
autorização explícita para publicar candidatos. Não aceita inputs. Seu array
versionado contém exatamente os 16 frameworks atuais; os testes exigem que
continue igual a `frameworks/*.yaml`, sem duplicatas e com pares completos.

O único job chama `build-base-images.yml`, com as mesmas variáveis AWS e
permissões do publicador normal. O lock
`factory-build-publish-${github.repository}`, com `cancel-in-progress: false`,
cobre a chamada inteira. Certificação e build normal não publicam em paralelo;
um run pendente ainda está sujeito à política de substituição de pendentes do
GitHub. Não há segunda implementação de build nem escrita de `stable` aqui.

O engine continua responsável por Melange/Apko, índices OCI amd64/arm64,
trust de certificados, Trivy, contratos funcionais, autorização por digest,
preflight ECR, publicação com read-back, Cosign keyless, SPDX e provenance.
Uma conclusão agregada ou uma linha `publicado` no resumo não substitui a
inspeção desses gates e dos passos posteriores de assinatura/attestation.

O schedule diário e o default de promoção permanecem no perfil
`go1-26`/`go1-26-dev`. Mudar esse perfil para FULL exige uma aprovação separada
depois da certificação. Este PR não despacha o workflow, não altera Terraform
nem muda `STABLE_PROMOTION_AUTHORIZED`.

## Evidência da execução

Depois do dispatch autorizado, registre o run ID, a tentativa e o `head_sha`
da API GitHub (`headSha` em `gh run view`). Preserve o inventário completo de jobs e artifacts desse run,
incluindo as conclusões dos passos de cada `Build & push <framework>`.
Baixe `publication-<framework>-<attempt>` para os 16 frameworks, os artifacts
`runtime-*`, `build-scans-*`, trust e `pipeline-summary-<attempt>`. A evidência
leve tem retenção de 30 dias; copie-a para o registro da certificação antes
de expirar. Não salve layouts OCI grandes no Git.

| Campo por artifact | Fonte e conferência |
| --- | --- |
| framework / repositório | Nome do artifact `publication-*` e `publication-evidence.json.image_ref` |
| digest e manifests amd64/arm64 | `publication-evidence.json`, `published-index.json` e `image.oci/validated-index.json`; o read-back deve coincidir com o índice validado |
| run_id / run_attempt / source_sha | Metadados do run, `runtime-gate-result.json` e `image.oci/build-inputs.json`; preserve também a tentativa de evidência funcional selecionada |
| tag imutável | Read-back ECR do digest; exija a tag de build do run/tentativa registrados, não `stable` nem uma tag inferida pela hora do run |
| imagePushedAt | Mesmo read-back ECR por digest, sem derivar do texto da tag |
| runtime contract status | `runtime-gate-result.json` e os relatórios amd64/arm64 correspondentes; os cinco companions compilados usam o contrato do runtime e vinculam os dois digests |
| Cosign status | Conclusão real de `Sign published image (keyless)`; registre separadamente a verificação remota |
| SPDX status | Conclusão de `Attest original SPDX SBOMs for index and both architectures` e `sbom-publication.json` com os subjects exatos |
| provenance status | Conclusão real de `Attest build provenance (SLSA)` e a attestation resolvida pelo digest |

Para cada digest confirmado, faça a consulta somente leitura abaixo usando
a região do run. Preserve o JSON completo, confira conta/repositório/digest
contra `publication-evidence.json.image_ref` e
identifique a tag com sufixo `-r<RUN_ID>-a<RUN_ATTEMPT>`. Evidência ausente,
ambígua ou de outro candidato não permite declarar a certificação completa.

```sh
aws ecr describe-images --region "$AWS_REGION" \
  --repository-name "image-base-${FRAMEWORK}" \
  --image-ids "imageDigest=${DIGEST}" --output json \
  > "ecr-${FRAMEWORK}.json"
```

`attested=true` e um passo de assinatura bem-sucedido registram publicação;
não são resultados de verificação criptográfica. Use o
[contrato de consumo](consumer-verification-contract.md) existente contra as
referências ECR por digest e preserve seus resultados separadamente. A
verificação de consumo do índice não deve ser descrita como verificação de
todas as attestations de plataforma. Não declare nenhum resultado hospedado
PASS antes de executar e examinar a evidência real.

## Soak e promoção posterior

Com os 16 candidatos e os gates completos, normalize os 16 `imagePushedAt`
para UTC e calcule:

```text
earliestPromotionAt = max(imagePushedAt dos 16 candidatos solicitados) + 6 horas
```

Preserve esses timestamps e identidades para a continuação. A hora da tag,
`created_at` do run e a hora de download do artifact não substituem o dado
ECR usado pela política real. Não há override de tempo para certificação.

O plano offline pode ser conferido sem AWS, com o array exato versionado no
workflow:

```sh
python3 -B -m scripts.pipeline.release.promotion_batch \
  '["dotnet10","dotnet10-dev","go1-25","go1-25-dev","go1-26","go1-26-dev","java21","java21-dev","java25","java25-dev","nodejs22","nodejs22-dev","nodejs24","nodejs24-dev","python3-13","python3-14"]' \
  --soak-hours 6 --plan
```

Resultado: 11 unidades para 16 artifacts. Os pares compilados são dotnet10,
go1-25, go1-26, java21 e java25 com seus `-dev`. nodejs22, nodejs22-dev,
nodejs24, nodejs24-dev, python3-13 e python3-14 são unidades independentes.

Somente depois do soak real e de autorização explícita de promoção, use o
`workflow_dispatch` existente de `Distroless - Promote stable`, com o array
FULL acima e soak de seis horas. O kill switch permanente continua valendo;
este entrypoint não o habilita. Não existe tag `stable-test`. Confirme os
candidatos atuais contra o registro da certificação: o seletor existente
consulta candidatos elegíveis no ECR, não fixa automaticamente um run de
certificação passado.

A promoção mantém inventário/seleção, autorização dos pares, verificação
Cosign/provenance e scan Trivy fresco antes da barreira global de escrita.
Unidades reprovadas não escrevem; unidades independentes autorizadas podem
concluir depois da barreira, com falha agregada se outra unidade falhar. As
escritas de um par não são uma transação ECR: falha parcial preserva ambos
os read-backs e mantém os dois membros com `promoted=false`.
