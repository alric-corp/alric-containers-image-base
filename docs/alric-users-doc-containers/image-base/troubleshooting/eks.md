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

Um container efêmero acrescenta ferramentas ao Pod em execução sem alterar a imagem da aplicação:

```bash
kubectl debug -it <pod> -n <namespace> \
  --image=<imagem-de-diagnostico-autorizada> \
  --target=<container>
```

- `--target` recebe o **nome do container**, que pode ser diferente do nome do Pod, e permite ver os processos desse container quando o runtime do cluster oferece suporte.
- `--profile` define as permissões do container de diagnóstico: `general` (padrão), `baseline`, `restricted`, `netadmin` ou `sysadmin`. Use o perfil mínimo necessário, como `netadmin` para captura de rede, e `sysadmin` somente com autorização. O `kubectl debug` não tem a opção `--privileged`.
- Quando o Pod inteiro roda com usuário não-root, algumas capabilities concedidas pelo perfil podem não funcionar.
- Containers efêmeros não podem ser removidos: permanecem até o Pod ser recriado.
- O uso depende de autorização, como RBAC para `pods/ephemeralcontainers`, e das políticas de segurança do cluster.

Use a imagem de diagnóstico autorizada para o seu cluster, como o toolkit corporativo de troubleshooting, mantido como produto separado das imagens base, com ferramentas de rede, Kubernetes, AWS CLI e certificados corporativos. Confirme a referência e a versão autorizadas com o suporte da plataforma.

Referência: [Kubernetes: debug de Pods em execução](https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/).

## O que evitar {#evite}

- Instalar ferramentas na imagem final ou trocar para a variante `-dev` em produção.
- Mudar para `runAsUser: 0` ou `USER root` como primeira resposta.
- Usar `--profile=sysadmin` sem autorização.
- Compartilhar a saída completa de `kubectl describe` ou de manifestos sem revisar variáveis sensíveis.
