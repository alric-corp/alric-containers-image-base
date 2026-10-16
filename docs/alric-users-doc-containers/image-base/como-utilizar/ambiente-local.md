---
title: Executar e validar localmente
sidebar_label: Ambiente local
description: Construa e execute a imagem da aplicação na sua máquina com o mesmo perfil de segurança usado nos testes da plataforma.
---

Valide localmente a imagem final da aplicação antes de enviá-la pela esteira. A imagem roda sem shell, então toda verificação é feita **de fora do container**.

## Pré-requisitos {#pre-requisitos}

- Docker com BuildKit: Docker Desktop ou Docker Engine com Buildx.
- Acesso de leitura ao registry de Image Base, **se ele for autorizado para você**. O consumo previsto é pela esteira da squad; o acesso a partir da sua máquina depende da política do seu ambiente.

Com acesso autorizado, autentique o Docker no Amazon ECR do registry de Image Base:

```bash
aws ecr get-login-password --region sa-east-1 \
  | docker login --username AWS --password-stdin 758421218117.dkr.ecr.sa-east-1.amazonaws.com
```

:::note Sem acesso local ao registry
Não contorne o controle de acesso copiando imagens ou credenciais de terceiros. Construa pela esteira da squad e valide a imagem final no ambiente autorizado.
:::

## Construir {#construir}

```bash
docker build --pull -t minha-app:local .
```

`--pull` faz o build consultar a versão atual da tag da base, em vez de reutilizar uma cópia local antiga.

## Executar {#executar}

Execute com os mesmos controles que a plataforma usa nos testes das aplicações de referência: raiz somente leitura, `/tmp` gravável em memória, nenhuma capability e sem escalonamento de privilégio.

```bash
docker run --rm --name minha-app \
  --read-only --tmpfs /tmp \
  --cap-drop ALL --security-opt no-new-privileges \
  -p 127.0.0.1:8080:8080 \
  minha-app:local
```

Ajuste a porta à sua aplicação. Se ela grava em outro diretório, monte um `--tmpfs` também para ele e configure o mesmo volume no [EKS](./eks.md#security-context) ou no [ECS](./ecs.md#task-definition).

## Validar {#validar}

Em outro terminal:

```bash
curl -fsS http://127.0.0.1:8080/<endpoint-de-saude>
docker logs minha-app
docker image inspect minha-app:local --format '{{.Config.User}} {{.Os}}/{{.Architecture}}'
docker stop --timeout 15 minha-app
```

Confira se:

- a aplicação responde e escreve logs na saída padrão;
- o usuário é `10000`, herdado da base;
- a arquitetura é a do ambiente de destino;
- `docker stop` encerra a aplicação em até 15 segundos. Como processo principal do container, a aplicação recebe o `SIGTERM` diretamente: alguns runtimes, como Node.js e Python, só encerram se a aplicação tratar esse sinal.

Para conferir arquivos e permissões sem shell, copie o conteúdo da imagem para fora:

```bash
docker create --name inspecao minha-app:local
docker cp inspecao:/app - | tar -tvf -
docker rm inspecao
```

## Testar a outra arquitetura {#arquitetura}

```bash
docker build --pull --platform linux/arm64 -t minha-app:arm64 .
docker run --rm --platform linux/arm64 --read-only --tmpfs /tmp \
  --cap-drop ALL --security-opt no-new-privileges \
  -p 127.0.0.1:8080:8080 minha-app:arm64
```

Em uma máquina amd64, a imagem arm64 roda por emulação, e o inverso também vale. A emulação revela erros de formato e de dependências nativas, mas não substitui o teste na arquitetura real. Veja [amd64 e arm64](../referencia/arquiteturas.md).

## Problemas frequentes {#problemas}

| Sintoma | Veja |
| --- | --- |
| `401`, `403` ou `no basic auth credentials` ao baixar a base | [Acesso negado ao registry](../troubleshooting/index.md#acesso-negado) |
| `manifest unknown` ou `not found` | [Imagem ou tag não encontrada](../troubleshooting/index.md#imagem-nao-encontrada) |
| `exec format error` | [Arquitetura incompatível](../troubleshooting/index.md#arquitetura) |
| `/bin/sh: not found` ou `executable file not found` | [Ausência de shell](../troubleshooting/index.md#shell) |
| `permission denied` ou `read-only file system` | [Permissões e filesystem](../troubleshooting/index.md#permissoes) |
| Erro de certificado em chamadas HTTPS | [Erro de certificado TLS](../troubleshooting/index.md#tls) |
