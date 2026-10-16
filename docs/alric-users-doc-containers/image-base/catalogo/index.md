---
title: Catálogo de imagens
sidebar_label: Imagens disponíveis
slug: /catalogo
description: Linguagens, versões e variantes de Image Base, com estado de suporte, disponibilidade por ambiente e como escolher a imagem certa.
---

O catálogo define **16 imagens: 9 runtimes e 7 variantes `-dev`**, para Java, Go, .NET, Node.js e Python. Todas seguem a mesma convenção: repositório `image-base-<framework>`, usuário não-root com UID/GID `10000`, diretório de trabalho `/app` e as plataformas `linux/amd64` e `linux/arm64`.

## Como escolher {#como-escolher}

1. Parta da linguagem e da versão principal que sua aplicação **já usa**. Trocar a base e a versão da linguagem ao mesmo tempo dificulta identificar a causa de incompatibilidades.
2. Use a imagem **runtime** no estágio final do Dockerfile.
3. Se a compilação ou a instalação de dependências acontece dentro do Docker, use a **`-dev` da mesma família e versão** no estágio de build. Veja [Runtime e -dev](./runtime-dev.md).
4. Confira o **suporte** e a **[disponibilidade](#disponibilidade)** no seu ambiente antes de adotar.

## Imagens {#imagens}

| Linguagem e versão | Runtime (estágio final) | `-dev` (estágio de build) | Suporte |
| --- | --- | --- | --- |
| Go 1.26 | `image-base-go1-26` | `image-base-go1-26-dev` | Suportada · referência principal |
| Java 21 (LTS) | `image-base-java21` | `image-base-java21-dev` | Suportada |
| Java 25 (LTS) | `image-base-java25` | `image-base-java25-dev` | Suportada |
| .NET 10 (LTS) · ASP.NET Core | `image-base-dotnet10` | `image-base-dotnet10-dev` | Suportada |
| Node.js 22 (LTS) | `image-base-nodejs22` | `image-base-nodejs22-dev` | Suportada |
| Node.js 24 (LTS) | `image-base-nodejs24` | `image-base-nodejs24-dev` | Suportada |
| Python 3.13 | `image-base-python3-13` | Sem variante `-dev` | Suportada |
| Python 3.14 | `image-base-python3-14` | Sem variante `-dev` | Suportada |
| Go 1.25 | `image-base-go1-25` | `image-base-go1-25-dev` | **Sem suporte upstream**: [não use em novas adoções](#go-1-25) |

**Suportada** significa que o fornecedor da linguagem ainda mantém a série e que os pacotes da imagem receberam atualização recente. Estado revisado em 13/10/2026; próxima revisão até 13/11/2026.

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

## Disponibilidade {#disponibilidade}

Estar no catálogo não significa estar disponível em todos os ambientes. Cada imagem passa por estados diferentes:

| Estado | Significado |
| --- | --- |
| **Definida no catálogo** | A plataforma sabe construir e testar a variante. Vale para as 16 imagens desta página. |
| **Suporte upstream** | O fornecedor da linguagem ainda publica correções para a série. Veja a coluna Suporte. |
| **Validada** | Passou nos testes da plataforma: build, scan de vulnerabilidades, confiança TLS e execução nas duas arquiteturas. |
| **Publicada** | Existe uma referência utilizável (`stable` ou o digest de um índice promovido) no registry do ambiente. |
| **Liberada para consumo** | O uso está autorizado no ambiente em que sua aplicação roda. |

Situação em outubro de 2026:

- As 16 imagens são validadas pela plataforma sempre que a base compartilhada muda, e o catálogo completo é certificado sob demanda.
- A publicação e a promoção contínuas para `stable` cobrem o par **Go 1.26** (`image-base-go1-26` e `image-base-go1-26-dev`), referência principal do produto.
- Para as demais variantes, esta documentação **não garante** que exista `stable` no seu ambiente.
- A liberação para consumo corporativo depende de cada ambiente.

:::info Antes de adotar
Para usar uma variante fora do par Go 1.26, ou para confirmar a liberação no seu ambiente, [fale com o Containers Products](../suporte.md).
:::

## Go 1.25: sem suporte upstream {#go-1-25}

:::warning Não use Go 1.25 em novas adoções
A série Go 1.25 deixou de receber correções do projeto Go em 19/08/2026, com o lançamento do Go 1.27, e a versão empacotada na imagem não inclui as últimas correções de segurança da série. `image-base-go1-25` e `image-base-go1-25-dev` continuam no catálogo até a decisão do owner do produto. Migre para Go 1.26.
:::

### Migrar para Go 1.26 {#migrar-go-1-26}

1. Troque o estágio de build para `image-base-go1-26-dev` e o estágio final para `image-base-go1-26`.
2. Não é preciso alterar a diretiva `go` do `go.mod`: o toolchain 1.26 compila módulos declarados com `go 1.25`.
3. Recompile, rode os testes nas arquiteturas de destino e confira a versão embutida com `go version -m <binário>`.
4. Imagens já implantadas não mudam sozinhas: a correção só chega no próximo build e deploy da aplicação.

## Tags e referências {#tags}

| Referência | Exemplo | Quando usar |
| --- | --- | --- |
| `stable` | `image-base-go1-26:stable` | Conveniência. Acompanha as promoções: dois builds em momentos diferentes podem receber bases diferentes. |
| Digest do índice | `image-base-go1-26@sha256:<digest>` | Builds reproduzíveis e consumo auditado. Use o digest de um índice promovido; veja [como fixar](../como-utilizar/dockerfile.mdx#fixar-digest). |
| Build tag | `<ddmmaa>-<hhmm>-r<execução>-a<tentativa>` | Rastrear de qual publicação veio uma base. É imutável, mas pode expirar com a política de retenção. |

Não crie tags nos repositórios `image-base-*`: eles são mantidos pela plataforma.
