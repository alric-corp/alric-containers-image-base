---
title: Perguntas frequentes
sidebar_label: Perguntas frequentes
description: Respostas rápidas sobre consumo, runtime, diagnóstico, segurança e atualizações de Image Base.
---

## Consumo {#consumo}

### Preciso conhecer como as imagens base são construídas? {#preciso-conhecer-a-construcao}

Não. Para consumir, use a imagem correspondente no Dockerfile e siga o [fluxo de uso](../como-utilizar/dockerfile.mdx).

### Onde encontro o endereço do registry? {#endereco-do-registry}

Ele é configurado na esteira da squad junto com o acesso de leitura. Se a sua esteira ainda não consome Image Base, solicite a habilitação pelo [canal de suporte](../suporte.md).

### Preciso da imagem `-dev` se meu pipeline já compila? {#dev-com-pipeline}

Não necessariamente. Você pode copiar o artefato pronto para o runtime, desde que ele seja compatível com a versão, o sistema, as bibliotecas e a arquitetura de destino.

### Uso `:stable` nos dois estágios? {#stable-nos-dois-estagios}

Se você compila com a `-dev`, use a mesma referência nos dois estágios, sempre da mesma família e versão. Para builds reproduzíveis, fixe o digest de cada estágio separadamente. Veja [Fixar a versão da base](../como-utilizar/dockerfile.mdx#fixar-digest).

### Posso usar a `-dev` como imagem final? {#dev-como-final}

Não é o padrão recomendado. A `-dev` é para o estágio de construção; o estágio final usa o runtime. `-dev` descreve a função da imagem, não um ambiente.

### A imagem vem com todas as bibliotecas da minha aplicação? {#bibliotecas-da-aplicacao}

Não. Spring, dependências npm, Python e NuGet e bibliotecas internas pertencem à aplicação. A base não é um ambiente de desenvolvimento completo.

### Posso usar Go 1.25? {#go-1-25}

Não em novas adoções: a série não recebe mais correções do projeto Go. Migre para Go 1.26, como descrito no [catálogo](../catalogo/index.md#go-1-25).

## Runtime e diagnóstico {#runtime}

### Posso fazer `RUN apk add`, `apt-get` ou instalar Bash no runtime? {#instalar-pacotes}

Não conte com esses comandos na imagem final: o runtime não tem shell nem gerenciador de pacotes. Uma dependência adicional de sistema precisa ser avaliada no contrato da base. Não use a `-dev` como runtime para contornar a ausência de ferramentas.

### Por que não consigo abrir um shell no container? {#shell}

Porque o runtime não tem shell, por design. Use logs e eventos e, quando autorizado, um [container efêmero no EKS](../troubleshooting/eks.md#container-efemero) ou o [ECS Exec](../troubleshooting/ecs.md#ecs-exec) com binários existentes na imagem.

## Segurança e atualizações {#seguranca}

### O scan aprovado da base dispensa o scan da minha imagem final? {#scan-da-imagem-final}

Não. Seu código, suas dependências e seus arquivos acrescentam conteúdo que não existia na base. A assinatura da base também não comprova a segurança desse conteúdo.

### Atualizar a tag da base e reiniciar o Pod corrige tudo? {#reiniciar-corrige}

Não. É necessário reconstruir a aplicação com a base corrigida, testar e fazer deploy da nova imagem final. Veja [Atualizações e CVEs](../seguranca/atualizacoes.md).

### Como faço rollback? {#rollback}

Pelo processo de release da aplicação, usando uma imagem final anterior retida e autorizada. Mudanças na `stable` da base não alteram deployments existentes nem substituem o rollback da squad.

### As imagens já confiam nas CAs corporativas? {#cas-corporativas}

Ainda não: as imagens publicadas confiam nas autoridades públicas do bundle padrão, e a inclusão das CAs corporativas depende de aprovação. Veja [Certificados e HTTPS](../seguranca/certificados.md#cas-corporativas).
