# Retenção e disponibilidade das imagens no ECR

Fonte ativa para o que o ECR da Factory retém, por quanto tempo e o que isso
permite recuperar. Imutabilidade de tag, disponibilidade de um digest,
retenção e recovery são contratos diferentes; este documento os separa por
ambiente.

A lifecycle aplicada é
[`infra/ecr/policies/ecr-lifecycle-7-days.json`](../infra/ecr/policies/ecr-lifecycle-7-days.json),
carregada por `infra/ecr/locals.tf` e associada a cada repositório do catálogo
em `infra/ecr/main.tf`. A semântica de avaliação é a da
[documentação de lifecycle do ECR](https://docs.aws.amazon.com/AmazonECR/latest/userguide/LifecyclePolicies.html).

## Estado verificado (DEV LAB, 2026-10-13)

Leitura somente de configuração e metadados (`describe-repositories`,
`get-lifecycle-policy`, `describe-images`) dos 16 repositórios `image-base-*`
da conta `712107929769`, região `us-east-1`:

- os 16 têm `IMMUTABLE_WITH_EXCLUSION` com exceção `stable`, `scanOnPush` e
  AES256;
- os 16 têm a mesma lifecycle, igual ao arquivo versionado (comparação do
  JSON canônico);
- nenhuma build tag com push anterior a 2026-10-06 continua no registry,
  exceto o índice que tem `stable`. Esse índice, publicado em 2026-10-01,
  continua presente;
- os 14 repositórios fora do golden path não têm nenhuma imagem com tag.
  Os índices da certificação de 2026-10-04 já expiraram.

## Regras efetivas em DEV

| Prioridade | Seleção | Efeito |
| --- | --- | --- |
| 1 | Imagens com a tag `stable`, contagem acima de 999999 | Na prática, nunca expira. Pela semântica do ECR, uma imagem que atende à seleção de uma regra de prioridade maior não pode ser expirada por regra de prioridade menor, mesmo que também tenha uma build tag. |
| 2 | Qualquer outra imagem com tag, `sinceImagePushed` | Expira 7 dias após o push. O ECR executa a expiração em até 24 horas depois de o critério ser atingido. |
| — | Imagens sem tag | Nenhuma regra. |

## O que cada contrato garante em DEV

| Contrato | Garantia em DEV |
| --- | --- |
| Imutabilidade de tag | A build tag `DDMMAA-HHMM-r<RUN>-a<ATTEMPT>` nunca é reapontada; `stable` é a única tag móvel. Imutável não significa retido: a tag desaparece com a imagem expirada. |
| Disponibilidade do digest do índice OCI | Candidate não promovido: cerca de 7 dias após o push (mais até 24 horas). Índice com `stable`: enquanto tiver a tag. Ao perder `stable`, um índice com mais de 7 dias expira na avaliação seguinte. |
| Proteção de `stable` | Somente o índice que tem `stable` agora. Releases anteriores não ficam protegidas. |
| Retenção de build tags | 7 dias após o push, para todo índice que não tem `stable`. |
| Filhos de plataforma | Um manifesto referenciado por um índice não expira enquanto o índice existir. Depois que o índice expira, os filhos sem tag permanecem, porque nenhuma regra seleciona itens sem tag; eles não formam uma imagem multi-arquitetura utilizável e não são retenção contratual. |
| Referrers (assinatura, SPDX, provenance) | O ECR os expira em até 24 horas após a remoção do subject. Não existe retenção de assinatura isolada do índice. |
| Artifacts transitórios do GitHub Actions | OCI aprovado por 3 dias; SBOM, locks, scans e evidências de release por 30 dias ([`health.json`](../policies/operations/health.json)). Não são backup e não prolongam a disponibilidade no ECR. |
| Release Store DEV (S3) | Candidates, manifestos, eventos e estado não têm expiração. Um registro de release não garante que os bytes da release ainda existam no ECR. |
| Rollback e recovery | Não existe recovery DEV para release anterior. Uma release DEV só pode ser promovida, ou retomada, enquanto seus bytes e referrers existirem e se passar de novo por trust e re-scan. Depois de expirada, a verificação falha fechado. |

## HOM

`infra/lifecycle` declara os repositórios HOM sem lifecycle: nenhuma imagem
expira por idade. O recovery (`recover-stable.yml`) aceita somente releases com
recibo em `promoted/` no bucket HOM e ainda exige bytes retidos e re-scan
aprovado. A promoção HOM está desabilitada (`"enabled": false` em
[`promote-hom.json`](../policies/pipeline/promote-hom.json)). A configuração
HOM não foi lida ao vivo nesta revisão.

## Ambiente corporativo

Não homologado. As janelas do LAB não são garantia corporativa. A janela de
pull, de rollback/recovery e de retenção de evidências depende de decisão dos
owners de Cloud, Produto e Auditoria para cada ambiente.

## Consequências para consumidores

- Fixe por digest um índice promovido a `stable`. Um digest DEV não promovido
  pode desaparecer em cerca de 7 dias.
- A tag `stable` é conveniência; o digest do índice é a identidade auditada
  ([contrato de verificação](consumer-verification-contract.md)).
- Reprodutibilidade de longo prazo exige copiar o índice e seus referrers para
  um registry com retenção aprovada pelo consumidor.

## Histórico, não aplicado

[`policies/operations/ecr-lifecycle.json`](../policies/operations/ecr-lifecycle.json)
é o modelo anterior: expirava somente imagens sem tag após 30 dias e preservava
todas as tags. Foi aplicado e relido nos 15 repositórios então existentes em
2026-09-10 (registro em [saúde operacional](m11-m04-operational-health.md)).
A lifecycle de 7 dias com proteção de `stable`
([ADR-0005](adr/0005-stable-lifecycle-realinhamento-rfc013.md)) o substituiu.
Nenhum Terraform, script ou workflow carrega esse arquivo; ele permanece apenas
como registro.

## Como conferir

Leituras sem efeito colateral:

```sh
aws ecr get-lifecycle-policy --repository-name image-base-go1-26 \
  --query lifecyclePolicyText --output text
aws ecr describe-repositories --repository-names image-base-go1-26
aws ecr describe-images --repository-name image-base-go1-26 --filter tagStatus=TAGGED
```

Compare o JSON da lifecycle com o arquivo versionado depois de normalizar a
ordem das chaves. Divergência é drift de Infra e deve ser tratada pelo fluxo
`Infra - Apply`, nunca por alteração manual.
