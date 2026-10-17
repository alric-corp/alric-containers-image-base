---
title: Runtime e variante -dev
sidebar_label: Runtime e -dev
description: Quando usar a imagem runtime, quando usar a variante -dev e como combinar as duas em um build multi-stage.
---

**Runtime** é a imagem que executa sua aplicação. **`-dev`** é a variante com ferramentas de construção (JDK, SDK .NET, compilador Go ou npm), usada somente no estágio de build quando sua squad compila ou instala dependências dentro do Docker.

## Qual usar {#qual-usar}

- **A esteira já produz o artefato** (JAR, binário Go, saída do `dotnet publish` ou bundle Node.js): o Dockerfile precisa apenas do runtime. Copie o artefato para a imagem.
- **A compilação acontece no Docker:** use a `-dev` no estágio de build e o runtime **da mesma família e versão** no estágio final, por exemplo `image-base-java21-dev` no build e `image-base-java21` no final.

:::warning `-dev` não é um ambiente
É uma variante de imagem para o estágio de construção. A imagem final usa sempre a variante runtime. Não use a `-dev` como imagem final para contornar a ausência de shell ou de ferramentas.
:::

## Por família {#por-familia}

| Família | A `-dev` acrescenta | Uso típico no build | Estágio final |
| --- | --- | --- | --- |
| Java 21 e 25 | JDK e shell | `javac`, `./mvnw`, `./gradlew` | JRE: `java -jar /app/app.jar` |
| Go 1.26 | Toolchain Go e shell | `go build` com `CGO_ENABLED=0` | Somente o binário estático |
| .NET 10 | SDK .NET e shell | `dotnet restore` e `dotnet publish` | ASP.NET Core Runtime: `dotnet /app/<app>.dll` |
| Node.js 22 e 24 | npm e shell | `npm ci` e o build do projeto | Node.js, sem npm |
| Python 3.13 e 3.14 | Não há variante `-dev` | Dependências preparadas fora da imagem | Interpretador Python |

Os exemplos completos de cada família estão em [Usar no Dockerfile](../como-utilizar/dockerfile.mdx#multi-stage).

## Python sem `-dev` {#python}

Python não ter `-dev` não significa que qualquer biblioteca possa ser instalada sem preparação. Prepare as dependências em um ambiente autorizado, com a mesma versão do Python e a mesma arquitetura de destino, e copie somente o necessário para a imagem. Extensões nativas precisam ser compatíveis com o runtime. Veja o [exemplo de Python](../como-utilizar/dockerfile.mdx#artefato-pronto).

## Atualize os dois estágios {#atualizacoes}

Quando o build usa a `-dev`, a atualização da base precisa alcançar também esse estágio. Trocar somente o runtime não corrige vulnerabilidades incorporadas ao artefato durante a compilação. Veja [Atualizações e CVEs](../seguranca/atualizacoes.md).
