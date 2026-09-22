# M08 — Publicar o primeiro candidate Go em DEV

**Dependências:** M00–M07 com os requisitos aplicáveis concluídos; autorização de uma publicação manual.  
**Tipo de trabalho:** Uma execução privilegiada do build DEV; sem stable, recovery ou apply.

## Objetivo desta sessão

Provar o caminho corporativo completo de candidate para o par Go antes de ampliar o catálogo.

## Consultar somente

- Trechos executados de `workflow.yml` e `build-base-images.yml` na revisão escolhida.
- Resultado dos marcos de ARC, identidade, ECR e certificados.
- Logs/artifacts do único run escolhido, sem reler todos os runs do LAB.

Amplie a leitura apenas para a dependência necessária a um achado concreto. Caminhos completos são relativos à raiz do repositório; nomes curtos identificam workflows/scripts já citados no inventário.

## Executar

1. Registre source SHA corporativo, reusable SHA, conta e região. Confirme que a execução em `develop` pede apenas `go1-26` e `go1-26-dev`.
2. Faça preflight do destino ECR e do estado de concorrência. Não disparar outro candidate se um run equivalente já estiver em andamento ou tiver sido concluído com as identidades pretendidas.
3. Mantenha promoção false. Apresente o dispatch e obtenha autorização de uma execução; respeite qualquer negativa do harness sem trocar de ferramenta para contorná-la.
4. Verifique jobs reais: Wolfi, Melange/Apko, duas arquiteturas, Trivy, trust, contrato funcional do par e gate de publicação. Preserve o efeito do gate agregado de certificados; `fail-fast: false` não torna todo gate independente.
5. Confira publicação do mesmo OCI, read-back, assinatura, SPDX e provenance pelos digests. Não repetir build para “verificar” o artefato já publicado.
6. Registre runtime/dev com tag imutável, index digest, manifests por arquitetura, run/attempt/source SHA e timestamps ECR. Confira o par e consumo remoto com a verificação existente.
7. Registre os resultados por etapa e qualquer publicação parcial. Não tocar outros frameworks nem declarar o catálogo completo certificado.

## Critérios de aceite

- Dois candidates corporativos publicados e identificados sem ambiguidade.
- Duas arquiteturas executadas/testadas conforme o contrato, com modo nativo/emulado registrado.
- Gates e evidências remotas do par aprovados.
- Stable e infraestrutura não foram alterados por este marco.

## Quando parar

Falha em origem, trust, scan, contrato, digest ou destino. Permita conclusão das legs independentes conforme o workflow, preserve evidências e não faça push/retag manual de recuperação.

## Resultado específico

Além do bloco curto de entrega definido em [CONTEXTO.md](CONTEXTO.md), informe:

```text
BUILD_RUN_ID_ATTEMPT =
RUNTIME_CANDIDATE_DIGEST =
DEV_CANDIDATE_DIGEST =
CANDIDATE_VERIFICATION =
```

Use valores observados ou `NÃO_VERIFICADO`; não preencha PASS antecipadamente. Atualize somente a linha deste marco e o checkpoint em [PROGRESSO.md](PROGRESSO.md).

## Prompt para a sessão

```text
Leia TODO/marcos-dev/CONTEXTO.md, TODO/marcos-dev/PROGRESSO.md e
TODO/marcos-dev/08-candidate-go-dev.md.
Execute somente M08. Prepare o primeiro candidate Go DEV usando o engine existente.
Depois da autorização, dispare exatamente uma vez e verifique jobs e digests reais.
Não altere stable, não aplique Terraform e não classifique um run verde com etapas
puladas como publicação concluída.
Ao terminar ou bloquear, entregue o resumo curto e atualize PROGRESSO.md.
```

---

**Base documental:** Análise fornecida: seções 5 e Gate 4. Ajustes da revisão: evidência por etapa, gate de trust compartilhado e nenhum PASS por job skipped. Este marco é um roteiro; não comprova que as ações já foram realizadas.
