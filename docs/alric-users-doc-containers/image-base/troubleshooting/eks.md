---
title: Debug no EKS
sidebar_label: Debug no EKS
description: Investigue Pods com runtime Distroless por estado, eventos e logs, e use containers efêmeros autorizados sem alterar a imagem da aplicação.
---

Use os comandos desta página somente no namespace e no contexto autorizados para você.

## Comece pelo que o cluster já mostra {#primeiros-passos}

```bash
kubectl get pods -n <namespace>
kubectl describe pod <pod> -n <namespace>
kubectl logs <pod> -n <namespace> -c <container>
kubectl logs <pod> -n <namespace> -c <container> --previous
kubectl get events -n <namespace> --sort-by=.lastTimestamp
```

| Estado ou evento | Causa provável |
| --- | --- |
| `ImagePullBackOff` ou `ErrImagePull` | Referência ou permissão de pull da imagem **da aplicação**. |
| `CrashLoopBackOff` | A aplicação encerra ao iniciar: veja `kubectl logs --previous` e o [diagnóstico por sintoma](./index.md). |
| `CreateContainerConfigError` | Secret ou ConfigMap ausente na configuração do Pod. |
| `OOMKilled` | Memória insuficiente para a aplicação. |
| `Readiness probe failed` ou `Liveness probe failed` | Endpoint, porta ou tempo de inicialização; probes `exec` com `sh` ou `curl` falham no runtime. |

## `kubectl exec` não abre shell {#kubectl-exec}

`kubectl exec -it <pod> -- sh` falha no runtime Distroless, porque não há shell. `kubectl exec` só executa binários que existem na imagem, por exemplo `kubectl exec <pod> -n <namespace> -- java -version`. Para investigar com ferramentas, use um container efêmero.

## Container efêmero de diagnóstico {#container-efemero}

Para diagnóstico interativo em Kubernetes, use o toolkit corporativo de troubleshooting. O container efêmero fornece ferramentas separadamente (`kubectl`, `helm`, `tcpdump`, `curl`, `jq` etc.) e não exige transformar a aplicação em uma imagem de troubleshooting.

**Itaú EV3 Container K8S Tools** é a imagem Alpine Linux com toolkit completo para troubleshooting. Inclui ferramentas de rede, Kubernetes, AWS CLI, certificados corporativos pré-configurados e autocomplete habilitado. Consulte o repositório para instruções completas de uso com Deployment, Ephemeral Container ou Docker:

**Repositório:** [itau-corp/itau-ev3-container-k8s-tools](https://github.com/itau-corp/itau-ev3-container-k8s-tools)

**Exemplo rápido — Ephemeral Container:**

```bash
kubectl debug -it <POD_NAME> -n <namespace> \
  --image=itau-ev3-docker.artifactory.prod.aws.cloud.ihf/itau-corp-itau-ev3-container-k8s-tools:v0.2.0-f7df65b \
  --target=<CONTAINER_NAME>
```

- `--target` recebe o **nome do container**, que pode ser diferente do nome do Pod, e permite ver os processos desse container quando o runtime do cluster oferece suporte.
- `--profile` define as permissões do container de diagnóstico: `general` (padrão), `baseline`, `restricted`, `netadmin` ou `sysadmin`. Use o perfil mínimo necessário, como `netadmin` para captura `tcpdump`. O equivalente a privilegiado é `--profile=sysadmin`, somente se necessário e autorizado pelas políticas do cluster: o `kubectl debug` não tem a opção `--privileged`.
- Quando o Pod inteiro roda com usuário não-root, algumas capabilities concedidas pelo perfil podem não funcionar.
- Containers efêmeros não podem ser removidos: permanecem até o Pod ser recriado.
- O uso depende de autorização, como RBAC para `pods/ephemeralcontainers`, e das políticas de segurança do cluster.

Confira a versão da imagem no repositório. Acesse o README do repositório para instruções detalhadas sobre deployment privilegiado, captura `tcpdump` e lista completa de ferramentas.

Referência: [Kubernetes: debug de Pods em execução](https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/).

## O que evitar {#evite}

- Instalar ferramentas na imagem final ou trocar para a variante `-dev` em produção.
- Mudar para `runAsUser: 0` ou `USER root` como primeira resposta.
- Usar `--profile=sysadmin` sem autorização.
- Compartilhar a saída completa de `kubectl describe` ou de manifestos sem revisar variáveis sensíveis.
