---
title: Ajuda e suporte
sidebar_label: Ajuda e suporte
description: Como pedir ajuda ao Containers Products, o que informar na solicitação, o checklist de adoção e as referências externas.
---

## Como pedir ajuda {#como-pedir-ajuda}

O responsável pelo produto é o **Containers Products**. O atendimento é feito por **RITM no ServiceNow**: [abrir solicitação](https://itau.service-now.com/tech?id=sc_cat_item&sys_id=e695fc1e1bd4fcd0f7f10f60f54bcb9a&table=sc_cat_item&searchTerm=container).

Antes de abrir a solicitação, consulte o [diagnóstico por sintoma](./troubleshooting/index.md) e as [perguntas frequentes](./referencia/faq.md).

## O que informar {#o-que-informar}

- A imagem usada, por exemplo `image-base-java21:stable`.
- O ambiente (local, EKS ou ECS), a região e a arquitetura.
- A mensagem de erro completa e a etapa em que ocorre: build, download, inicialização ou execução.
- O trecho relevante do Dockerfile e o que você já verificou.

**Não inclua** tokens, senhas, variáveis sensíveis nem dumps completos de `docker inspect`, task definitions ou manifestos sem revisão.

## Checklist de adoção {#checklist-de-adocao}

- [ ] Esteira da squad habilitada a consumir o registry corporativo de Image Base.
- [ ] Dockerfile usa a tag `stable`; se compila com `-dev`, estágio de build e runtime da mesma família e versão.
- [ ] Artefato final deriva do runtime, sem toolchain desnecessária.
- [ ] Testes, scan da aplicação, TLS, permissões de escrita e shutdown validados.
- [ ] Arquiteturas necessárias realmente construídas e executadas.
- [ ] Processo de rebuild da aplicação definido para incorporar atualizações da base.
- [ ] Deploy/rollback e canal de suporte conhecidos.

## Sugerir uma correção nesta documentação {#sugerir-correcao}

Use o link **Editar esta página**, no fim de cada página, para propor a alteração no repositório da documentação.

## Referências externas {#referencias-externas}

Documentação oficial: [Dockerfile](https://docs.docker.com/reference/dockerfile/), [boas práticas de build](https://docs.docker.com/build/building/best-practices/), [secrets de build](https://docs.docker.com/build/building/secrets/), [multi-platform](https://docs.docker.com/build/building/multi-platform/), [Kubernetes: security context](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/), [Kubernetes: debug de Pods](https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/) e [Amazon ECS Exec](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html).
