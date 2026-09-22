# M03 — Provar capacidades de build e rede do ARC

**Dependências:** M02.  
**Tipo de trabalho:** Diagnóstico e smoke de containers; sem ECR write nem alteração do cluster.

## Objetivo desta sessão

Verificar se os runners escolhidos oferecem as ferramentas e capacidades necessárias, e não apenas CPU/memória suficientes.

## Consultar somente

- Reusable no SHA consumido: `validate-apko-images.yml` e `test-runtime-images.yml`.
- `.github/workflows/image-trust.yml` e os trechos de Docker/QEMU/Buildx dos jobs consumidores.
- Contrato do runner corporativo, se disponível, e somente logs dos smokes necessários.

Amplie a leitura apenas para a dependência necessária a um achado concreto. Caminhos completos são relativos à raiz do repositório; nomes curtos identificam workflows/scripts já citados no inventário.

## Executar

1. Liste por job as dependências efetivas: Python, Git, Bash, Make, Docker, Buildx/BuildKit, ferramentas de verificação, armazenamento e rede. Não instalar tudo automaticamente.
2. Identifique a arquitetura do daemon/nó e como containers serão executados. Não assumir que “rodar em Kubernetes” já entrega um daemon Docker compatível com os comandos atuais.
3. Confirme o mecanismo aprovado de amd64/arm64. Quando houver emulação, registre-a como emulação; manifest multiarch não comprova execução.
4. Inspecione necessidades de Melange e QEMU quanto a privilégios. Não habilite DinD privilegiado, binfmt ou montagens de socket sem aprovação da plataforma.
5. Faça, mediante autorização, um smoke barato com imagem/ferramenta aprovada e pin já governado. Não reconstrua o catálogo. ECR autenticado pode permanecer dependência do M04/M08; conectividade não é autorização de pull.
6. Registre DNS/TLS/egress necessários para GitHub, artifacts, registries e serviços de assinatura usados pelo código. Não desative TLS nem trate CA da imagem final como solução automática para o host.
7. Dimensione por job. Proponha menor classe suficiente e paralelismo inicial limitado, sem transformar o workflow FULL inteiro em uma escolha única de runner.

## Critérios de aceite

- Ferramentas e execução de containers confirmadas ou lacunas explicitadas.
- Estratégia real para as duas arquiteturas definida.
- Privilégios, rede e armazenamento aprovados para os jobs que os exigem.
- Nenhuma afirmação de execução nativa onde houve emulação.

## Quando parar

Capacidade necessária não aprovada ou indisponível: registre a dependência de Infra. Não aumente permissões, instale componentes de cluster ou contorne o proxy.

## Resultado específico

Além do bloco curto de entrega definido em [CONTEXTO.md](CONTEXTO.md), informe:

```text
DOCKER_EXECUTION =
MULTIARCH_EXECUTION_MODE =
NETWORK_TRUST_READINESS =
RUNNER_CAPABILITY_GAPS =
```

Use valores observados ou `NÃO_VERIFICADO`; não preencha PASS antecipadamente. Atualize somente a linha deste marco e o checkpoint em [PROGRESSO.md](PROGRESSO.md).

## Prompt para a sessão

```text
Leia TODO/marcos-dev/CONTEXTO.md, TODO/marcos-dev/PROGRESSO.md e
TODO/marcos-dev/03-arc-ferramentas-arquiteturas-e-rede.md.
Execute somente M03. Valide apenas ferramentas, execução de containers, arquiteturas
e rede do ARC. Reutilize os pins existentes. Não mude o cluster, não publique
imagens e não rode o catálogo completo. Separe capacidade confirmada de dependência
ainda não testada.
Ao terminar ou bloquear, entregue o resumo curto e atualize PROGRESSO.md.
```

---

**Base documental:** Análise fornecida: seções 5.2, 8.2 e 18. Ajustes da revisão: capacidade por job, distinção de modos ARC e limites de paralelismo. Este marco é um roteiro; não comprova que as ações já foram realizadas.
