---
title: Ajuda e suporte
sidebar_label: Ajuda e suporte
description: Como pedir ajuda ao Containers Products, o que informar na solicitação, o checklist de adoção e as referências externas.
---

## Como pedir ajuda {#como-pedir-ajuda}

O responsável pelo produto é o **Containers Products**. O atendimento é feito por solicitação **RITM no ServiceNow**, direcionada ao Containers Products.

Antes de abrir a solicitação, consulte o [diagnóstico por sintoma](./troubleshooting/index.md) e as [perguntas frequentes](./referencia/faq.md).

## O que informar {#o-que-informar}

- A imagem e a referência exata usadas: `image-base-<framework>` com a tag ou o digest.
- O ambiente (local, EKS ou ECS), a região e a arquitetura.
- A mensagem de erro completa e a etapa em que ocorre: build, download, inicialização ou execução.
- O trecho relevante do Dockerfile e o que você já verificou.

**Não inclua** tokens, senhas, variáveis sensíveis nem dumps completos de `docker inspect`, task definitions ou manifestos sem revisão.

## Checklist de adoção {#checklist-de-adocao}

- [ ] Esteira da squad habilitada a consumir o registry de Image Base.
- [ ] Variante confirmada como [publicada e liberada](./catalogo/index.md#disponibilidade) no ambiente de destino.
- [ ] Dockerfile com o runtime no estágio final; com `-dev`, a mesma família e versão nos dois estágios.
- [ ] Referência da base definida (`stable` ou digest promovido) e processo de atualização combinado.
- [ ] Imagem final derivada do runtime, sem toolchain desnecessário.
- [ ] Testes, scan da imagem final, TLS, permissões de escrita e encerramento validados.
- [ ] Arquiteturas necessárias construídas e executadas.
- [ ] Processo de rebuild definido para incorporar as atualizações da base.
- [ ] Deploy, rollback e canal de suporte conhecidos.

## Sugerir uma correção nesta documentação {#sugerir-correcao}

Use o link **Editar esta página**, no fim de cada página, para propor a alteração no repositório da documentação.

## Referências externas {#referencias-externas}

Documentação oficial: [Dockerfile](https://docs.docker.com/reference/dockerfile/), [boas práticas de build](https://docs.docker.com/build/building/best-practices/), [secrets de build](https://docs.docker.com/build/building/secrets/), [multi-platform](https://docs.docker.com/build/building/multi-platform/), [Kubernetes: security context](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/), [Kubernetes: debug de Pods](https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/) e [Amazon ECS Exec](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html).
