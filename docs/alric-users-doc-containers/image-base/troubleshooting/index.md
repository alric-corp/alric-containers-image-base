---
title: Diagnóstico por sintoma
sidebar_label: Diagnóstico por sintoma
slug: /troubleshooting
description: Encontre a causa provável de falhas de acesso, inicialização, runtime, TLS, permissões e arquitetura em imagens Distroless, e saiba quando acionar o suporte.
toc_max_heading_level: 2
---

A ausência de `/bin/sh`, Bash, `curl` ou gerenciador de pacotes no runtime é **esperada**. Comece por logs, estado do container, eventos e configuração do workload, sem instalar ferramentas na imagem final. Para diagnóstico em cada ambiente, veja também [Debug no EKS](./eks.md) e [Diagnóstico no ECS e ECS Exec](./ecs.md).

:::warning Cuidado com dados sensíveis
Não compartilhe dumps completos de `docker inspect`, task definitions ou manifestos sem revisão: eles podem conter variáveis sensíveis e segredos.
:::

## Encontre o sintoma {#sintomas}

| Mensagem ou sintoma | Seção |
| --- | --- |
| `manifest unknown` ou `not found` ao baixar a base | [Imagem ou tag não encontrada](#imagem-nao-encontrada) |
| `no basic auth credentials`, `401`, `403` ou `denied` | [Acesso negado ao registry](#acesso-negado) |
| `exec format error` ou `no matching manifest` | [Arquitetura incompatível](#arquitetura) |
| `/bin/sh: not found` ou `executable file not found` | [Ausência de shell](#shell) |
| `no such file or directory` com o executável presente | [A aplicação não inicia](#nao-inicia) |
| `UnsupportedClassVersionError`, `NODE_MODULE_VERSION`, framework .NET não encontrado | [Runtime incompatível](#runtime-incompativel) |
| `x509`, `PKIX path building failed` ou `CERTIFICATE_VERIFY_FAILED` | [Erro de certificado TLS](#tls) |
| `permission denied`, `EACCES` ou `read-only file system` | [Permissões e filesystem](#permissoes) |
| JAR, DLL, módulo ou script da aplicação não encontrado | [Arquivo da aplicação não encontrado](#arquivo-nao-encontrado) |
| `ImagePullBackOff`, `CrashLoopBackOff` ou task parada | [Falhas no EKS ou no ECS](#eks-ecs) |

## Imagem ou tag não encontrada {#imagem-nao-encontrada}

O build falha ao baixar a base com `manifest unknown`, `not found` ou `failed to resolve source metadata`.

- **Causas prováveis:** nome do repositório diferente de `image-base-<framework>`; tag ou digest inexistente no ambiente, já que nem toda variante tem `stable` em todos os ambientes; digest não promovido que expirou; registry ou região diferentes dos configurados na esteira.
- **Como verificar:** compare o nome com o [catálogo](../catalogo/index.md) e confira a [disponibilidade](../catalogo/index.md#disponibilidade) da variante. Com acesso autorizado, `docker buildx imagetools inspect <referencia>` mostra se a referência existe.
- **Como corrigir:** use o nome exato e `stable` ou o digest de um índice promovido. Não crie tags nos repositórios `image-base-*`.
- **Quando acionar o suporte:** a variante de que você precisa não está publicada no seu ambiente, ou um digest aprovado deixou de existir.

## Acesso negado ao registry {#acesso-negado}

O download da base falha com `no basic auth credentials`, `401 Unauthorized`, `403 Forbidden` ou `denied`.

- **Causas prováveis:** a esteira não autenticou no registry de Image Base; token do ECR expirado (vale 12 horas); região diferente da do registry; a esteira não tem permissão de leitura; proxy ou rede bloqueando o acesso.
- **Como verificar:** confira nos logs da esteira se o login no registry acontece antes do build, com o host e a região corretos.
- **Como corrigir:** autentique pela esteira, renove o login e use a região do registry. Não use credenciais pessoais na esteira.
- **Quando acionar o suporte:** a esteira da squad ainda não está habilitada a consumir o registry de Image Base.

## Arquitetura incompatível {#arquitetura}

O container falha ao iniciar com `exec format error`, ou o download falha com `no matching manifest for linux/arm64`.

- **Causas prováveis:** binário ou dependência nativa (CGO, JNI, addons Node.js, wheels Python) compilado para outra arquitetura; imagem final publicada para uma única plataforma; nó do EKS ou task do ECS em outra arquitetura.
- **Como verificar:** `docker image inspect <imagem> --format '{{.Os}}/{{.Architecture}}'` mostra a plataforma de uma imagem local, e `docker buildx imagetools inspect <imagem>` lista as plataformas publicadas. No EKS, `kubectl get nodes -L kubernetes.io/arch`; no ECS, o `runtimePlatform` da task.
- **Como corrigir:** construa para a arquitetura de destino com `--platform`, publique a imagem final com as duas plataformas ou restrinja onde a aplicação roda. Veja [amd64 e arm64](../referencia/arquiteturas.md).
- **Quando acionar o suporte:** a base não contém a plataforma esperada.

## Ausência de shell {#shell}

O container ou a probe falha com `exec: "/bin/sh": stat /bin/sh: no such file or directory`, `/bin/sh: not found` ou `executable file not found in $PATH`.

- **Causas prováveis:** `CMD` ou `ENTRYPOINT` em formato de texto (`CMD java -jar app.jar`); `RUN` no estágio final; script de inicialização com `#!/bin/sh`; probe ou health check com `sh -c` ou `curl`; `kubectl exec -- sh`.
- **Como verificar:** procure no Dockerfile `RUN` no estágio final e instruções em formato de texto; revise probes do Pod e o `healthCheck` da task.
- **Como corrigir:** use o formato de lista (`ENTRYPOINT ["java", "-jar", "/app/app.jar"]`); mova `RUN` para o estágio `-dev`; leve a lógica de scripts para a aplicação; use probes `httpGet`, `tcpSocket` ou `grpc` e health check `CMD` ou do load balancer. Não use a `-dev` como imagem final para ter shell.
- **Quando acionar o suporte:** não é necessário: é o comportamento esperado do runtime.

## A aplicação não inicia {#nao-inicia}

O container encerra logo após iniciar, ou falha com `exec /app/<binario>: no such file or directory` mesmo com o arquivo presente.

- **Causas prováveis:** binário Go dinâmico, compilado com CGO, sem as bibliotecas C que o runtime não tem; script com fim de linha CRLF ou interpretador inexistente; arquivo sem permissão de execução; caminho errado no `ENTRYPOINT`; configuração obrigatória ausente.
- **Como verificar:** leia os logs do container; confira o comando com `docker image inspect <imagem> --format '{{json .Config.Entrypoint}}'`; no host, `file <binario>` indica se o binário é dinâmico.
- **Como corrigir:** compile Go com `CGO_ENABLED=0`; substitua scripts por chamadas diretas ao executável; corrija permissões e caminhos no Dockerfile.
- **Quando acionar o suporte:** a falha se reproduz com um exemplo mínimo que usa somente a base.

## Runtime incompatível {#runtime-incompativel}

A aplicação falha com `UnsupportedClassVersionError` (Java), `was compiled against a different Node.js version using NODE_MODULE_VERSION` (Node.js), `You must install or update .NET to run this application` (.NET) ou erro de importação de extensão nativa (Python).

- **Causas prováveis:** artefato compilado para uma versão diferente da versão da imagem; dependência nativa compilada para outra versão, arquitetura ou biblioteca C.
- **Como verificar:** compare a versão usada no build com a da imagem no [catálogo](../catalogo/index.md). Para ver a versão da base, execute o binário diretamente, por exemplo `docker run --rm --entrypoint java <registry-image-base>/image-base-java21:stable -version`.
- **Como corrigir:** use a `-dev` e o runtime da mesma família e versão; recompile as dependências nativas no estágio `-dev`.
- **Quando acionar o suporte:** a versão do runtime na imagem diverge do catálogo.

## Erro de certificado TLS {#tls}

Chamadas HTTPS falham com `x509: certificate signed by unknown authority` (Go), `PKIX path building failed` (Java), `CERTIFICATE_VERIFY_FAILED` (Python), `UNABLE_TO_GET_ISSUER_CERT_LOCALLY` ou `SELF_SIGNED_CERT_IN_CHAIN` (Node.js) ou `The remote certificate is invalid` (.NET).

- **Causas prováveis:** serviço com certificado emitido por CA corporativa, ainda não incluída nas imagens publicadas; cadeia incompleta no servidor; hostname diferente do certificado; certificado expirado ou relógio incorreto; aplicação usando um trust store próprio.
- **Como verificar:** de uma máquina com ferramentas, `openssl s_client -connect <host>:443 -servername <host> -showcerts` mostra a cadeia apresentada. Confira também qual trust store o cliente usa, como `-Djavax.net.ssl.trustStore` ou `REQUESTS_CA_BUNDLE`.
- **Como corrigir:** remova trust stores próprios desnecessários e corrija hostname, cadeia ou validade no servidor. **Não** desabilite a verificação (`curl -k`, `verify=False`, `NODE_TLS_REJECT_UNAUTHORIZED=0` ou callbacks que aceitam qualquer certificado).
- **Quando acionar o suporte:** a CA corporativa de que o serviço precisa está ausente, ou a falha se reproduz com a configuração padrão da base. Veja [Certificados e HTTPS](../seguranca/certificados.md).

## Permissões e filesystem {#permissoes}

A aplicação falha com `permission denied`, `EACCES` ou `Read-only file system`.

- **Causas prováveis:** arquivos copiados sem `--chown=10000:10000`; a aplicação grava fora de um volume gravável quando a raiz é somente leitura; volume montado com dono ou permissão incompatível com o UID `10000`; porta abaixo de 1024, que pode exigir privilégio.
- **Como verificar:** identifique nos logs o caminho que falhou. Para listar dono e permissão sem shell: `docker create --name inspecao <imagem>`, `docker cp inspecao:/app - | tar -tvf -` e `docker rm inspecao`.
- **Como corrigir:** use `COPY --chown=10000:10000`; configure diretórios graváveis específicos (`--tmpfs`, `emptyDir` ou volume) e aponte a aplicação para eles; use portas acima de 1024, como `8080`. Não mude para root como primeira resposta.
- **Quando acionar o suporte:** um diretório da própria base, como `/app` ou `/tmp`, está com dono ou permissão incorretos.

## Arquivo da aplicação não encontrado {#arquivo-nao-encontrado}

A aplicação falha com `Unable to access jarfile` (Java), `The application to execute does not exist` (.NET), `Cannot find module` (Node.js) ou `can't open file` (Python).

- **Causas prováveis:** caminho do `COPY` diferente do usado no `ENTRYPOINT`; saída do build em outro diretório; `.dockerignore` excluindo o artefato; diretório de trabalho diferente do esperado.
- **Como verificar:** liste o conteúdo com `docker cp` como em [Permissões e filesystem](#permissoes) e compare com `docker image inspect <imagem> --format '{{json .Config.Entrypoint}} {{.Config.WorkingDir}}'`.
- **Como corrigir:** alinhe os caminhos e use caminhos absolutos no `ENTRYPOINT`.
- **Quando acionar o suporte:** normalmente não é necessário.

## Falhas no EKS ou no ECS {#eks-ecs}

- **`ImagePullBackOff` ou `CannotPullContainerError`:** o problema está na imagem **da aplicação**, não na base. Confira a referência, as permissões de pull do workload e a rede até o registry da aplicação.
- **`CrashLoopBackOff` ou task parada logo após iniciar:** leia os logs do container e use as seções acima para a mensagem encontrada.
- **Probe ou health check falhando:** confira se ele depende de shell e se o endpoint, a porta e o tempo de inicialização estão corretos.

Diagnóstico detalhado por ambiente: [Debug no EKS](./eks.md) e [Diagnóstico no ECS e ECS Exec](./ecs.md).
