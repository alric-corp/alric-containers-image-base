---
title: Usar no Amazon ECS
sidebar_label: Amazon ECS
description: Como a imagem base participa do build e do deploy no ECS, com task definition, health checks, arquitetura, raiz somente leitura e validação.
---

## Imagem base e imagem da aplicação {#imagens}

A imagem base entra no **build**. O ECS executa a **imagem final da aplicação**, construída e publicada pela esteira da squad.

- O campo `image` da task definition referencia a **sua** imagem (`<registry-da-aplicacao>/<aplicacao>`), nunca um repositório `image-base-*`.
- Uma nova versão da base não altera tasks em execução. A correção chega com rebuild, testes e um novo deploy do serviço. Veja [Atualizações e CVEs](../seguranca/atualizacoes.md).

## Task definition {#task-definition}

Trecho de uma task definition no Fargate:

```json title="Task definition (trecho)"
{
  "runtimePlatform": {
    "cpuArchitecture": "ARM64",
    "operatingSystemFamily": "LINUX"
  },
  "containerDefinitions": [
    {
      "name": "minha-app",
      "image": "<registry-da-aplicacao>/minha-app:<tag>",
      "essential": true,
      "portMappings": [{ "containerPort": 8080 }],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "<log-group>",
          "awslogs-region": "<regiao>",
          "awslogs-stream-prefix": "minha-app"
        }
      }
    }
  ]
}
```

- Não é preciso definir `user`: a imagem já roda como UID `10000`, herdado da base. Não troque para `root`.
- A aplicação deve escrever logs na saída padrão; o driver `awslogs` envia essa saída ao CloudWatch Logs.

### Raiz somente leitura {#raiz-somente-leitura}

`readonlyRootFilesystem: true` é a configuração recomendada, como no EKS, mas exige um volume gravável para cada diretório em que a aplicação grava (`mountPoints` no container e `volumes` na task). Antes de adotar, considere:

- **Permissão do volume no Fargate:** o volume é criado com dono `root` e permissão `0755`, sem gravação para o UID `10000`, a menos que a imagem declare `VOLUME` para o mesmo caminho, com o diretório já pertencente ao usuário da aplicação. Veja [AWS: bind mounts](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/bind-mounts.html).
- **ECS Exec:** não funciona com raiz somente leitura. Veja [Diagnóstico no ECS](../troubleshooting/ecs.md#ecs-exec).

Valide a gravação em um ambiente de testes antes de levar a configuração para produção.

## Health check {#health-check}

O health check `CMD-SHELL` executa o comando com o shell do container, que não existe no runtime: com ele, a task falha nas verificações. Use uma destas opções:

- o health check do load balancer (target group), por HTTP;
- `CMD` com um executável que exista na imagem, como um subcomando de verificação da própria aplicação:

```json title="containerDefinitions[].healthCheck"
{
  "command": ["CMD", "/app/servidor", "healthcheck"],
  "interval": 30,
  "timeout": 5,
  "retries": 3,
  "startPeriod": 30
}
```

## Arquitetura {#arquitetura}

- **Fargate:** `runtimePlatform.cpuArchitecture` aceita `X86_64` (padrão) ou `ARM64`. Todas as task definitions de um mesmo serviço precisam usar o mesmo valor, e a imagem final precisa conter essa plataforma.
- **EC2:** a arquitetura vem das instâncias do cluster. Publique a imagem final com as plataformas dessas instâncias.

Uma task em arquitetura incompatível falha com `exec format error`. Veja [amd64 e arm64](../referencia/arquiteturas.md).

## Encerramento {#encerramento}

O ECS envia `SIGTERM` ao container e aguarda o `stopTimeout` (30 segundos por padrão no Fargate, até 120) antes de encerrá-lo à força. Trate o sinal na aplicação: Node.js e Python, por exemplo, ignoram o `SIGTERM` como processo principal do container se a aplicação não registrar um handler.

## Validar o deploy {#validar}

Use somente com as permissões e no ambiente autorizados:

```bash
aws ecs describe-services --cluster <cluster> --services <servico> \
  --query 'services[0].{status:status,emExecucao:runningCount,desejado:desiredCount,eventos:events[:5].message}'
aws ecs describe-tasks --cluster <cluster> --tasks <task-id> \
  --query 'tasks[0].{status:lastStatus,motivo:stoppedReason,containers:containers[].{nome:name,saida:exitCode,motivo:reason}}'
aws logs tail <log-group> --since 30m
```

Se algo falhar, siga para [Diagnóstico no ECS e ECS Exec](../troubleshooting/ecs.md).
