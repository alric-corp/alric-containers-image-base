---
title: Diagnóstico no ECS e ECS Exec
sidebar_label: ECS e ECS Exec
description: Investigue tasks com runtime Distroless por eventos, logs e motivo de parada, e entenda os pré-requisitos e os limites do ECS Exec.
---

Use os comandos desta página somente com as permissões e no ambiente autorizados para você.

## Comece pelos sinais do ECS {#primeiros-passos}

```bash
aws ecs describe-services --cluster <cluster> --services <servico> \
  --query 'services[0].events[:10].message'
aws ecs list-tasks --cluster <cluster> --service-name <servico> --desired-status STOPPED
aws ecs describe-tasks --cluster <cluster> --tasks <task-id> \
  --query 'tasks[0].{status:lastStatus,codigo:stopCode,motivo:stoppedReason,containers:containers[].{nome:name,saida:exitCode,motivo:reason,saude:healthStatus}}'
aws logs tail <log-group> --since 30m
```

| Sinal | Causa provável |
| --- | --- |
| `CannotPullContainerError` | Referência da imagem **da aplicação**, permissão da role de execução da task ou rede até o registry. |
| `Essential container in task exited` com código `137` | Encerramento forçado: falta de memória ou aplicação que não terminou dentro do `stopTimeout`. |
| `Essential container in task exited` com outro código | Erro da aplicação: leia os logs e o [diagnóstico por sintoma](./index.md). |
| `Task failed container health checks` | Health check `CMD-SHELL` (o runtime não tem shell), endpoint, porta ou `startPeriod` incorretos. |
| `ResourceInitializationError` | Configuração da task, como secrets, logs ou rede, e não a imagem base. |

## ECS Exec com runtime Distroless {#ecs-exec}

O ECS Exec executa comandos em um container em execução por meio do AWS Systems Manager. No runtime Distroless, o uso é limitado:

| Limite | Efeito no runtime Distroless |
| --- | --- |
| Não há shell | `--command "/bin/sh"` falha. Só é possível executar binários que existem na imagem. |
| Raiz somente leitura não é suportada | Tasks com `readonlyRootFilesystem: true` não aceitam ECS Exec. |
| Comandos rodam como `root` | O agente do Systems Manager e os comandos rodam como root, mesmo com o container configurado para o UID `10000`. |
| Registro da sessão exige `script` e `cat` | O runtime não tem esses binários: a saída da sessão não é registrada no CloudWatch Logs nem no S3. Confira se isso atende aos requisitos de auditoria do seu ambiente. |

### Pré-requisitos {#ecs-exec-pre-requisitos}

- ECS Exec habilitado no serviço ou na task com `--enable-execute-command`. Tasks que já estavam em execução não passam a aceitá-lo: é preciso um novo deploy.
- Role da task com as permissões do Systems Manager exigidas pelo ECS Exec.
- AWS CLI 2.3.6 ou superior e o Session Manager plugin instalados na sua máquina.
- Fargate na plataforma 1.4.0 ou superior e acesso de rede ao Systems Manager.
- Autorização da governança do ambiente: o ECS Exec dá acesso interativo à task.

### Executar um comando {#ecs-exec-comando}

Confirme que o agente está pronto (`ExecuteCommandAgent` com status `RUNNING`) e execute um binário que existe na imagem:

```bash
aws ecs describe-tasks --cluster <cluster> --tasks <task-id> \
  --query 'tasks[0].containers[].managedAgents'

aws ecs execute-command --cluster <cluster> --task <task-id> \
  --container <container> --interactive \
  --command "<binario-da-imagem> <argumentos>"
```

Exemplos de binários presentes no runtime: `java -version` (Java), `node --version` (Node.js), `dotnet --info` (.NET), `python3 --version` (Python) e o próprio binário da aplicação (Go).

Referência: [AWS: ECS Exec](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-exec.html).

## Quando precisar de ferramentas {#ferramentas}

Para investigar rede, DNS ou TLS a partir do contexto da aplicação, use uma imagem de diagnóstico autorizada em uma task separada, nas mesmas subnets e security groups, ou como container adicional não essencial em uma nova revisão da task definition, conforme a governança do seu ambiente. Não altere a imagem da aplicação e remova o container de diagnóstico ao terminar.
