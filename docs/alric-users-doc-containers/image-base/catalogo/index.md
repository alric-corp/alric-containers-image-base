---
title: Catálogo de imagens
sidebar_label: Imagens disponíveis
slug: /catalogo
description: Linguagens, versões e variantes de Image Base, o que cada imagem contém e como escolher a imagem certa.
---

O catálogo reúne **16 imagens: nove runtimes e sete variantes `-dev`**, para Java, Go, .NET, Node.js e Python. Todas seguem a mesma convenção: repositório `image-base-<framework>`, usuário não-root com UID/GID `10000`, diretório de trabalho `/app` e as plataformas `linux/amd64` e `linux/arm64`.

## Como escolher {#como-escolher}

1. Parta da linguagem e da versão principal que sua aplicação **já usa**. Para a primeira migração, preserve a linha de runtime que sua aplicação já suporta: trocar a imagem base e a versão principal da linguagem ao mesmo tempo dificulta identificar a causa de incompatibilidades.
2. Use a imagem **runtime** no estágio final do Dockerfile.
3. Se a compilação ou a instalação de dependências acontece dentro do Docker, use a **`-dev` da mesma família e versão** no estágio de build. Veja [Runtime e -dev](./runtime-dev.md).

## Imagens {#imagens}

| Aplicação | Imagem de execução | Imagem de construção/preparação |
| --- | --- | --- |
| Java 21 | `image-base-java21:stable` | `image-base-java21-dev:stable` |
| Java 25 | `image-base-java25:stable` | `image-base-java25-dev:stable` |
| Go 1.25 | `image-base-go1-25:stable` | `image-base-go1-25-dev:stable` |
| Go 1.26 | `image-base-go1-26:stable` | `image-base-go1-26-dev:stable` |
| .NET 10 / ASP.NET Core | `image-base-dotnet10:stable` | `image-base-dotnet10-dev:stable` |
| Node.js 22 | `image-base-nodejs22:stable` | `image-base-nodejs22-dev:stable` |
| Node.js 24 | `image-base-nodejs24:stable` | `image-base-nodejs24-dev:stable` |
| Python 3.13 | `image-base-python3-13:stable` | Sem variante `-dev` neste catálogo |
| Python 3.14 | `image-base-python3-14:stable` | Sem variante `-dev` neste catálogo |

Para cada framework disponível no catálogo, a tag `stable` identifica a versão atualmente disponibilizada pelo Containers Products para consumo. Os exemplos desta documentação utilizam essa tag.

Não crie tags nos repositórios `image-base-*`: eles são mantidos pela plataforma.

## O que cada imagem contém {#conteudo}

| | Runtime | `-dev` |
| --- | --- | --- |
| Finalidade | Executar a aplicação: é a base da imagem final. | Construir a aplicação no estágio de build. |
| Linguagem | JRE, ASP.NET Core Runtime, Node.js ou Python. Go não tem runtime: a imagem recebe o binário estático. | Toolchain completo: JDK, SDK .NET, Go ou Node.js com npm. |
| Shell e gerenciador de pacotes | Não. | Shell `/bin/sh` (BusyBox), para `RUN` e wrappers como `mvnw` e `gradlew`. Sem gerenciador de pacotes. |
| Base comum | Certificados de CA, dados de fuso horário (`tzdata`), usuário UID/GID `10000` (`spring` no Java, `appuser` nas demais) e diretório `/app` pertencente a esse usuário. | Igual ao runtime. |

Detalhes por família:

- **Go:** o runtime não tem o toolchain nem bibliotecas C. Compile binários estáticos, com `CGO_ENABLED=0`.
- **Java:** o runtime tem o JRE, sem `javac`; a `-dev` tem o JDK.
- **.NET:** o runtime tem o ASP.NET Core Runtime, sem o SDK; a `-dev` tem o SDK.
- **Node.js:** o runtime tem o Node.js, sem npm; a `-dev` tem o npm.
- **Python:** somente runtime. Prepare as dependências fora da imagem final, como mostra o [exemplo do Dockerfile](../como-utilizar/dockerfile.mdx#artefato-pronto).
